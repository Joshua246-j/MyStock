from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

async def http_error_handler(_: Request, exc: StarletteHTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and isinstance(detail.get("message"), str):
        error = {"code": str(detail.get("code") or f"http_{exc.status_code}"), "message": detail["message"]}
    else:
        message = detail if isinstance(detail, str) else "The request could not be completed."
        error = {"code": f"http_{exc.status_code}", "message": message}
    return JSONResponse(status_code=exc.status_code, content={"error": error}, headers=exc.headers)

async def validation_error_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": {"code": "validation_error", "message": "The request contains invalid fields.", "details": exc.errors()}})
