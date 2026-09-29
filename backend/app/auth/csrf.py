"""CSRF kiểu double-submit (requirements.md Phase 4, mục Phiên và bảo mật).

Request thay đổi dữ liệu (`POST`, `PUT`, `PATCH`, `DELETE`) có cookie phiên phải gửi header
`X-CSRF-Token` trùng cookie `csrf_token`, nếu không → `403 csrf_failed`. Request không có cookie
phiên (đăng nhập, yêu cầu truy cập) và API worker (bearer token) không áp dụng.
"""

from __future__ import annotations

import hmac

from fastapi import status
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from advertest_contracts.enums import ErrorCode
from backend.app.api.errors import error_response
from backend.app.api.security import SESSION_COOKIE
from backend.app.auth.sessions import CSRF_COOKIE, CSRF_HEADER

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
EXEMPT_PREFIX = "/internal/worker"


def csrf_ok(request: Request) -> bool:
    if request.method not in UNSAFE_METHODS or request.url.path.startswith(EXEMPT_PREFIX):
        return True
    if not request.cookies.get(SESSION_COOKIE):
        return True
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get(CSRF_HEADER, "")
    return bool(cookie) and hmac.compare_digest(cookie.encode(), header.encode())


class CsrfMiddleware:
    """Middleware ASGI thuần: chỉ đọc header và cookie, không đọc body."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and not csrf_ok(Request(scope)):
            response = error_response(
                status.HTTP_403_FORBIDDEN, ErrorCode.CSRF_FAILED, "Thiếu hoặc sai CSRF token"
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
