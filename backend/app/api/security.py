"""Security scheme khai báo trong OpenAPI (Phase 0: chỉ khai báo, chưa xác thực thật).

- Người dùng: cookie phiên httpOnly `advertest_session`, phiên phía server (Phase 4 cài đặt).
- Worker (`/internal/worker`): bearer token của compute target (Phase 3 cài đặt).
"""

from __future__ import annotations

from fastapi.security import APIKeyCookie, HTTPBearer

SESSION_COOKIE = "advertest_session"

user_session = APIKeyCookie(
    name=SESSION_COOKIE,
    scheme_name="userSession",
    description="Cookie phiên của người dùng (token ngẫu nhiên, httpOnly; phiên lưu phía server).",
    auto_error=False,
)
worker_token = HTTPBearer(
    scheme_name="workerToken",
    description="Token của compute target, chỉ dùng cho /internal/worker.",
    auto_error=False,
)
