"""
Tenant middleware — Enforces tenant isolation.
Injects tenant_id from authenticated user.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastapi import HTTPException

# Paths that don't require tenant context
EXEMPT_PATHS = {
    "/", "/docs", "/redoc", "/openapi.json",
    "/api/auth/login", "/api/auth/register-institution",
    "/api/auth/me", "/api/auth/available-users",
}

EXEMPT_PREFIXES = ["/api/admin/tenants"]


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip tenant check for exempt paths
        if path in EXEMPT_PATHS or any(path.startswith(p) for p in EXEMPT_PREFIXES):
            return await call_next(request)

        # For OPTIONS (CORS preflight), pass through
        if request.method == "OPTIONS":
            return await call_next(request)

        # tenant_id will be set by security.get_current_user and used in routers
        return await call_next(request)


def get_tenant_id(user: dict) -> str | None:
    """
    Extract tenant_id from authenticated user.
    Super admin has no tenant_id (can access all).
    Everyone else MUST have a tenant_id.
    """
    tenant_id = user.get("tenant_id")
    if user.get("role") == "super_admin":
        return tenant_id  # can be None
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant context. User not assigned to an institution.")
    return tenant_id
