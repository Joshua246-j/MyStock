import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import market, documents, chat, settings
from app.db.database import engine, Base
from app.db.cache import clear_expired
from app.db.models import UserSettings
from app.db.database import SessionLocal
from app.market.service import market_service
from app.ollama_client import OllamaClient
from app.rag.vector_store import get_vector_store

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("stockrag")
ollama_client = OllamaClient()


def _initialize_database():
    Base.metadata.create_all(bind=engine)
    clear_expired()


def _health_settings():
    with SessionLocal() as db:
        row = db.query(UserSettings).first()
        return row.settings if row and row.settings else {}


def _check_chroma():
    try:
        get_vector_store()._collection.count()
        return True
    except Exception:
        logger.exception("Chroma health check failed")
        return False


@asynccontextmanager
async def lifespan(_: FastAPI):
    await asyncio.to_thread(_initialize_database)
    yield


app = FastAPI(title="Stock Market Analysis AI", lifespan=lifespan)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled request failure", extra={"request_id": request_id, "path": request.url.path})
        response = JSONResponse(status_code=500, content={"error": {"code": "internal_error", "message": "An internal error occurred."}})
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    logger.info("request_complete", extra={"request_id": request_id, "method": request.method, "path": request.url.path, "status_code": response.status_code, "latency_ms": latency_ms})
    return response


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_: Request, exc: StarletteHTTPException):
    detail = exc.detail
    message = detail if isinstance(detail, str) else "The request could not be completed."
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": f"http_{exc.status_code}", "message": message}}, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": {"code": "validation_error", "message": "The request contains invalid fields.", "details": exc.errors()}})

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(market.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(settings.router, prefix="/api")

@app.get("/")
def read_root():
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return {"message": "Stock Market Analysis AI is running. Use /api/chat to interact."}

@app.get("/api/health")
async def health_check():
    settings = await asyncio.to_thread(_health_settings)
    model = settings.get("ai_model", ollama_client.model)
    timeout = max(1, int(settings.get("request_timeout", 30)))
    try:
        ollama_ok = await asyncio.wait_for(asyncio.to_thread(ollama_client.check_health, min(timeout, 5)), timeout=min(timeout, 6))
    except asyncio.TimeoutError:
        ollama_ok = False
    try:
        model_ok = await asyncio.wait_for(asyncio.to_thread(ollama_client.has_model, model, min(timeout, 5)), timeout=min(timeout, 6)) if ollama_ok else False
    except asyncio.TimeoutError:
        model_ok = False
    chroma_call = asyncio.wait_for(asyncio.to_thread(_check_chroma), timeout=min(timeout, 10))
    market_call = asyncio.wait_for(asyncio.to_thread(market_service.get_quote, "AAPL"), timeout=timeout)
    checks = await asyncio.gather(chroma_call, market_call, return_exceptions=True)
    chroma_ok = checks[0] is True
    market_result = checks[1] if isinstance(checks[1], dict) else {}
    market_ok = bool(isinstance(market_result, dict) and market_result.get("success"))
    provider = market_result.get("source") if market_ok else None
    return {
        "application": "running",
        "ollama": "connected" if ollama_ok else "disconnected",
        "model": model,
        "model_available": model_ok,
        "vector_database": "available" if chroma_ok else "unavailable",
        "market_data": {"status": "available" if market_ok else "unavailable", "provider": provider},
    }
