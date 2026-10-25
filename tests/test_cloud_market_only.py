import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def market_only_client(monkeypatch):
    monkeypatch.setenv("MARKET_ONLY", "true")
    monkeypatch.setenv("ALLOWED_ORIGINS", "*")
    import importlib
    import app.api.routes.health as health_module
    import app.main as main_module

    importlib.reload(health_module)
    importlib.reload(main_module)

    with TestClient(main_module.app) as client:
        yield client

    # Cleanup environment
    monkeypatch.delenv("MARKET_ONLY", raising=False)
    importlib.reload(health_module)
    importlib.reload(main_module)


def test_market_only_health_probes(market_only_client):
    # Live probe must succeed without Ollama
    live_res = market_only_client.get("/api/health/live")
    assert live_res.status_code == 200
    assert live_res.json()["status"] == "live"
    assert live_res.json()["mode"] == "market-only"

    # Ready probe must report ready without Ollama model warmup
    ready_res = market_only_client.get("/api/health/ready")
    assert ready_res.status_code == 200
    ready_data = ready_res.json()
    assert ready_data["ready"] is True
    assert ready_data["mode"] == "market-only"
    assert ready_data["database"] == "available"

    # Main diagnostic endpoint
    health_res = market_only_client.get("/api/health")
    assert health_res.status_code == 200
    health_data = health_res.json()
    assert health_data["status"] == "ready"
    assert health_data["ready"] is True
    assert health_data["mode"] == "market-only"
    assert "market_data" in health_data


def test_market_only_routes_and_cors(market_only_client):
    # Test CORS header
    res = market_only_client.get("/api/symbols/popular", headers={"Origin": "https://example.com"})
    assert res.status_code == 200
    assert "symbols" in res.json()
    assert len(res.json()["symbols"]) > 0
    assert res.headers.get("access-control-allow-origin") == "*"

    # Educational cloud preview messages on AI chat and documents
    chat_res = market_only_client.post("/api/chat", json={"message": "hello"})
    assert chat_res.status_code == 200
    assert "Market Cloud Preview" in chat_res.json()["response"]

    doc_res = market_only_client.get("/api/documents")
    assert doc_res.status_code == 200
    assert doc_res.json()["status"] == "market_cloud_preview"


def test_market_only_root_frontend(market_only_client):
    res = market_only_client.get("/")
    assert res.status_code == 200
    assert "<html" in res.text.lower()
