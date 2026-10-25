import asyncio
import logging
from fastapi import APIRouter, Response
from sqlalchemy import text
from app.db.models import UserSettings
from app.db.database import SessionLocal, engine
from app.ollama_client import OllamaClient
import os

try:
    from app.rag.vector_store import get_vector_store
except ImportError:
    get_vector_store = None

try:
    from app.rag.lexical_store import lexical_index_available
except ImportError:
    lexical_index_available = None

from app.dependencies import market_service
from app.config import EMBEDDING_MODEL

logger = logging.getLogger("stockrag")
ollama_client = OllamaClient()

router = APIRouter()
_warmed_chat_model: str | None = None
_chat_model_warming = False
_readiness_warmup_lock = asyncio.Lock()

MARKET_ONLY = os.getenv("MARKET_ONLY", "").lower() in ("1", "true", "yes") or os.getenv("APP_MODE", "").lower() == "market-only"


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
    if MARKET_ONLY or get_vector_store is None:
        return True
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
    timeout = max(1, int(settings.get("request_timeout", 30)))

    if MARKET_ONLY:
        def _check_web():
            import socket
            try:
                socket.gethostbyname("news.google.com")
                return True
            except Exception:
                return False

        database_ok = False
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            database_ok = True
        except Exception:
            logger.exception("database_health_check_failed")

        market_result = {}
        market_ok = True
        provider = "Yahoo Finance / Stooq"
        if include_external:
            try:
                market_result = await asyncio.wait_for(asyncio.to_thread(market_service.check_provider, "AAPL"), timeout=min(timeout, 4))
                market_ok = bool(isinstance(market_result, dict) and market_result.get("success"))
                if market_ok:
                    provider = market_result.get("source", provider)
            except Exception:
                market_ok = False

        web_ok = await asyncio.to_thread(_check_web) if include_external else False
        ready = bool(database_ok and (market_ok or not include_external))

        return {
            "application": "running" if ready else "degraded",
            "status": "ready" if ready else "not_ready",
            "ready": ready,
            "mode": "market-only",
            "cloud_preview": True,
            "database": "available" if database_ok else "unavailable",
            "ollama": "not_applicable",
            "model": "cloud-market-preview",
            "context_size": int(settings.get("context_size", 4096)),
            "database_stats": {"documents": 0, "chunks": 0},
            "model_available": True,
            "embedding_model": "not_applicable",
            "embedding_model_available": True,
            "document_retrieval": "market_only",
            "semantic_document_retrieval": "not_applicable",
            "keyword_document_retrieval": "not_applicable",
            "vector_database": "not_applicable",
            "vector_backend": "none",
            "web_search": {
                "status": "available" if web_ok else "unavailable" if include_external else "not_checked",
                "service": "Google News RSS & Allowed Publishers",
            },
            "market_data": {
                "status": "available" if market_ok else "unavailable" if include_external else "not_checked",
                "provider": provider,
                "data_status": market_result.get("data_status", "PROVIDER_CLOSE") if market_ok else "UNAVAILABLE",
                "error": None if market_ok else market_result.get("error", "No configured market-data provider is reachable."),
            },
        }

    model = settings.get("ai_model", ollama_client.model)
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
    lexical_fn = lexical_index_available if lexical_index_available is not None else (lambda: False)
    lexical_call = asyncio.wait_for(asyncio.to_thread(lexical_fn), timeout=min(timeout, 3))
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

    chat_generation_verified = _warmed_chat_model == model
    try:
        running_catalog = await asyncio.wait_for(
            ollama_client.list_running_models(min(timeout, 2)), timeout=min(timeout, 3)
        )
    except asyncio.TimeoutError:
        running_catalog = {"available": False, "models": []}
    running_models = running_catalog.get("models", [])
    chat_model_loaded = running_catalog.get("available") is True and any(
        name == model or name.startswith(model + ":") for name in running_models
    )
    chat_warmed = chat_generation_verified and chat_model_loaded
    retrieval_ok = bool(faiss_ok or lexical_ok)
    # Ollama unloads idle models to release RAM. A model proven during this
    # process remains ready to load on demand; report runner residency separately.
    ready = bool(database_ok and model_ok and embedding_ok and chat_generation_verified and retrieval_ok)
    return {
        "application": "running" if ready else "degraded",
        "status": "ready" if ready else "not_ready",
        "ready": ready,
        "chat_model_warmed": chat_warmed,
        "chat_model_loaded": chat_model_loaded,
        "chat_model_generation_verified": chat_generation_verified,
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
    return {"application": "running", "status": "live", "mode": "market-only" if MARKET_ONLY else "full"}


@router.get("/health/ready")
async def readiness_check(response: Response):
    """Report ready only when core dependencies respond."""
    if MARKET_ONLY:
        details = await health_check(include_external=False)
        if not details["ready"]:
            response.status_code = 503
        return details

    details = await health_check(include_external=False)
    if details.get("model_available") and not details.get("chat_model_generation_verified"):
        # Serialize fallback warmups so simultaneous health probes cannot
        # start competing model generations on memory-constrained machines.
        async with _readiness_warmup_lock:
            details = await health_check(include_external=False)
            if details.get("model_available") and not details.get("chat_model_generation_verified"):
                # Let the application startup warmup finish before attempting
                # the fallback generation. It uses the same context size.
                for _ in range(1200):
                    if not _chat_model_warming:
                        break
                    await asyncio.sleep(0.25)
                details = await health_check(include_external=False)
            if details.get("model_available") and not details.get("chat_model_generation_verified"):
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
