import time
import uuid
import logging
from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("stockrag")

async def request_logging_middleware(request: Request, call_next):
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
