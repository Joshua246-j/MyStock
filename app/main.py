import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import market, settings, symbols, health, news
from app.db.cache import clear_expired
from app.config import PROJECT_ROOT, OLLAMA_MODEL

from app.api.middlewares import request_logging_middleware
from app.api.exception_handlers import http_error_handler, validation_error_handler
from app.api.auth import BasicAuthMiddleware

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("stockrag")

MARKET_ONLY = os.getenv("MARKET_ONLY", "").lower() in ("1", "true", "yes") or os.getenv("APP_MODE", "").lower() == "market-only"

if not MARKET_ONLY:
    try:
        from app.api.routes import documents, chat, models, forecast, memory
        from app.analysis.orchestrator import ollama_client
    except ImportError:
        logger.warning("Local RAG/Ollama modules unavailable; automatically activating MARKET_ONLY mode.")
        MARKET_ONLY = True

# Fallback routers for market-only cloud deployments
if MARKET_ONLY:
    chat_router = APIRouter(prefix="/chat", tags=["AI Chat (Cloud Preview)"])
    @chat_router.get("")
    @chat_router.post("")
    async def chat_cloud_preview():
        return {
            "response": (
                "Market Cloud Preview: Interactive stock charts, real-time quotes, technical analytics, "
                "and financial news are fully active in this cloud deployment. "
                "Local AI synthesis and document RAG require the local Ollama LLM runtime "
                "(available in the local Docker or Kubernetes cluster deployment)."
            ),
            "status": "market_cloud_preview",
            "model": "cloud-preview"
        }

    docs_router = APIRouter(prefix="/documents", tags=["Data Hub (Cloud Preview)"])
    @docs_router.get("")
    async def docs_cloud_preview():
        return {"documents": [], "total": 0, "status": "market_cloud_preview", "message": "Document storage and RAG are available in the local deployment."}

    models_router = APIRouter(prefix="/models", tags=["Models (Cloud Preview)"])
    @models_router.get("")
    async def models_cloud_preview():
        return {"available": False, "models": [], "embedding_models": [], "status": "market_cloud_preview"}

    forecast_router = APIRouter(prefix="/forecast", tags=["Forecast (Cloud Preview)"])
    @forecast_router.get("/{symbol}")
    async def forecast_cloud_preview(symbol: str):
        return {"symbol": symbol, "status": "market_cloud_preview", "message": "Probabilistic ML forecasting engine runs in the local deployment."}


@asynccontextmanager
async def lifespan(_: FastAPI):
    warmup_task = None
    if not MARKET_ONLY:
        async def warm_local_model():
            health.set_chat_model_warming(True)
            try:
                def load_model_settings():
                    from app.db.database import SessionLocal
                    from app.db.models import UserSettings
                    with SessionLocal() as db:
                        row = db.query(UserSettings).first()
                        values = row.settings or {} if row else {}
                        return values.get("ai_model", OLLAMA_MODEL), int(values.get("context_size", 4096))
                model, context_size = await asyncio.to_thread(load_model_settings)
                if not await ollama_client.has_model(model, timeout=4):
                    health.set_chat_model_warming(False)
                    health.set_warmed_chat_model(None)
                    logger.info("ollama_warmup_skipped", extra={"model": model, "reason": "model unavailable"})
                    return
                await ollama_client.chat(
                    [{"role":"system","content":"Respond with one short readiness word."},{"role":"user","content":"Ready"}],
                    model,
                    # Cold CPU-only model loading can exceed 150 seconds on this
                    # hardware profile; allow a bounded load before aborting it.
                    timeout=300,
                    # Warm with the same context size regular chat uses so Ollama
                    # does not need to reload the model when the first user arrives.
                    context_size=context_size,
                    max_output_tokens=8,
                )
                health.set_warmed_chat_model(model)
                health.set_chat_model_warming(False)
                logger.info("ollama_model_warmed", extra={"model": model})
            except asyncio.CancelledError:
                health.set_chat_model_warming(False)
                raise
            except Exception as exc:
                health.set_warmed_chat_model(None)
                health.set_chat_model_warming(False)
                logger.info("ollama_warmup_failed", extra={"reason": str(exc)})

        warmup_task = asyncio.create_task(warm_local_model())

    async def cache_cleanup_loop():
        while True:
            await asyncio.sleep(3600)
            try:
                removed = await asyncio.to_thread(clear_expired)
                logger.info("expired_cache_cleanup_complete", extra={"rows_removed": removed})
            except Exception:
                logger.exception("expired_cache_cleanup_failed")
    cleanup_task = asyncio.create_task(cache_cleanup_loop())
    
    rag_task = None
    if not MARKET_ONLY:
        async def rag_cleanup_loop():
            while True:
                await asyncio.sleep(86400)  # once a day
                try:
                    from app.rag.lexical_store import clean_orphaned_chunks
                    removed = await asyncio.to_thread(clean_orphaned_chunks)
                    logger.info("rag_cleanup_complete", extra={"orphaned_chunks_removed": removed})
                except Exception:
                    logger.exception("rag_cleanup_failed")
                    
        rag_task = asyncio.create_task(rag_cleanup_loop())
    
    try:
        yield
    finally:
        active_tasks = [t for t in (rag_task, cleanup_task, warmup_task) if t is not None]
        for t in active_tasks:
            t.cancel()
        if active_tasks:
            await asyncio.gather(*active_tasks, return_exceptions=True)

app = FastAPI(title="Stock Market Analysis AI", lifespan=lifespan)

# CORS configuration for cloud hosting and external client access
cors_origins_env = os.getenv("ALLOWED_ORIGINS", "*")
origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],
    allow_credentials=origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(BasicAuthMiddleware)
app.middleware("http")(request_logging_middleware)
app.add_exception_handler(StarletteHTTPException, http_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)

STATIC_DIR = PROJECT_ROOT / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Core market and diagnostic endpoints (always enabled)
app.include_router(market.router, prefix="/api")
app.include_router(news.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(symbols.router, prefix="/api")
app.include_router(health.router, prefix="/api")

# Mode-specific endpoints
if not MARKET_ONLY:
    app.include_router(documents.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(models.router, prefix="/api")
    app.include_router(forecast.router, prefix="/api")
    app.include_router(memory.router, prefix="/api")
else:
    app.include_router(docs_router, prefix="/api")
    app.include_router(chat_router, prefix="/api")
    app.include_router(models_router, prefix="/api")
    app.include_router(forecast_router, prefix="/api")

@app.get("/")
def read_root():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Stock Market Analysis AI is running. Use /api/chat to interact."}


@app.get("/markets", include_in_schema=False)
@app.get("/news", include_in_schema=False)
@app.get("/watchlist", include_in_schema=False)
@app.get("/compare", include_in_schema=False)
@app.get("/ai", include_in_schema=False)
@app.get("/stock/{symbol}", include_in_schema=False)
def read_terminal_route(symbol: str | None = None):
    """Serve the terminal shell for bookmarkable first-party app pages."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Stock Market Analysis AI is running. Use /api/chat to interact."}
