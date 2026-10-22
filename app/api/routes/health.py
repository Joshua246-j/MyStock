import asyncio
import logging
from fastapi import APIRouter, Response
from sqlalchemy import text
from app.db.models import UserSettings
from app.db.database import SessionLocal, engine
from app.ollama_client import OllamaClient
from app.rag.vector_store import get_vector_store
from app.rag.lexical_store import lexical_index_available
from app.dependencies import market_service
from app.config import EMBEDDING_MODEL

logger = logging.getLogger("stockrag")
ollama_client = OllamaClient()

router = APIRouter()
_warmed_chat_model: str | None = None
_chat_model_warming = False
_readiness_warmup_lock = asyncio.Lock()


def set_warmed_chat_model(model: str | None) -> None:
    """Record only a model that completed a real, non-empty generation request."""
    global _warmed_chat_model
    _warmed_chat_model = model


def set_chat_model_warming(warming: bool) -> None:
    global _chat_model_warming
    _chat_model_warming = warming

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
async def health_check(include_external: bool = True):
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
    def _check_web():
        import socket
        try:
            socket.gethostbyname("news.google.com")
            return True
        except Exception:
            return False

    if include_external:
        market_call = asyncio.wait_for(asyncio.to_thread(market_service.check_provider, "AAPL"), timeout=min(timeout, 3))
        web_call = asyncio.wait_for(asyncio.to_thread(_check_web), timeout=min(timeout, 2))
        checks = await asyncio.gather(faiss_call, lexical_call, market_call, web_call, return_exceptions=True)
    else:
        checks = await asyncio.gather(faiss_call, lexical_call, return_exceptions=True)
    faiss_ok = checks[0] is True
    lexical_ok = checks[1] is True
    market_result = checks[2] if include_external and isinstance(checks[2], dict) else {}
    market_ok = bool(isinstance(market_result, dict) and market_result.get("success"))
    provider = market_result.get("source") if market_ok else None
    web_ok = checks[3] is True if include_external else False
    
    docs_count, chunks_count = 0, 0
    try:
        from app.db.models import DocumentMetadata
        with SessionLocal() as db:
            docs_count = db.query(DocumentMetadata).filter(DocumentMetadata.status == "completed").count()
        from sqlalchemy import text as _text
        with engine.connect() as conn:
            chunks_count = conn.execute(_text("SELECT count(*) FROM rag_chunks")).scalar() or 0
    except Exception:
        pass

    database_ok = False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        database_ok = True
    except Exception:
        logger.exception("database_health_check_failed")

    chat_warmed = _warmed_chat_model == model
    retrieval_ok = bool(faiss_ok or lexical_ok)
    ready = bool(database_ok and model_ok and embedding_ok and chat_warmed and retrieval_ok)
    return {
        "application": "running" if ready else "degraded",
        "status": "ready" if ready else "not_ready",
        "ready": ready,
        "chat_model_warmed": chat_warmed,
        "database": "available" if database_ok else "unavailable",
        "ollama": "connected" if ollama_ok else "disconnected",
        "model": model,
        "context_size": int(settings.get("context_size", 4096)),
        "database_stats": {"documents": docs_count, "chunks": chunks_count},
        "model_available": model_ok,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_model_available": embedding_ok,
        "document_retrieval": "semantic" if faiss_ok and embedding_ok else "keyword" if lexical_ok else "unavailable",
        "semantic_document_retrieval": "available" if faiss_ok and embedding_ok else "unavailable",
        "keyword_document_retrieval": "available" if lexical_ok else "unavailable",
        "vector_database": "available" if faiss_ok else "unavailable",
        "vector_backend": "faiss-cpu",
        "web_search": {
            "status": "available" if web_ok else "unavailable" if include_external else "not_checked",
            "service": "Google News RSS & Allowed Publishers",
        },
        "market_data": {
            "status": "available" if market_ok else "unavailable" if include_external else "not_checked",
            "provider": provider,
            "data_status": market_result.get("data_status", "UNVERIFIED_FRESHNESS") if market_ok else "UNAVAILABLE",
            "error": None if market_ok else market_result.get("error", "Provider connectivity is not checked by the readiness probe." if not include_external else "No configured market-data provider is reachable."),
        },
    }


@router.get("/health/live")
async def liveness_check():
    """Cheap process check for restart policies; does not imply dependencies are ready."""
    return {"application": "running", "status": "live"}


@router.get("/health/ready")
async def readiness_check(response: Response):
    """Report ready only when the configured chatbot model, embedding model, and DB respond."""
    details = await health_check(include_external=False)
    if details.get("model_available") and not details.get("chat_model_warmed"):
        # Serialize fallback warmups so simultaneous health probes cannot
        # start competing model generations on memory-constrained machines.
        async with _readiness_warmup_lock:
            details = await health_check(include_external=False)
            if details.get("model_available") and not details.get("chat_model_warmed"):
                # Let the application startup warmup finish before attempting
                # the fallback generation. It uses the same context size.
                for _ in range(1200):
                    if not _chat_model_warming:
                        break
                    await asyncio.sleep(0.25)
                details = await health_check(include_external=False)
            if details.get("model_available") and not details.get("chat_model_warmed"):
                set_chat_model_warming(True)
                try:
                    answer = await ollama_client.chat(
                        [{"role": "system", "content": "Respond with one short readiness word."},
                         {"role": "user", "content": "Ready"}],
                        details["model"], timeout=300, context_size=details.get("context_size", 4096), max_output_tokens=8,
                    )
                    if not isinstance(answer, str) or not answer.strip():
                        raise RuntimeError("Model returned an empty readiness response")
                    set_warmed_chat_model(details["model"])
                    details = await health_check(include_external=False)
                except Exception:
                    set_warmed_chat_model(None)
                    logger.exception("readiness_model_warmup_failed")
                finally:
                    set_chat_model_warming(False)
    if not details["ready"]:
        response.status_code = 503
    return details
