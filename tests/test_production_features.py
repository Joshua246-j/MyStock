import asyncio
import threading
import time
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from app.analysis.orchestrator import classify_intents, orchestrate_chat, _missing_research_sections, _citation_matches, _document_numeric_fact, _missing_fact_values, _direct_source_answer
from app.market.service import MarketDataService
from app.api.routes.settings import get_settings, update_settings
from app.db.database import Base
from app.db.models import UserSettings
from app.analysis.technical import calculate_technical_indicators
from app.analysis.data_analysis import analyze_dataset
from app.ollama_client import OllamaError
from app.ollama_client import OllamaClient
from app.market.symbol_resolver import resolve_symbol
from app.api.routes.chat import ChatRequest, chat as post_chat
from app.rag import vector_store as vector_store_module
from app.rag import lexical_store as lexical_store_module
from app.documents import pdf as pdf_module
from sqlalchemy.pool import StaticPool
import pandas as pd


def test_intent_classifier_supports_combined_sources_and_settings():
    intents = classify_intents(
        "Compare AAPL RSI with the earnings PDF at https://www.sec.gov/filing",
        "AAPL",
        {"automatic_technical_analysis": True, "web_research_enabled": True},
    )

    assert {"technical", "document_qa", "web_research"}.issubset(intents)
    disabled = classify_intents("AAPL RSI", "AAPL", {"automatic_technical_analysis": False})
    assert "technical" not in disabled


def test_product_workflow_question_is_not_misrouted_to_document_contents():
    intents = classify_intents(
        "What is StockRAG and how do I upload my own PDF and ask it questions?",
        None,
        {},
    )
    assert "document_qa" not in intents
    assert "general_chat" in intents


def test_market_service_falls_back_after_primary_failure():
    class MockCache:
        def get(self, key): return None
        def set(self, *args, **kwargs): pass
        def delete(self, key): pass
    primary = SimpleNamespace(get_quote=lambda _symbol: {"success": False, "error": "rate limited"})
    fallback = SimpleNamespace(get_quote=lambda symbol: {"success": True, "symbol": symbol, "price": 123.5, "source": "fallback"})
    service = MarketDataService(provider=primary, fallback_providers=[fallback], cache=MockCache(), settings_provider=lambda: {"cache_ttl": 300})

    result = service.get_quote("AAPL")

    assert result["success"] is True
    assert result["source"] == "fallback"
    assert result["price"] == 123.5


def test_market_service_surfaces_both_provider_failures_clearly():
    class MockCache:
        def get(self, key): return None
        def set(self, *args, **kwargs): pass
        def delete(self, key): pass
    primary = SimpleNamespace(get_quote=lambda _symbol: {"success": False, "error": "Upstream unavailable"})
    fallback = SimpleNamespace(get_quote=lambda _symbol: {"success": False, "error": "US listings only"})
    service = MarketDataService(provider=primary, fallback_providers=[fallback], cache=MockCache(), settings_provider=lambda: {"cache_ttl": 300})

    result = service.get_quote("RELIANCE.NS")

    assert result["success"] is False
    assert "Primary" not in result["error"]
    assert "Upstream unavailable" in result["error"]
    assert "US listings only" in result["error"]


def test_technical_metrics_and_scenario_are_finite_and_bounded():
    closes = [100 * (1.001 ** day) for day in range(120)]
    frame = pd.DataFrame({"Date": pd.date_range("2025-01-01", periods=len(closes)), "Close": closes,
                          "High": [value * 1.01 for value in closes], "Low": [value * 0.99 for value in closes]})

    result = calculate_technical_indicators(frame)

    assert result["success"] is True
    assert result["metrics"]["RSI_14"] is not None
    assert 0 <= result["metrics"]["RSI_14"] <= 100
    assert result["metrics"]["ATR_14"] > 0
    scenario = result["scenario_estimate"]
    assert scenario["lower_80_percent"] <= scenario["central_estimate"] <= scenario["upper_80_percent"]
    assert scenario["horizon_trading_days"] == 20
    assert "not a validated investment forecast" in scenario["limitations"]


def test_indian_bluechips_and_indices_resolve_to_supported_exchange_symbols():
    assert resolve_symbol("reliance")["resolved_symbol"] == "RELIANCE.NS"
    assert resolve_symbol("^NSEI")["exchange"] == "NSE"
    assert resolve_symbol("^BSESN")["exchange"] == "BSE"


def test_dataset_profile_includes_computed_statistics_missingness_and_bounded_sample(tmp_path):
    dataset = tmp_path / "earnings.csv"
    dataset.write_text("symbol,revenue,region\nAAA,10,West\nBBB,20,East\nCCC,,West\n", encoding="utf-8")
    result = analyze_dataset(str(dataset), "compare revenue by region")

    assert result["success"] is True
    assert result["rows_analyzed"] == 3
    assert "median=15" in result["analysis_text"]
    assert "revenue=1" in result["analysis_text"]
    assert "AAA" in result["analysis_text"]


def test_orchestrator_raises_service_failure_instead_of_fabricating_ai_text(monkeypatch):
    class MockRetriever:
        def retrieve_context(self, *args, **kwargs): return {"context": "", "sources": []}
    async def mock_check_health_false(*_args, **_kwargs): return False
    monkeypatch.setattr("app.analysis.orchestrator.ollama_client.check_health", mock_check_health_false)

    with pytest.raises(OllamaError, match="Start Ollama"):
        asyncio.run(orchestrate_chat("What does StockRAG do?", settings={"request_timeout": 2}, retriever=MockRetriever()))


def test_general_chat_does_not_search_or_leak_unselected_uploaded_documents(monkeypatch):
    class MockRetriever:
        def retrieve_context(self, *args, **kwargs): raise AssertionError("unexpected RAG call")
    async def mock_check_health_true(*_args, **_kwargs): return True
    monkeypatch.setattr("app.analysis.orchestrator.ollama_client.check_health", mock_check_health_true)
    async def mock_chat(*_args, **_kwargs): return "StockRAG helps analyze evidence you provide."
    monkeypatch.setattr("app.analysis.orchestrator.ollama_client.chat", mock_chat)

    result = asyncio.run(orchestrate_chat("What is StockRAG designed to do?", settings={"request_timeout": 2}, retriever=MockRetriever()))

    assert result["answer"] == "StockRAG helps analyze evidence you provide."
    assert result["citations"] == []
    assert result["retrieval"]["document_modes"] == []


def test_chat_route_returns_structured_service_error_and_removes_failed_user_turn(monkeypatch):
    class Query:
        def filter(self, *_args, **_kwargs):
            return self
        def order_by(self, *_args, **_kwargs):
            return self
        def limit(self, value):
            return self
        def first(self):
            return None
        def all(self):
            return []

    class FakeDb:
        def __init__(self):
            self.deleted = []
        def query(self, _model):
            return Query()
        def add(self, _record):
            pass
        def commit(self):
            pass
        def delete(self, record):
            self.deleted.append(record)

    def fail_generation(**_kwargs):
        raise OllamaError("Model missing", code="ollama_model_missing", status_code=503)

    monkeypatch.setattr("app.services.chat.orchestrate_chat", fail_generation)
    db = FakeDb()
    from app.services.chat import ChatService
    service = ChatService(db)
    with pytest.raises(HTTPException) as raised:
        post_chat(ChatRequest(message="Explain this"), service)

    assert raised.value.status_code == 503
    assert raised.value.detail == {"code": "ollama_model_missing", "message": "Model missing"}
    assert any(getattr(record, "role", None) == "user" for record in db.deleted)


def test_vector_store_client_is_initialized_once_for_concurrent_request_safety(monkeypatch):
    created = []
    class FakeVectorStore:
        def __init__(self, **kwargs):
            created.append(kwargs)
    monkeypatch.setattr(vector_store_module, "Chroma", FakeVectorStore)
    monkeypatch.setattr(vector_store_module, "get_embeddings", lambda: "embedding-client")
    monkeypatch.setattr(vector_store_module, "_vector_store", None)

    first = vector_store_module.get_vector_store()
    second = vector_store_module.get_vector_store()

    assert first is second
    assert len(created) == 1


def test_pdf_remains_retrievable_when_ollama_embeddings_and_chroma_are_unavailable(tmp_path, monkeypatch):
    import pymupdf as fitz

    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    monkeypatch.setattr(lexical_store_module, "engine", test_engine)

    pdf_path = tmp_path / "earnings.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Project Cedar achieved revenue of 742 million rupees in fiscal quarter 2026.")
    document.save(pdf_path)
    document.close()

    class BrokenVectorStore:
        def add_texts(self, **_kwargs):
            raise RuntimeError("embedding model is not installed")

        def similarity_search_with_score(self, *_args, **_kwargs):
            raise RuntimeError("Chroma is offline")

    monkeypatch.setattr("app.rag.ingest.get_vector_store", BrokenVectorStore)
    monkeypatch.setattr("app.rag.retriever.get_vector_store", BrokenVectorStore)

    from app.rag.ingest import ingest_document
    ingested = ingest_document(pdf_module.PDFLoader(), str(pdf_path), "cedar-report.pdf", document_id=908172)
    retrieved = __import__("app.rag.retriever", fromlist=["retrieve_context"]).retrieve_context(
        "What revenue did Project Cedar report for fiscal quarter 2026?", document_ids=[908172]
    )

    assert ingested["success"] is True
    assert "742 million rupees" in retrieved["context"]
    assert retrieved["sources"] == ["cedar-report.pdf — Page 1"]
    assert retrieved["retrieval_mode"] == "keyword"
    assert retrieved["degraded"] is True
    test_engine.dispose()


def test_settings_merge_validate_and_persist():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as db:
        updated = update_settings({"theme": "dark", "request_timeout": 12, "max_output_tokens": 192}, db)
        read_back = get_settings(db)
        assert updated["theme"] == "dark"
        assert read_back["request_timeout"] == 12
        assert read_back["max_output_tokens"] == 192
        assert read_back["ai_model"] == "qwen2.5:1.5b"
        with pytest.raises(HTTPException):
            update_settings({"request_timeout": 0}, db)
        with pytest.raises(HTTPException):
            update_settings({"max_output_tokens": 32}, db)
    engine.dispose()


def test_orchestrator_fans_out_and_returns_real_model_and_citations(monkeypatch):
    active = 0
    peak = 0
    lock = threading.Lock()

    def blocking_result(value):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.08)
        with lock:
            active -= 1
        return value

    class MockMarket:
        def get_quote(self, symbol, **kwargs): return blocking_result({"success": True, "price": 123, "change": 2, "change_percent": 1.6, "source": "fixture", "timestamp": "2026-09-24T10:00:00Z", "status": "LIVE"})
        def get_technical_analysis(self, symbol, **kwargs): return blocking_result({"success": True, "metrics": {"RSI_14": 51.2}})
        def get_financials(self, symbol, **kwargs): return {"success": False}
        def get_news(self, symbol, **kwargs): return []

    class MockRetriever:
        def retrieve_context(self, *args, **kwargs): return blocking_result({"context": "Earnings increased year over year.", "sources": ["earnings.pdf — Page 2"]})

    async def mock_check_health_true(*_args, **_kwargs): return True
    monkeypatch.setattr("app.analysis.orchestrator.ollama_client.check_health", mock_check_health_true)
    async def mock_chat(*_args, **_kwargs): return "## Answer\nThe indicators and filing are consistent.\n\n## Key Facts\n- RSI is 51.2.\n\n## Analysis\nThe provided facts are consistent.\n\n## Limitations\nThe dataset is limited.\n\n## Sources\n- earnings.pdf — Page 2"
    monkeypatch.setattr("app.analysis.orchestrator.ollama_client.chat", mock_chat)

    result = asyncio.run(orchestrate_chat(
        "Compare AAPL RSI and price with the earnings PDF",
        symbol="AAPL",
        model="test-model:latest",
        settings={"request_timeout": 5, "ai_model": "test-model:latest", "automatic_technical_analysis": True},
        market_data=MockMarket(),
        retriever=MockRetriever(),
    ))

    assert peak >= 2
    assert result["model"] == "test-model:latest"
    assert result["data_timestamp"] == "2026-09-24T10:00:00Z"
    assert result["sources_unverified"] is False
    assert result["format_unverified"] is False
    assert "earnings.pdf — Page 2" in result["citations"]


def test_research_response_contract_requires_explicit_sections():
    valid = "## Answer\nA\n## Key Facts\nB\n## Analysis\nC\n## Limitations\nD\n## Sources\nE"
    assert _missing_research_sections(valid, require_sources=True) == []
    assert _missing_research_sections("## Answer\nA", require_sources=True) == ["Key Facts", "Analysis", "Limitations", "Sources"]
    assert _citation_matches("verified_revenue_fixture.pdf — Page 1", "\n- verified_revenue_fixture.pdf — Page 1\n")


def test_document_numeric_validation_uses_exact_source_when_model_drops_value():
    fact = _document_numeric_fact(
        "What was company revenue for FY2025?",
        [{"content": "Company revenue for FY2025 was $125 million.", "source": "filing.pdf — Page 4"}],
    )
    assert fact == {"text": "Company revenue for FY2025 was $125 million.", "source": "filing.pdf — Page 4"}
    assert _missing_fact_values(fact, "The company's revenue was  million in 2025.") == ["$125 million"]
    fallback = _direct_source_answer(fact)
    assert "$125 million" in fallback
    assert "filing.pdf — Page 4" in fallback
    assert _missing_research_sections(fallback, require_sources=True) == []


def test_model_capability_filter_hides_embedding_only_models_from_chat_selection():
    assert OllamaClient._supports({"capabilities": ["completion", "tools"]}, "generation")
    assert not OllamaClient._supports({"capabilities": ["embedding"]}, "generation")
    assert OllamaClient._supports({"capabilities": ["embedding"]}, "embedding")
    assert not OllamaClient._supports({"capabilities": ["completion"]}, "embedding")


def test_ollama_client_rejects_truncated_output_instead_of_returning_a_partial_answer():
    with pytest.raises(OllamaError) as raised:
        OllamaClient._completed_text({"response": "partial answer", "done": True, "done_reason": "length"}, "response")
    assert raised.value.code == "ollama_output_limit"
    assert "Maximum answer tokens" in str(raised.value)
