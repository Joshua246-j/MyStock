import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.database import Base, get_db
from app.services.memory import MemoryService, extract_memory_directive
from app.services.chat import ChatService
from app.analysis.capabilities import (
    APPLICATION_CAPABILITIES,
    UNSUPPORTED_CAPABILITIES,
    is_capability_query,
    get_capability_context,
)
from app.analysis.orchestrator import orchestrate_chat


@pytest.fixture
def mem_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        yield db
    engine.dispose()


@pytest.fixture
def api_client(mem_db):
    def override_get_db():
        try:
            yield mem_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


# ==========================================
# 1. Capability Registry Tests
# ==========================================

def test_capability_detection():
    assert is_capability_query("Can I buy 50 shares of AAPL through this bot?")
    assert is_capability_query("Can this terminal place orders?")
    assert is_capability_query("What forecasting models are supported?")
    assert is_capability_query("How does forecasting work in this app?")
    assert is_capability_query("What indicators are supported?")
    assert is_capability_query("Can you automate trade execution?")
    # Non-capability queries
    assert not is_capability_query("What is the current price of NVDA?")
    assert not is_capability_query("Analyze Reliance technical indicators")


def test_capability_context_boundaries():
    ctx = get_capability_context("Can I execute trades and place market orders?")
    assert "CRITICAL RULE ON TRADING" in ctx or "DOES NOT execute" in ctx
    assert "brokerage" in ctx.lower() or "trade execution" in ctx.lower()

    forecast_ctx = get_capability_context("Tell me about the forecasting system")
    assert "Probabilistic Forecasting" in forecast_ctx
    assert "Ridge" in forecast_ctx or "prediction interval" in forecast_ctx.lower()


# ==========================================
# 2. Memory Directive Extraction Tests
# ==========================================

def test_extract_memory_directive():
    mem_svc = MemoryService(None)

    # Set directives
    res = mem_svc.extract_memory_directive("Please remember that my risk tolerance is low")
    assert res is not None
    assert res["action"] == "set"
    assert res["key"] == "risk_tolerance"
    assert "low" in res["value"].lower()

    res2 = extract_memory_directive("Remember that I prefer 1-day candlestick charts")
    assert res2 is not None
    assert res2["action"] == "set"
    assert "candlestick" in res2["value"].lower()

    # Forget directives
    res3 = mem_svc.extract_memory_directive("Forget my risk tolerance")
    assert res3 is not None
    assert res3["action"] == "delete"
    assert res3["key"] == "risk_tolerance"

    # List directives
    res4 = mem_svc.extract_memory_directive("What do you remember about me?")
    assert res4 is not None
    assert res4["action"] == "list"

    res5 = extract_memory_directive("Show all my saved memories")
    assert res5 is not None
    assert res5["action"] == "list"

    # Clear directives
    res6 = mem_svc.extract_memory_directive("Forget everything about me")
    assert res6 is not None
    assert res6["action"] == "clear"

    # Regular messages should not trigger directives
    assert mem_svc.extract_memory_directive("What was Apple's revenue in 2024?") is None
    assert mem_svc.extract_memory_directive("Tell me about RELIANCE technicals") is None


# ==========================================
# 3. Memory Service CRUD & Isolation Tests
# ==========================================

def test_memory_crud_and_user_isolation(mem_db):
    mem_svc = MemoryService(mem_db)

    # Set memories for user1
    m1 = mem_svc.set_memory(key="risk_tolerance", value="conservative", category="preference", user_id="user_alpha")
    assert m1["id"] is not None
    assert m1["key"] == "risk_tolerance"
    assert m1["value"] == "conservative"

    m2 = mem_svc.set_memory(key="favorite_sector", value="semiconductors", category="preference", user_id="user_alpha")

    # Set memories for user2
    mem_svc.set_memory(key="risk_tolerance", value="aggressive", category="preference", user_id="user_beta")

    # Verify user_alpha memories
    alpha_memories = mem_svc.get_memories("user_alpha")
    assert len(alpha_memories) == 2
    keys = {m["key"] for m in alpha_memories}
    assert keys == {"risk_tolerance", "favorite_sector"}

    # Strict isolation: user_beta only sees their own
    beta_memories = mem_svc.get_memories("user_beta")
    assert len(beta_memories) == 1
    assert beta_memories[0]["value"] == "aggressive"

    # Relevance retrieval
    relevant = mem_svc.get_relevant_memories("What semiconductor stocks fit my conservative risk?", user_id="user_alpha")
    assert len(relevant) >= 1

    # Delete single key
    deleted = mem_svc.delete_memory_by_key("risk_tolerance", user_id="user_alpha")
    assert deleted is True
    assert len(mem_svc.get_memories("user_alpha")) == 1

    # Clear user memories
    cleared = mem_svc.clear_memories("user_alpha")
    assert cleared == 1
    assert len(mem_svc.get_memories("user_alpha")) == 0
    # user_beta still intact
    assert len(mem_svc.get_memories("user_beta")) == 1


# ==========================================
# 4. ChatService Memory Integration
# ==========================================

def test_chat_service_intercepts_memory_commands(mem_db):
    chat_svc = ChatService(mem_db)

    # 1. Send "Remember that..."
    res1 = chat_svc.chat("Remember that my preferred currency is INR", session_id="test_sess")
    assert "Memory Saved" in res1["answer"]
    assert res1["citations"] == []
    assert res1["answer_method"] == "memory_directive"

    # Verify stored in DB
    mem_svc = MemoryService(mem_db)
    memories = mem_svc.get_memories()
    assert len(memories) == 1
    assert "currency" in memories[0]["key"] or "preferred" in memories[0]["key"]

    # 2. Query "What do you remember about me?"
    res2 = chat_svc.chat("What do you remember about me?", session_id="test_sess")
    assert "INR" in res2["answer"]
    assert res2["citations"] == []

    # 3. Send "Forget..."
    res3 = chat_svc.chat("Forget everything about me", session_id="test_sess")
    assert "Memories Cleared" in res3["answer"]
    assert len(mem_svc.get_memories()) == 0


# ==========================================
# 5. REST API Endpoints (/api/memory)
# ==========================================

def test_api_memory_endpoints(api_client):
    # GET initially empty
    resp = api_client.get("/api/memory")
    assert resp.status_code == 200
    assert resp.json()["memories"] == []

    # POST new memory
    payload = {
        "key": "trading_horizon",
        "value": "swing trading (3-10 days)",
        "category": "preference"
    }
    resp = api_client.post("/api/memory", json=payload)
    assert resp.status_code == 200
    created = resp.json()
    assert created["success"] is True
    assert created["memory"]["key"] == "trading_horizon"
    assert created["memory"]["value"] == "swing trading (3-10 days)"
    mem_id = created["memory"]["id"]

    # GET returns created memory
    resp = api_client.get("/api/memory")
    assert resp.status_code == 200
    items = resp.json()["memories"]
    assert len(items) == 1
    assert items[0]["id"] == mem_id

    # DELETE memory
    resp = api_client.delete(f"/api/memory/{mem_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    # GET is empty again
    resp = api_client.get("/api/memory")
    assert resp.status_code == 200
    assert len(resp.json()["memories"]) == 0


# ==========================================
# 6. Contextual Follow-up Symbol Resolution
# ==========================================

@pytest.mark.asyncio
async def test_contextual_followup_resolves_prior_symbol(monkeypatch):
    class MockMarket:
        def get_technical_analysis(self, symbol, period=None, interval=None, **kwargs):
            return {
                "success": True,
                "symbol": symbol,
                "metrics": {"rsi": 54.2},
                "source": "MockProvider",
                "data_status": "LIVE",
                "last_bar_at": "2026-10-21",
            }

    async def mock_ollama_chat(messages, model, **kwargs):
        return (
            "## Key Facts\n- INFY RSI is 54.2.\n\n"
            "## Analysis\nThe RSI for INFY is 54.2 indicating neutral momentum.\n\n"
            "## Limitations\n- Technical indicators are historical and lagging."
        )

    async def mock_health(*args, **kwargs):
        return True

    from app.analysis import orchestrator
    monkeypatch.setattr(orchestrator.ollama_client, "check_health", mock_health)
    monkeypatch.setattr(orchestrator.ollama_client, "chat", mock_ollama_chat)

    history = [
        {"role": "user", "content": "How is INFY performing?"},
        {"role": "assistant", "content": "Infosys (INFY.NS) is trading at 1,850 INR with solid volume."}
    ]

    # Follow-up without explicit ticker
    res = await orchestrate_chat(
        "What are its technical indicators?",
        symbol=None,
        history=history,
        market_data=MockMarket(),
        settings={"automatic_technical_analysis": True, "request_timeout": 5}
    )

    assert "INFY" in res["answer"] or "RSI" in res["answer"]
    assert any("INFY" in c for c in res["citations"])
