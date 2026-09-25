import asyncio
import logging
import os
from contextlib import asynccontextmanager
from sqlalchemy import inspect, text

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import market, documents, chat, settings, symbols, models, health
from app.db.database import engine, Base
from app.db.cache import clear_expired
from app.config import PROJECT_ROOT

from app.api.middlewares import request_logging_middleware
from app.api.exception_handlers import http_error_handler, validation_error_handler

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("stockrag")

def _initialize_database():
    Base.metadata.create_all(bind=engine)
    document_columns = {column["name"] for column in inspect(engine).get_columns("documents")}
    if "storage_path" not in document_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE documents ADD COLUMN storage_path VARCHAR"))
    clear_expired()

@asynccontextmanager
async def lifespan(_: FastAPI):
    await asyncio.to_thread(_initialize_database)
    async def cache_cleanup_loop():
        while True:
            await asyncio.sleep(3600)
            try:
                removed = await asyncio.to_thread(clear_expired)
                logger.info("expired_cache_cleanup_complete", extra={"rows_removed": removed})
            except Exception:
                logger.exception("expired_cache_cleanup_failed")
    cleanup_task = asyncio.create_task(cache_cleanup_loop())
    try:
        yield
    finally:
        cleanup_task.cancel()
        await asyncio.gather(cleanup_task, return_exceptions=True)

app = FastAPI(title="Stock Market Analysis AI", lifespan=lifespan)

app.middleware("http")(request_logging_middleware)
app.add_exception_handler(StarletteHTTPException, http_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)

STATIC_DIR = PROJECT_ROOT / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(market.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(symbols.router, prefix="/api")
app.include_router(models.router, prefix="/api")
app.include_router(health.router, prefix="/api")

@app.get("/")
def read_root():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Stock Market Analysis AI is running. Use /api/chat to interact."}
