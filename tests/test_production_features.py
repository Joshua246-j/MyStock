import asyncio
import threading
import time
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from app.analysis.orchestrator import classify_intents, orchestrate_chat, _missing_research_sections, _citation_matches, _document_numeric_fact, _missing_fact_values, _direct_source_answer, _unsupported_answer_terms, _answer_claims_evidence_is_missing, _unsupported_entity_relations
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


def test_news_queries_use_web_search_but_uploaded_filing_questions_stay_scoped():
    news = classify_intents("What are the latest news and events for AAPL?", "AAPL", {})
    filing = classify_intents("According to the uploaded 10-K, what was latest revenue?", "AAPL", {})

    assert "web_research" in news
    assert "document_qa" in filing
    assert "web_research" not in filing


def test_standalone_filing_requests_route_to_indexed_document_retrieval():
    intents = classify_intents("Find the latest 10-K filing", None, {})

    assert "document_qa" in intents


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


def test_faiss_store_is_a_process_wide_singleton():
    first = vector_store_module.get_vector_store()
    second = vector_store_module.get_vector_store()

    assert first is second


def test_pdf_remains_retrievable_when_ollama_embeddings_and_faiss_are_unavailable(tmp_path, monkeypatch):
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
            raise RuntimeError("FAISS embeddings are unavailable")

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
    technical_request = {}

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
        def get_technical_analysis(self, symbol, **kwargs):
            technical_request.update(symbol=symbol, **kwargs)
            return blocking_result({"success": True, "metrics": {"RSI_14": 51.2}, "source": "fixture", "last_bar_at": "2026-10-08"})
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
        chart_period="3mo",
        chart_interval="1wk",
        chart_mode="candlestick",
        chart_view="rsi",
        market_data=MockMarket(),
        retriever=MockRetriever(),
    ))

    assert peak >= 2
    assert result["model"] == "test-model:latest"
    assert result["data_timestamp"] == "2026-09-24T10:00:00Z"
    assert result["sources_unverified"] is False
    assert result["format_unverified"] is False
    assert "earnings.pdf — Page 2" in result["citations"]
    assert technical_request == {"symbol": "AAPL", "period": "3mo", "interval": "1wk"}
    assert any("3mo, 1wk" in citation and "2026-10-08" in citation for citation in result["citations"])
    assert result["structured_analysis"]["chart_context"] == {"symbol": "AAPL", "period": "3mo", "interval": "1wk", "mode": "candlestick", "view": "rsi"}


def test_orchestrator_uses_recent_conversation_context_for_followup_rag(monkeypatch):
    observed = {}
    requested_market_tools = []

    class MockRetriever:
        def retrieve_context(self, query, **kwargs):
            observed["query"] = query
            return {"context": "Revenue was $100 million in FY2025.", "sources": ["fixture.pdf — Page 2"],
                    "passages": [{"content": "Revenue was $100 million in FY2025.", "source": "fixture.pdf — Page 2"}],
                    "retrieval_mode": "hybrid", "degraded": False}

    async def mock_check_health(*_args, **_kwargs): return True
    async def mock_chat(*_args, **_kwargs):
        return "## Answer\nThe earlier period is in the retrieved filing.\n\n## Key Facts\n- The filing includes prior-year revenue.\n\n## Analysis\nThe document provides the requested context.\n\n## Limitations\nOnly the retrieved passage was checked.\n\n## Sources\n- fixture.pdf — Page 2"
    class MockMarket:
        def get_quote(self, *_args, **_kwargs):
            requested_market_tools.append("quote")
            return {"success": False, "error": "unexpected quote request"}
    monkeypatch.setattr("app.analysis.orchestrator.ollama_client.check_health", mock_check_health)
    monkeypatch.setattr("app.analysis.orchestrator.ollama_client.chat", mock_chat)

    result = asyncio.run(orchestrate_chat(
        "What about the prior year?", symbol="TSTX",
        history=[{"role": "user", "content": "According to the uploaded 10-K, what was revenue for FY2025?"}],
        settings={"request_timeout": 5}, market_data=MockMarket(), retriever=MockRetriever(),
    ))

    assert "FY2025" in observed["query"] and "Follow-up: What about the prior year?" in observed["query"]
    assert result["structured_analysis"]["evidence_types"] == ["documents"]
    assert result["retrieval"]["documents"] == 1
    assert requested_market_tools == []


def test_explicit_prompt_ticker_overrides_the_open_chart_symbol(monkeypatch):
    requested_symbols = []

    class MockMarket:
        def get_quote(self, symbol, **_kwargs):
            requested_symbols.append(symbol)
            return {"success": True, "price": 100, "change": 1, "change_percent": 1, "source": "fixture", "timestamp": "2026-10-10T10:00:00Z", "status": "LIVE"}

    class MockRetriever:
        def retrieve_context(self, *_args, **_kwargs): return {"context": "", "sources": []}

    async def mock_check_health(*_args, **_kwargs): return True
    async def mock_chat(*_args, **_kwargs):
        return "## Answer\nMSFT is at the supplied provider price.\n\n## Key Facts\n- Provider price supplied.\n\n## Analysis\nNo additional calculation.\n\n## Limitations\nProvider freshness is not verified.\n\n## Sources\n- Market quote"
    monkeypatch.setattr("app.analysis.orchestrator.ollama_client.check_health", mock_check_health)
    monkeypatch.setattr("app.analysis.orchestrator.ollama_client.chat", mock_chat)

    asyncio.run(orchestrate_chat(
        "What is MSFT current price?", symbol="AAPL",
        settings={"request_timeout": 5}, market_data=MockMarket(), retriever=MockRetriever(),
    ))

    assert requested_symbols == ["MSFT"]


def test_research_response_contract_requires_explicit_sections():
    valid = "## Answer\nA\n## Key Facts\nB\n## Analysis\nC\n## Limitations\nD\n## Sources\nE"
    assert _missing_research_sections(valid, require_sources=True) == []
    assert _missing_research_sections("## Answer\nA", require_sources=True) == ["Key Facts", "Analysis", "Limitations", "Sources"]
    assert _citation_matches("verified_revenue_fixture.pdf — Page 1", "\n- verified_revenue_fixture.pdf — Page 1\n")


def test_concise_research_allows_inline_answer_and_requires_sources_only():
    response = "The source says Products and Services.\n\n## Sources\n- SEC AAPL 10-K"
    assert _missing_research_sections(response, require_sources=True, detail="concise") == []


def test_document_answer_guard_detects_unsupported_product_names():
    response = (
        "## Answer Two categories are ‘Smartphones’ and ‘Personal Computers’.\n\n"
        "## Sources\n- SEC AAPL 10-K"
    )
    passages = [{"content": "Net sales: Products $307,003 million; Services $109,158 million."}]
    assert {"smartphones", "personal", "computers"}.issubset(
        set(_unsupported_answer_terms(response, "Name two product categories in the Apple 10-K.", passages))
    )


def test_document_answer_guard_detects_internal_evidence_contradiction():
    response = (
        "## Answer The categories are smartphones and personal computers.\n\n"
        "## Analysis The evidence does not provide specific product categories."
    )
    assert _answer_claims_evidence_is_missing(response)


def test_document_answer_guard_rejects_entity_relation_not_in_same_passage():
    response = "The Mac line includes laptops and iPad."
    passages = [
        {"content": "Mac is the company's line of personal computers that includes laptops."},
        {"content": "iPad is a separate product line of tablets."},
    ]
    assert _unsupported_entity_relations(response, "What do iPhone and Mac refer to?", passages) == ["ipad"]


def test_document_answer_guard_withholds_unsupported_generated_claim(monkeypatch):
    class MockRetriever:
        def retrieve_context(self, *args, **kwargs):
            source = "SEC AAPL 10-K — https://www.sec.gov/Archives/aapl.htm"
            content = "Net sales: Products $307,003 million; Services $109,158 million."
            return {"context": content, "sources": [source], "passages": [{"content": content, "source": source}],
                    "retrieval_mode": "hybrid", "degraded": False}

    async def mock_check_health(*_args, **_kwargs): return True
    async def mock_chat(*_args, **_kwargs):
        return (
            "## Answer Two product categories are ‘Smartphones’ and ‘Personal Computers’.\n\n"
            "## Sources\n- SEC AAPL 10-K — https://www.sec.gov/Archives/aapl.htm"
        )

    monkeypatch.setattr("app.analysis.orchestrator.ollama_client.check_health", mock_check_health)
    monkeypatch.setattr("app.analysis.orchestrator.ollama_client.chat", mock_chat)
    result = asyncio.run(orchestrate_chat(
        "Name two product categories in the Apple 10-K.", settings={"request_timeout": 5, "response_detail": "concise"},
        mode="documents", document_ids=[1], retriever=MockRetriever(),
    ))

    assert result["numeric_validation"] == "not_applicable"
    assert result["answer_method"] == "deterministic_rag_insufficient_evidence"
    assert "couldn't verify a direct answer" in result["answer"]
    assert "Smartphones" not in result["answer"]
    assert result["sources_unverified"] is False


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


def test_numeric_document_question_uses_exact_extracted_value_without_calling_model(monkeypatch):
    class MockRetriever:
        def retrieve_context(self, *args, **kwargs):
            assert kwargs["metadata_filter"] == {"ticker": "TSTX", "document_type": "10-K"}
            return {"context": "Revenue for FY2025 was $125 million.", "sources": ["fixture.pdf — Page 1"],
                    "passages": [{"content": "Revenue for FY2025 was $125 million.", "source": "fixture.pdf — Page 1"}],
                    "retrieval_mode": "hybrid", "degraded": False}

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("Numeric document facts must be returned from the source passage")

    monkeypatch.setattr("app.analysis.orchestrator.ollama_client.check_health", fail_if_called)
    monkeypatch.setattr("app.analysis.orchestrator.ollama_client.chat", fail_if_called)
    result = asyncio.run(orchestrate_chat(
        "According to the uploaded TSTX 10-K, what was revenue for FY2025?",
        symbol="TSTX", settings={"request_timeout": 5}, retriever=MockRetriever(),
    ))

    assert result["answer_method"] == "extractive_source_fallback"
    assert "$125 million" in result["answer"]
    assert "fixture.pdf — Page 1" in result["citations"]
    assert "fundamental" not in result["structured_analysis"]["evidence_types"]


def test_numeric_document_question_withholds_value_when_source_has_no_number(monkeypatch):
    class MockRetriever:
        def retrieve_context(self, *args, **kwargs):
            return {"context": "Revenue information is discussed.", "sources": ["fixture.pdf — Page 1"],
                    "passages": [{"content": "Revenue information is discussed.", "source": "fixture.pdf — Page 1"}],
                    "retrieval_mode": "keyword", "degraded": True}

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("Insufficient document evidence must not be sent to generation")

    monkeypatch.setattr("app.analysis.orchestrator.ollama_client.check_health", fail_if_called)
    monkeypatch.setattr("app.analysis.orchestrator.ollama_client.chat", fail_if_called)
    result = asyncio.run(orchestrate_chat(
        "According to the uploaded TSTX 10-K, what was revenue for FY2025?",
        symbol="TSTX", settings={"request_timeout": 5}, retriever=MockRetriever(),
    ))

    assert result["numeric_validation"] == "insufficient_evidence"
    assert "could not be verified" in result["answer"]
    assert result["sources_unverified"] is False
    assert result["answer_method"] == "deterministic_insufficient_evidence"
    assert result["model"] is None


def test_numeric_document_answer_does_not_substitute_a_different_financial_metric(monkeypatch):
    class MockRetriever:
        def retrieve_context(self, *args, **kwargs):
            source = "fixture.pdf — Page 1"
            text = "Revenue was 735 million dollars for fiscal 2026."
            return {"context": text, "sources": [source], "passages": [{"content": text, "source": source}],
                    "retrieval_mode": "hybrid", "degraded": False}

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("An unrelated numeric fact must not be substituted for the requested metric")

    monkeypatch.setattr("app.analysis.orchestrator.ollama_client.check_health", fail_if_called)
    monkeypatch.setattr("app.analysis.orchestrator.ollama_client.chat", fail_if_called)
    result = asyncio.run(orchestrate_chat(
        "According to the uploaded TSTX 10-K, what was net income for FY2026?",
        symbol="TSTX", settings={"request_timeout": 5}, retriever=MockRetriever(),
    ))

    assert result["numeric_validation"] == "insufficient_evidence"
    assert "could not be verified" in result["answer"]


def test_model_capability_filter_hides_embedding_only_models_from_chat_selection():
    assert OllamaClient._supports({"capabilities": ["completion", "tools"]}, "generation")
    assert not OllamaClient._supports({"capabilities": ["embedding"]}, "generation")
    assert OllamaClient._supports({"capabilities": ["embedding"]}, "embedding")
    assert not OllamaClient._supports({"capabilities": ["completion"]}, "embedding")
    assert not OllamaClient._supports({"name": "nomic-embed-text:latest"}, "generation")
    assert OllamaClient._supports({"name": "qwen3:8b"}, "generation")
    assert OllamaClient._supports({"name": "nomic-embed-text:latest"}, "embedding")


def test_ollama_client_rejects_truncated_output_instead_of_returning_a_partial_answer():
    with pytest.raises(OllamaError) as raised:
        OllamaClient._completed_text({"response": "partial answer", "done": True, "done_reason": "length"}, "response")
    assert raised.value.code == "ollama_output_limit"
    assert "Maximum answer tokens" in str(raised.value)
