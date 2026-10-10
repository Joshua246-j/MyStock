import asyncio
import logging
from fastapi import APIRouter
from app.db.models import UserSettings
from app.db.database import SessionLocal
from app.ollama_client import OllamaClient
from app.rag.vector_store import get_vector_store
from app.rag.lexical_store import lexical_index_available
from app.dependencies import market_service
from app.config import EMBEDDING_MODEL

logger = logging.getLogger("stockrag")
ollama_client = OllamaClient()

router = APIRouter()

def _health_settings():
    with SessionLocal() as db:
        row = db.query(UserSettings).first()
        return row.settings if row and row.settings else {}

def _check_faiss():
    try:
        if not get_vector_store().health_check():
            return False
        return True
    except Exception:
        logger.exception("FAISS health check failed")
        return False

@router.get("/health")
async def health_check():
    settings = await asyncio.to_thread(_health_settings)
    model = settings.get("ai_model", ollama_client.model)
    timeout = max(1, int(settings.get("request_timeout", 30)))
    # One bounded catalog read gives consistent readiness for the selected chat
    # model and embeddings without a separate request for each model.
    try:
        model_catalog = await asyncio.wait_for(ollama_client.list_models(min(timeout, 4)), timeout=min(timeout, 5))
    except asyncio.TimeoutError:
        model_catalog = {"available": False, "models": [], "embedding_models": []}
    installed_models = model_catalog.get("models", [])
    embedding_models = model_catalog.get("embedding_models", [])
    model_ok = model_catalog.get("available") is True and any(name == model or name.startswith(model + ":") for name in installed_models)
    embedding_root = EMBEDDING_MODEL.split(":", 1)[0]
    embedding_ok = model_catalog.get("available") is True and any(name == EMBEDDING_MODEL or name.startswith(embedding_root + ":") for name in embedding_models)
    ollama_ok = model_catalog.get("available") is True
    faiss_call = asyncio.wait_for(asyncio.to_thread(_check_faiss), timeout=min(timeout, 3))
    lexical_call = asyncio.wait_for(asyncio.to_thread(lexical_index_available), timeout=min(timeout, 3))
    market_call = asyncio.wait_for(asyncio.to_thread(market_service.check_provider, "AAPL"), timeout=min(timeout, 3))
    checks = await asyncio.gather(faiss_call, lexical_call, market_call, return_exceptions=True)
    faiss_ok = checks[0] is True
    lexical_ok = checks[1] is True
    market_result = checks[2] if isinstance(checks[2], dict) else {}
    market_ok = bool(isinstance(market_result, dict) and market_result.get("success"))
    provider = market_result.get("source") if market_ok else None
    return {
        "application": "running",
        "ollama": "connected" if ollama_ok else "disconnected",
        "model": model,
        "model_available": model_ok,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_model_available": embedding_ok,
        "document_retrieval": "semantic" if faiss_ok and embedding_ok else "keyword" if lexical_ok else "unavailable",
        "semantic_document_retrieval": "available" if faiss_ok and embedding_ok else "unavailable",
        "keyword_document_retrieval": "available" if lexical_ok else "unavailable",
        "vector_database": "available" if faiss_ok else "unavailable",
        "vector_backend": "faiss-cpu",
        "market_data": {
            "status": "available" if market_ok else "unavailable",
            "provider": provider,
            "data_status": market_result.get("data_status", "UNVERIFIED_FRESHNESS") if market_ok else "UNAVAILABLE",
            "error": None if market_ok else market_result.get("error", "No configured market-data provider is reachable."),
        },
    }
