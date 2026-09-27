"""Nghiệm thu Phase 0, mục API (validation.md)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from advertest_contracts.models import ErrorResponse, HealthResponse
from advertest_contracts.registry import SCHEMAS
from backend.app.main import create_app

from .conftest import env

PUBLIC_GROUPS = [
    "/auth", "/users", "/models", "/datasets", "/slices", "/attack-specs", "/protocols",
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
}
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


@pytest.mark.parametrize("group", [g for g in PUBLIC_GROUPS if g != "/health"])
def test_sample_endpoint_returns_501_with_uniform_error(
    openapi: dict[str, Any], repo: Path, group: str
) -> None:
    method, path, body = _sample_request(openapi, repo, group)
    response = TestClient(create_app()).request(method, path, json=body)
    assert response.status_code == 501
    body = ErrorResponse.model_validate(response.json())
    assert body.error.code == "not_implemented"


def test_worker_internal_endpoint_returns_501() -> None:
    response = TestClient(create_app()).post("/internal/worker/lease")
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
            elif path.startswith(("/verify", "/health")):
                assert used == set(), path
            else:
                assert used == {("apiKey", None, "cookie")}, path
