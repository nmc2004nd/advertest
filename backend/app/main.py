"""App FastAPI của AdverTest."""

from __future__ import annotations

import os
from importlib.metadata import version

from fastapi import FastAPI
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from backend.app.api import health, public, worker
from backend.app.api.errors import install_error_handlers
from backend.app.auth.csrf import CsrfMiddleware


def create_app() -> FastAPI:
    app = FastAPI(title="AdverTest API", version=version("advertest"))
    install_error_handlers(app)
    app.add_middleware(CsrfMiddleware)
    # IP của client chỉ lấy từ X-Forwarded-For khi kết nối đến từ proxy tin cậy
    # (requirements.md Phase 4). Đặt trong app (thay cờ --forwarded-allow-ips của uvicorn) để
    # test được; entrypoint chạy uvicorn với --no-proxy-headers. Middleware thêm sau cùng nằm
    # ngoài cùng, nên CSRF và route đều thấy IP đã xử lý.
    app.add_middleware(
        ProxyHeadersMiddleware, trusted_hosts=os.environ.get("TRUSTED_PROXIES", "127.0.0.1")
    )
    app.include_router(health.router)
    app.include_router(public.auth_public_router)
    app.include_router(public.router)
    app.include_router(public.verify_router)
    app.include_router(worker.router)
    return app


app = create_app()
