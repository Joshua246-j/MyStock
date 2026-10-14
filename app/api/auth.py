import os
import secrets
import base64
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

class BasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if os.getenv("AUTH_ENABLED", "false").lower() != "true":
            return await call_next(request)

        # Allow health checks without auth so monitoring works
        if request.url.path.startswith("/api/health"):
            return await call_next(request)
            
        auth_header = request.headers.get("Authorization")
        # Default to admin/admin if not configured in environment
        expected_user = os.getenv("AUTH_USERNAME", "admin")
        expected_pass = os.getenv("AUTH_PASSWORD", "admin")
        
        if auth_header and auth_header.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
                username, password = decoded.split(":", 1)
                
                # Use secrets.compare_digest to prevent timing attacks
                is_valid_user = secrets.compare_digest(username, expected_user)
                is_valid_pass = secrets.compare_digest(password, expected_pass)
                
                if is_valid_user and is_valid_pass:
                    return await call_next(request)
            except Exception:
                pass
                
        # Ask the browser to prompt for credentials
        return JSONResponse(
            status_code=401,
            content={"detail": "Unauthorized"},
            headers={"WWW-Authenticate": 'Basic realm="Secure Area"'},
        )
