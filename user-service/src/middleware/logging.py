import time
import logging
import json
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("user-service")


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Unhandled exception during request")
            raise
        duration = (time.time() - start) * 1000
        tenant = getattr(request.state, "tenant_id", None)
        payload = {
            "ts": time.time(),
            "service": "user-service",
            "method": request.method,
            "path": request.url.path,
            "status_code": getattr(response, "status_code", None),
            "duration_ms": round(duration, 2),
            "tenant": tenant,
        }
        logger.info("HTTP Request", extra=payload)
        return response
