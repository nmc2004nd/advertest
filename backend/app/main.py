"""App FastAPI của AdverTest."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from backend.app.api import health, public, worker
from backend.app.api.deps import get_sessionmaker
from backend.app.api.errors import install_error_handlers
from backend.app.auth.csrf import CsrfMiddleware
from backend.app.auth.permissions import check_route_permissions
from backend.app.reports import service as report_service
from backend.app.services import notifications

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Kiểm tra lại lúc khởi động: bắt cả route được thêm sau create_app().
    check_route_permissions(app)
    # Phase 8: report kẹt ở `generating` (tác vụ nền bị ngắt khi API dừng) được sinh tiếp, chạy
    # ở thread riêng để không chặn khởi động. Chỉ khi đã cấu hình MinIO.
    resume = (
        asyncio.create_task(asyncio.to_thread(_resume_reports))
        if os.environ.get("MINIO_ENDPOINT")
        else None
    )
    try:
        async with _email_delivery():
            yield
    finally:
        if resume is not None:
            await resume


def _resume_reports() -> None:
    try:
        count = report_service.resume_generating(get_sessionmaker(), public.get_report_stores())
    except Exception:  # khởi động không được hỏng vì DB hay MinIO tạm lỗi; chỉ ghi log
        logger.exception("Không sinh tiếp được report đang generating")
        return
    if count:
        logger.info("Đã sinh tiếp %d report đang generating", count)


@asynccontextmanager
async def _email_delivery() -> AsyncIterator[None]:
    # Phase 5: gửi email từ outbox khi đã cấu hình SMTP; chưa cấu hình thì email nằm chờ.
    smtp = notifications.SmtpConfig.from_env()
    if smtp is None:
        yield
        return
    stop = asyncio.Event()
    task = asyncio.create_task(
        notifications.delivery_loop(get_sessionmaker(), notifications.smtp_sender(smtp), stop)
    )
    try:
        yield
    finally:
        stop.set()
        await task


def create_app() -> FastAPI:
    app = FastAPI(title="AdverTest API", version=version("advertest"), lifespan=lifespan)
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
    # Route không công khai thiếu khai báo permission → không tạo được app (Phase 4).
    check_route_permissions(app)
    return app


app = create_app()
