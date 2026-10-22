import asyncio

import pytest

from app import ollama_client
from app.ollama_client import OllamaClient


@pytest.fixture(autouse=True)
def clear_model_catalog_cache():
    ollama_client._MODEL_CATALOG_CACHE.clear()
    ollama_client._MODEL_CATALOG_PENDING.clear()
    yield
    ollama_client._MODEL_CATALOG_CACHE.clear()
    ollama_client._MODEL_CATALOG_PENDING.clear()


def test_model_catalog_cache_is_scoped_to_ollama_url(monkeypatch):
    calls = []

    async def fetch(self, _timeout):
        calls.append(self.base_url)
        return {"available": True, "models": [self.base_url], "embedding_models": []}

    monkeypatch.setattr(OllamaClient, "_fetch_model_catalog", fetch)
    first = OllamaClient()
    second = OllamaClient()
    first.base_url = "http://ollama-a:11434"
    second.base_url = "http://ollama-b:11434"

    async def run():
        return await asyncio.gather(first.list_models(), second.list_models())

    results = asyncio.run(run())
    assert results[0]["models"] == ["http://ollama-a:11434"]
    assert results[1]["models"] == ["http://ollama-b:11434"]
    assert calls == ["http://ollama-a:11434", "http://ollama-b:11434"]


def test_cancelled_catalog_waiter_does_not_cancel_shared_fetch(monkeypatch):
    started = asyncio.Event()
    finish = asyncio.Event()
    calls = 0

    async def fetch(_self, _timeout):
        nonlocal calls
        calls += 1
        started.set()
        await finish.wait()
        return {"available": True, "models": ["qwen2.5:1.5b"], "embedding_models": []}

    monkeypatch.setattr(OllamaClient, "_fetch_model_catalog", fetch)

    async def run():
        client = OllamaClient()
        cancelled_waiter = asyncio.create_task(client.list_models())
        await started.wait()
        surviving_waiter = asyncio.create_task(client.list_models())
        cancelled_waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled_waiter
        finish.set()
        return await surviving_waiter

    result = asyncio.run(run())
    assert result["models"] == ["qwen2.5:1.5b"]
    assert calls == 1
