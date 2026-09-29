"""Kiểm tra lúc khởi động (validation.md Phase 4): app từ chối chạy nếu route không công khai
thiếu khai báo permission, hoặc x-permission lệch với dependency."""

from __future__ import annotations

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from advertest_contracts.permissions import Permission
from backend.app.auth.permissions import (
    check_route_permissions,
    guard,
    require_permission,
    route_permission_errors,
)
from backend.app.main import create_app


def test_real_app_declares_every_route() -> None:
    app = create_app()
    assert route_permission_errors(app) == []
    # Kiểm tra thật sự duyệt các route của router con (không phải danh sách rỗng).
    checked = {path for path in app.openapi()["paths"] if not path.startswith("/internal")}
    assert len(checked) >= 25


def test_route_without_permission_blocks_startup() -> None:
    app = create_app()
    extra = APIRouter()

    @extra.get("/khong-khai-bao")
    def undeclared() -> None: ...

    app.include_router(extra)
    with pytest.raises(RuntimeError, match="/khong-khai-bao"):
        check_route_permissions(app)
    with pytest.raises(RuntimeError, match="/khong-khai-bao"), TestClient(app):
        pass


def test_mismatched_x_permission_is_rejected() -> None:
    app = create_app()
    extra = APIRouter()

    @extra.get(
        "/lech",
        dependencies=[Depends(require_permission(Permission.AUDIT_READ))],
        openapi_extra={"x-permission": "model.read"},
    )
    def mismatched() -> None: ...

    app.include_router(extra)
    [error] = route_permission_errors(app)
    assert "/lech" in error and "model.read" in error


def test_declared_route_and_public_or_worker_routes_pass() -> None:
    app = create_app()
    extra = APIRouter()

    @extra.get("/co-khai-bao", **guard(Permission.MODEL_READ))
    def declared() -> None: ...

    @extra.get("/internal/worker/them")
    def worker_route() -> None: ...

    app.include_router(extra)
    check_route_permissions(app)
