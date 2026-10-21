import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import market, documents, chat, settings, symbols, models, health, news, forecast, memory
from app.db.cache import clear_expired
from app.config import PROJECT_ROOT
from app.config import OLLAMA_MODEL
from app.analysis.orchestrator import ollama_client

from app.api.middlewares import request_logging_middleware
from app.api.exception_handlers import http_error_handler, validation_error_handler
from app.api.auth import BasicAuthMiddleware

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("stockrag")


@asynccontextmanager
async def lifespan(_: FastAPI):
    async def warm_local_model():
        try:
            def load_model_name():
                from app.db.database import SessionLocal
                from app.db.models import UserSettings
                with SessionLocal() as db:
                    row = db.query(UserSettings).first()
                    return (row.settings or {}).get("ai_model", OLLAMA_MODEL) if row else OLLAMA_MODEL
            model = await asyncio.to_thread(load_model_name)
            if not await ollama_client.has_model(model, timeout=4):
                logger.info("ollama_warmup_skipped", extra={"model": model, "reason": "model unavailable"})
                return
            await ollama_client.chat(
                [{"role":"system","content":"Respond with one short readiness word."},{"role":"user","content":"Ready"}],
                model,
                timeout=45,
                context_size=512,
                max_output_tokens=8,
            )
            logger.info("ollama_model_warmed", extra={"model": model})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
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
        rag_task.cancel()
        cleanup_task.cancel()
        warmup_task.cancel()
        await asyncio.gather(cleanup_task, warmup_task, rag_task, return_exceptions=True)

app = FastAPI(title="Stock Market Analysis AI", lifespan=lifespan)

app.add_middleware(BasicAuthMiddleware)
app.middleware("http")(request_logging_middleware)
app.add_exception_handler(StarletteHTTPException, http_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)

STATIC_DIR = PROJECT_ROOT / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(market.router, prefix="/api")
app.include_router(news.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(symbols.router, prefix="/api")
app.include_router(models.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(forecast.router, prefix="/api")
app.include_router(memory.router, prefix="/api")

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
