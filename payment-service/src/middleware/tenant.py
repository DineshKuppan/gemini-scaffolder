from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import re


class TenantMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health") or request.url.path.startswith("/mcp"):
            return await call_next(request)

        tenant = request.headers.get("x-tenant-id") or request.headers.get("X-Tenant-ID")
        if not tenant or not re.match(r"^[A-Za-z0-9_-]+$", tenant):
            raise HTTPException(status_code=400, detail="Missing or invalid X-Tenant-ID header")

        request.state.tenant_id = tenant
        return await call_next(request)
