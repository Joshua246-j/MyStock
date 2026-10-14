import asyncio
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.analysis.orchestrator import (
    classify_intents,
    orchestrate_chat,
    _is_greeting,
    _followup_context,
)
from app.api.routes.chat import ChatRequest, chat as post_chat
from app.api.routes.settings import update_settings, reset_settings, get_settings_schema, DEFAULT_SETTINGS
from app.market.symbol_resolver import resolve_symbol
from app.ollama_client import OllamaError
from app.services.chat import ChatService


# ==========================================
# 1. Greetings Fast-Path Tests
# ==========================================

def test_greeting_patterns():
    assert _is_greeting("Hi")
    assert _is_greeting("hello")
    assert _is_greeting("Hey there!")
    assert _is_greeting("Good morning")
    assert _is_greeting("good evening assistant")
    assert _is_greeting("what's up mystock?")
    # Non-greetings
    assert not _is_greeting("Hi, what is Apple's stock price?")
    assert not _is_greeting("Hello, tell me about NVDA")
    assert not _is_greeting("What is StockRAG?")


def test_greeting_intent_classification():
    # Pure greetings must classify strictly to general_chat
    assert classify_intents("Hi", None, {}) == {"general_chat"}
    assert classify_intents("hello there", "AAPL", {}) == {"general_chat"}
    assert classify_intents("Good morning", "RELIANCE.NS", {}) == {"general_chat"}


def test_greeting_skips_market_and_rag_retrieval(monkeypatch):
    class ExplodingRetriever:
        def retrieve_context(self, *args, **kwargs):
            raise AssertionError("Retriever should NEVER be called on a greeting")

    class ExplodingMarketData:
        def get_quote(self, *args, **kwargs):
            raise AssertionError("Market quote should NEVER be called on a greeting")
        def get_technical_analysis(self, *args, **kwargs):
            raise AssertionError("Technical analysis should NEVER be called on a greeting")
        def get_financials(self, *args, **kwargs):
            raise AssertionError("Financials should NEVER be called on a greeting")
        def get_news(self, *args, **kwargs):
            raise AssertionError("News should NEVER be called on a greeting")

    async def mock_check_health(*args, **kwargs):
        return True

    captured_prompt = []
    async def mock_chat(messages, model, **kwargs):
        captured_prompt.extend(messages)
        return "Hello! How can I assist with your market research today?"

    monkeypatch.setattr("app.analysis.orchestrator.ollama_client.check_health", mock_check_health)
    monkeypatch.setattr("app.analysis.orchestrator.ollama_client.chat", mock_chat)

    result = asyncio.run(orchestrate_chat(
        "Hi there!",
        symbol="AAPL",  # Active UI symbol should not contaminate greeting
        settings={"request_timeout": 5},
        retriever=ExplodingRetriever(),
        market_data=ExplodingMarketData(),
    ))

    assert "Hello!" in result["answer"]
    assert result["citations"] == []
    assert result["retrieval"]["market_sources"] == 0
    assert result["retrieval"]["web_sources"] == 0
    assert result["retrieval"]["documents"] == 0
    # The prompt sent to the LLM must have the greeting instruction
    assert any("warmly" in m.get("content", "").lower() for m in captured_prompt if m.get("role") == "system")


# ==========================================
# 2. Invalid Tickers Tests
# ==========================================

def test_invalid_symbol_resolution():
    res = resolve_symbol("INVALID$$$XYZ")
    assert res["valid"] is False
    assert res["input"] == "INVALID$$$XYZ"
    assert res["resolved_symbol"] is None


# ==========================================
# 3. Missing Documents Tests
# ==========================================

def test_missing_document_ids_raise_value_error():
    class DummyQuery:
        def filter(self, *args, **kwargs):
            return self
        def first(self):
            return None
        def all(self):
            return []  # None found

    class DummyDb:
        def query(self, *args, **kwargs):
            return DummyQuery()

    service = ChatService(DummyDb())
    with pytest.raises(ValueError, match="One or more selected documents are unavailable"):
        service.chat(
            message="Summarize this",
            dataset_id=None,
            dataset_path=None,
            symbol=None,
            session_id=None,
            mode="documents",
            document_ids=[9999, 10000],
        )


# ==========================================
# 4. Settings Schema & Reset Tests
# ==========================================

def test_settings_schema_structure():
    schema_data = get_settings_schema()
    assert "defaults" in schema_data
    assert "schema" in schema_data
    schema = schema_data["schema"]
    assert "temperature" in schema
    assert "context_size" in schema
    assert "top_p" in schema
    assert "top_k" in schema
    assert "repeat_penalty" in schema
    assert "seed" in schema
    assert "max_output_tokens" in schema
    assert schema["max_output_tokens"]["max"] == 16384
    assert "streaming" in schema


def test_reset_settings_returns_defaults():
    class DummyRecord:
        settings = {"temperature": 1.8, "top_k": 100}
        updated_at = None

    class DummyDb:
        def __init__(self):
            self.committed = False
        def query(self, *args, **kwargs):
            return self
        def first(self):
            return DummyRecord()
        def commit(self):
            self.committed = True

    db = DummyDb()
    res = reset_settings(db)
    assert res == DEFAULT_SETTINGS
    assert db.committed is True


def test_update_settings_validates_numeric_ranges():
    class DummyDb:
        pass

    with pytest.raises(HTTPException) as exc:
        update_settings({"temperature": 5.0}, DummyDb())
    assert exc.value.status_code == 422
    assert "temperature must be between" in exc.value.detail

    with pytest.raises(HTTPException) as exc:
        update_settings({"top_k": -10}, DummyDb())
    assert exc.value.status_code == 422
    assert "top_k must be between" in exc.value.detail


def test_update_settings_rejects_unknown_keys():
    with pytest.raises(HTTPException) as exc:
        update_settings({"fabricated_setting_xyz": 123}, None)
    assert exc.value.status_code == 422
    assert "Unknown setting(s)" in exc.value.detail


# ==========================================
# 5. Chat Request Parameters & Persona Limits
# ==========================================

def test_chat_request_accepts_all_sampling_parameters():
    req = ChatRequest(
        message="Hello",
        temperature=0.7,
        top_p=0.95,
        top_k=50,
        repeat_penalty=1.2,
        seed=42,
        max_output_tokens=4096,
        custom_persona="You are a conservative value investor.",
    )
    assert req.top_k == 50
    assert req.repeat_penalty == 1.2
    assert req.seed == 42
    assert req.max_output_tokens == 4096


def test_chat_request_rejects_excessive_custom_persona():
    with pytest.raises(ValidationError):
        ChatRequest(
            message="Hello",
            custom_persona="A" * 2500,  # exceeds 2000 character limit
        )


# ==========================================
# 6. Follow-up Context & Chat History Isolation
# ==========================================

def test_followup_context_does_not_bleed_into_unrelated_queries():
    history = [
        {"role": "user", "content": "What is Apple's revenue and gross margin for FY2024?"},
        {"role": "assistant", "content": "Apple reported $391B in revenue with 46% margin."},
    ]

    # Unrelated queries should NOT attach prior context
    assert _followup_context("What is Tesla's delivery count?", history) == ""
    assert _followup_context("Hi there!", history) == ""
    assert _followup_context("Explain machine learning", history) == ""

    # Genuine follow-up phrases SHOULD attach prior context
    followup = _followup_context("What about net income?", history)
    assert "Apple's revenue" in followup

    followup2 = _followup_context("Why did it change?", history)
    assert "Apple's revenue" in followup2
