"""Khung API: đủ nhóm endpoint, security scheme đúng, endpoint chưa làm trả 501."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app

PUBLIC_GROUPS = [
    "/auth", "/users", "/models", "/datasets", "/slices", "/attack-specs", "/protocols",
    "/experiments", "/runs", "/failure-cases", "/reviews", "/reports", "/compute-targets",
    "/budget", "/audit-log", "/verify",
]  # fmt: skip
WORKER_ENDPOINTS = {
    ("post", "/internal/worker/lease"),
    ("post", "/internal/worker/heartbeat"),
    ("post", "/internal/worker/runs/{run_id}/progress"),
    ("post", "/internal/worker/runs/{run_id}/artifact-url"),
    ("post", "/internal/worker/runs/{run_id}/complete"),
    ("post", "/internal/worker/experiments/{experiment_id}/search-result"),
}
RUN_ID = "00000000-0000-5000-8000-000000000001"
SAMPLE_CALLS = [
    ("post", "/auth/login"),
    ("get", "/users"),
    ("get", "/models"),
    ("get", "/datasets"),
    ("get", "/slices"),
    ("get", "/attack-specs"),
    ("get", "/failure-cases/" + RUN_ID),
    ("get", "/runs/" + RUN_ID),
    ("get", "/reviews"),
    ("get", "/reports/" + RUN_ID),
    ("get", "/compute-targets"),
    ("get", "/budget"),
    ("get", "/audit-log"),
    ("get", "/verify/" + RUN_ID),
    ("post", "/internal/worker/lease"),
    ("post", "/internal/worker/heartbeat"),
    ("post", "/internal/worker/runs/" + RUN_ID + "/artifact-url"),
]


@pytest.fixture(scope="module")
def openapi() -> dict[str, Any]:
    return create_app().openapi()


def test_every_public_group_has_an_endpoint(openapi: dict[str, Any]) -> None:
    paths = openapi["paths"]
    for group in PUBLIC_GROUPS:
        assert any(p == group or p.startswith(group + "/") for p in paths), group


def test_worker_endpoints(openapi: dict[str, Any]) -> None:
    declared = {
        (method, path)
        for path, ops in openapi["paths"].items()
        if path.startswith("/internal/worker")
        for method in ops
    }
    assert declared == WORKER_ENDPOINTS


def test_security_schemes(openapi: dict[str, Any]) -> None:
    schemes = openapi["components"]["securitySchemes"]
    assert schemes["userSession"] == {
        "type": "apiKey", "in": "cookie", "name": "advertest_session",
        "description": "Cookie phiên của người dùng (JWT, httpOnly).",
    }  # fmt: skip
    assert schemes["workerToken"]["type"] == "http"
    assert schemes["workerToken"]["scheme"] == "bearer"
    for path, ops in openapi["paths"].items():
        for op in ops.values():
            names = {name for req in op.get("security", []) for name in req}
            if path.startswith("/internal/worker"):
                assert names == {"workerToken"}, path
            elif path.startswith("/verify"):
                assert names == set(), path
            else:
                assert names == {"userSession"}, path


@pytest.mark.parametrize(("method", "path"), SAMPLE_CALLS)
def test_unimplemented_endpoints_return_501(method: str, path: str) -> None:
    response = TestClient(create_app()).request(method, path)
    assert response.status_code == 501
