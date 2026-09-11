"""Cross-site request protection for cookie-authenticated, state-changing requests.

The session cookie is SameSite=Lax (so browsers don't send it on cross-site POSTs anyway);
this middleware adds a second layer: if a browser sends an Origin header on an unsafe method,
it must be same-origin or explicitly allowed.
"""

from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import get_settings

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def origin_allowed(origin: str, host: str | None) -> bool:
    origin = origin.rstrip("/")
    if origin in get_settings().allowed_origins:
        return True
    return bool(host) and urlsplit(origin).netloc == host


class OriginCheckMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] in UNSAFE_METHODS:
            headers = Headers(scope=scope)
            origin = headers.get("origin")
            if origin is not None and not origin_allowed(origin, headers.get("host")):
                response = JSONResponse(
                    {"error": {"code": "BAD_ORIGIN", "message": "Cross-site request blocked.", "details": None}},
                    status_code=403,
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
