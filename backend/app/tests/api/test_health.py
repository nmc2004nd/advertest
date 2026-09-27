"""GET /health: luôn 200, status khớp dependency, git commit hợp lệ."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from advertest_contracts.models import DependencyStatus, HealthResponse
from backend.app.api import health
from backend.app.main import create_app


@dataclass(frozen=True)
class FakeChecks:
    postgres_ok: bool
    minio_ok: bool

    def postgres(self) -> DependencyStatus:
        return DependencyStatus(ok=self.postgres_ok, detail=None if self.postgres_ok else "down")

    def minio(self) -> DependencyStatus:
        return DependencyStatus(ok=self.minio_ok, detail=None if self.minio_ok else "down")


@pytest.fixture(autouse=True)
def _fresh_git_commit() -> Iterator[None]:
    health.git_commit.cache_clear()
    yield
    health.git_commit.cache_clear()


def _get(checks: FakeChecks) -> HealthResponse:
    app = create_app()
    app.dependency_overrides[health.get_checks] = lambda: checks
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    return HealthResponse.model_validate(response.json())


def test_all_ok() -> None:
    body = _get(FakeChecks(postgres_ok=True, minio_ok=True))
    assert body.status == "ok"
    assert body.version == "0.0.0"


@pytest.mark.parametrize(("pg", "minio"), [(False, True), (True, False), (False, False)])
def test_degraded_still_returns_200(pg: bool, minio: bool) -> None:
    body = _get(FakeChecks(postgres_ok=pg, minio_ok=minio))
    assert body.status == "degraded"
    assert body.postgres.ok is pg
    assert body.minio.ok is minio


def test_git_commit_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_COMMIT", "A" * 40)
    assert _get(FakeChecks(True, True)).git_commit == "a" * 40


def test_git_commit_falls_back_to_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_COMMIT", "not-a-sha")
    commit = _get(FakeChecks(True, True)).git_commit
    assert commit == "unknown" or len(commit) == 40


def test_live_checks_report_missing_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("MINIO_ENDPOINT", raising=False)
    checks = health.LiveChecks()
    assert checks.postgres() == DependencyStatus(ok=False, detail="Thiếu DATABASE_URL")
    assert checks.minio() == DependencyStatus(ok=False, detail="Thiếu MINIO_ENDPOINT")


def test_live_checks_report_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    # Cổng 1 trên localhost không có dịch vụ: kết nối bị từ chối ngay.
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x:y@127.0.0.1:1/x")
    monkeypatch.setenv("MINIO_ENDPOINT", "http://127.0.0.1:1")
    checks = health.LiveChecks()
    assert checks.postgres().ok is False
    assert checks.minio().ok is False
