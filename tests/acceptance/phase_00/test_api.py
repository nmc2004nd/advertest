"""Nghiệm thu Phase 0, mục API (validation.md)."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from advertest_contracts.enums import Role, UserStatus
from advertest_contracts.models import ErrorResponse, HealthResponse
from advertest_contracts.registry import SCHEMAS
from backend.app.api.deps import get_sessionmaker
from backend.app.auth.passwords import hash_password
from backend.app.db import models as m
from backend.app.main import create_app

from .conftest import env

# Phase 4: "/users" (khung Phase 0) thay bằng "/admin" (/admin/users/*).
PUBLIC_GROUPS = [
    "/auth", "/admin", "/models", "/datasets", "/slices", "/attack-specs", "/protocols",
    "/experiments", "/runs", "/failure-cases", "/reviews", "/reports", "/compute-targets",
    "/budget", "/audit-log", "/verify", "/health",
]  # fmt: skip
WORKER_ENDPOINTS = {
    "/internal/worker/lease",
    "/internal/worker/heartbeat",
    "/internal/worker/runs/{run_id}/progress",
    "/internal/worker/runs/{run_id}/artifact-url",
    "/internal/worker/runs/{run_id}/complete",
    "/internal/worker/experiments/{experiment_id}/search-result",
    # Phase 3 (requirements.md, bảng API nội bộ cho worker).
    "/internal/worker/experiments/{experiment_id}/bundle",
    "/internal/worker/runs/{run_id}/start",
    "/internal/worker/cost-profiles",
    # Phase 6: dừng sớm, đăng ký patch.
    "/internal/worker/runs/{run_id}/skip",
    "/internal/worker/runs/{run_id}/patch",
    # Phase 7: tạo run động của tìm ngưỡng.
    "/internal/worker/experiments/{experiment_id}/runs",
}
# Nhóm Phase 4 cài đặt thật: không còn là khung trả 501.
# Phase 5 Group 1: API đọc tài nguyên (plan.md task 5b). /protocols: GET đã cài đặt, POST vẫn là
# khung tới Phase 8 (test backend `test_skeleton.py` kiểm tra POST /protocols trả 501).
# Phase 5 Group 2: experiment, run, failure case (plan.md task 5b).
IMPLEMENTED_GROUPS = {
    "/health", "/auth", "/admin", "/audit-log",
    "/models", "/datasets", "/slices", "/attack-specs", "/protocols", "/compute-targets",
    "/experiments", "/runs", "/failure-cases",
}  # fmt: skip
# Endpoint công khai, không cần phiên (requirements.md Phase 4, mục Bảo vệ endpoint).
PUBLIC_PATHS = ("/health", "/verify", "/auth/request-access", "/auth/login", "/auth/password-reset")
SAMPLE_ID = "00000000-0000-5000-8000-000000000001"


@pytest.fixture(scope="module")
def openapi(repo: Path) -> dict[str, Any]:
    """OpenAPI đã commit (contracts/openapi.json), không phải bản sinh lúc chạy test."""
    return json.loads((repo / "contracts" / "openapi.json").read_text())


def _sample_request(
    openapi: dict[str, Any], repo: Path, group: str
) -> tuple[str, str, dict[str, Any] | None]:
    """Endpoint đầu tiên của nhóm, với ID mẫu và body hợp lệ lấy từ contracts/mocks (nếu cần)."""
    for path, ops in sorted(openapi["paths"].items()):
        if path == group or path.startswith(group + "/"):
            method, op = next(iter(ops.items()))
            body = None
            if "requestBody" in op:
                ref = op["requestBody"]["content"]["application/json"]["schema"]["$ref"]
                # FastAPI tách schema dùng cả hai chiều thành "<Tên>-Input" / "<Tên>-Output".
                schema_name = re.sub(r"-(Input|Output)$", "", ref.rsplit("/", 1)[-1])
                mock_dir = next(d for d, model in SCHEMAS.items() if model.__name__ == schema_name)
                mock = sorted((repo / "contracts" / "mocks" / mock_dir).glob("*.json"))[0]
                body = json.loads(mock.read_text())
            return method, re.sub(r"\{[^}]+\}", SAMPLE_ID, path), body
    raise AssertionError(f"Không có endpoint cho nhóm {group}")


@pytest.mark.db
def test_health_reports_version_commit_and_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", env("ADVERTEST_TEST_APP_URL"))
    monkeypatch.setenv("MINIO_ENDPOINT", env("ADVERTEST_TEST_MINIO_ENDPOINT"))
    monkeypatch.setenv("MINIO_ACCESS_KEY", env("ADVERTEST_TEST_MINIO_ACCESS_KEY"))
    monkeypatch.setenv("MINIO_SECRET_KEY", env("ADVERTEST_TEST_MINIO_SECRET_KEY"))
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 200
    body = HealthResponse.model_validate(response.json())
    assert body.version
    assert body.git_commit
    assert body.postgres.ok is True
    assert body.minio.ok is True
    assert body.status == "ok"


SKELETON_GROUPS = [g for g in PUBLIC_GROUPS if g not in IMPLEMENTED_GROUPS]


@pytest.mark.parametrize("group", SKELETON_GROUPS)
def test_sample_endpoint_without_session(openapi: dict[str, Any], repo: Path, group: str) -> None:
    """Không có phiên: endpoint công khai còn là khung trả 501; endpoint cần phiên trả 401 trước
    501 (Phase 4, requirements.md mục Bảo vệ endpoint). Body lỗi luôn là ErrorResponse."""
    method, path, body = _sample_request(openapi, repo, group)
    response = TestClient(create_app()).request(method, path, json=body)
    error = ErrorResponse.model_validate(response.json()).error
    if path.startswith(PUBLIC_PATHS):
        assert (response.status_code, error.code) == (501, "not_implemented")
    else:
        assert (response.status_code, error.code) == (401, "unauthenticated")


@pytest.mark.db
def test_sample_endpoint_returns_501_with_session(
    openapi: dict[str, Any], repo: Path, app_engine: Engine, owner_engine: Engine
) -> None:
    """Với phiên thật của người dùng đủ 3 role: mọi nhóm còn là khung trả 501 thống nhất
    (Phase 4 Group 7 siết lại test chuyển tiếp của Group 0, plan.md task 34)."""
    email = f"phase00-{uuid.uuid4().hex[:8]}@x.test"
    with Session(owner_engine) as session, session.begin():
        user = m.User(
            email=email,
            full_name="Đủ role",
            password_hash=hash_password("mat-khau-phase-00"),
            status=UserStatus.ACTIVE,
        )
        session.add(user)
        session.flush()
        session.add_all(m.UserRole(user_id=user.id, role=role) for role in Role)
    app = create_app()
    factory = sessionmaker(app_engine)
    app.dependency_overrides[get_sessionmaker] = lambda: factory
    client = TestClient(app)
    login = client.post("/auth/login", json={"email": email, "password": "mat-khau-phase-00"})
    assert login.status_code == 200
    headers = {"X-CSRF-Token": client.cookies["csrf_token"]}
    for group in SKELETON_GROUPS:
        method, path, body = _sample_request(openapi, repo, group)
        response = client.request(method, path, json=body, headers=headers)
        error = ErrorResponse.model_validate(response.json()).error
        assert (response.status_code, error.code) == (501, "not_implemented"), group


def test_worker_internal_endpoint_returns_501(repo: Path) -> None:
    # Phase 3 cài đặt các endpoint worker khác; search-result vẫn là khung tới Phase 7 (Phase 7:
    # body là SearchResultReport).
    body = json.loads(
        next((repo / "contracts" / "mocks" / "search_result_report").glob("*.json")).read_text()
    )
    response = TestClient(create_app()).post(
        f"/internal/worker/experiments/{SAMPLE_ID}/search-result", json=body
    )
    assert response.status_code == 501
    assert ErrorResponse.model_validate(response.json()).error.code == "not_implemented"


def test_openapi_contains_every_group_and_worker_endpoint(openapi: dict[str, Any]) -> None:
    paths = set(openapi["paths"])
    for group in PUBLIC_GROUPS:
        assert any(p == group or p.startswith(group + "/") for p in paths), group
    assert {p for p in paths if p.startswith("/internal/worker")} == WORKER_ENDPOINTS


def test_security_schemes(openapi: dict[str, Any]) -> None:
    schemes = openapi["components"]["securitySchemes"]
    by_type = {name: (s["type"], s.get("scheme"), s.get("in")) for name, s in schemes.items()}
    for path, ops in openapi["paths"].items():
        for op in ops.values():
            used = {by_type[name] for req in op.get("security", []) for name in req}
            if path.startswith("/internal/worker"):
                assert used == {("http", "bearer", None)}, path
            elif path.startswith(PUBLIC_PATHS):
                assert used == set(), path
            else:
                assert used == {("apiKey", None, "cookie")}, path
