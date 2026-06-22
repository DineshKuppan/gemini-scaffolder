from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import re
import logging

logger = logging.getLogger("user-service")


class TenantMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        # Bypass for health and mcp tool listing
        if request.url.path.startswith("/health") or request.url.path.startswith("/mcp"):
            return await call_next(request)
        # Log headers for troubleshooting
        try:
            logger.info("Incoming headers: %s", dict(request.headers))
        except Exception:
            pass

        tenant = request.headers.get("x-tenant-id") or request.headers.get("X-Tenant-ID")
        if not tenant or not re.match(r"^[A-Za-z0-9_-]+$", tenant):
            raise HTTPException(status_code=400, detail="Missing or invalid X-Tenant-ID header")

        # Attach tenant to request state for downstream handlers
        request.state.tenant_id = tenant
        return await call_next(request)
