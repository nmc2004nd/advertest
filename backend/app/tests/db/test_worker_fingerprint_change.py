"""End-to-end (worker thật + API thật): worker chết, môi trường đổi (GIT_COMMIT khác) rồi chạy
tiếp. Run đang chạy dở thành failed thay vì kẹt; các run còn lại chạy tiếp (review Group 4,
phát hiện 3). Postgres và MinIO thật (`make test-db`)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from advertest_contracts.enums import ExperimentStatus, RunStatus
from advertest_contracts.models import CostProfile
from advertest_worker.cache import JobCache
from advertest_worker.client import WorkerClient
from advertest_worker.job import BatchHook, JobRunner
from backend.app.db import models as m

from .test_worker_api import _runs, _setup, client
from .test_worker_services import FakeClock, World, _config, world

pytestmark = pytest.mark.db
__all__ = ["client", "world"]


class Crash(BaseException):
    """Mô phỏng worker chết đột ngột (kill -9)."""


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def _runner(
    api: TestClient, token: str, cache: Path, clock: FakeClock, on_batch: BatchHook | None
) -> JobRunner:
    return JobRunner(
        WorkerClient(api, token, sleep=lambda _s: None),
        JobCache(cache),
        "cpu",
        url_http=httpx.Client(timeout=60),
        heartbeat_interval_s=3600,
        clock=clock,
        on_batch=on_batch,
    )


def test_changed_environment_on_resume_fails_run_and_continues(
    client: TestClient, app_engine: Engine, world: World, clock: FakeClock, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    monkeypatch.setenv("GIT_COMMIT", "1" * 40)  # fingerprint riêng, không trúng cache test khác
    token, target_id, experiment_id = _setup(app_engine, world, clock)
    worker = WorkerClient(client, token, sleep=lambda _s: None)
    env = {"compute_target_id": str(target_id), "gpu_model": None, "cuda_version": None,
           "driver_version": None}  # fmt: skip
    for attack in _config(world).attacks:  # batch 1, bỏ qua calibration
        worker.cost_profile(
            CostProfile.model_validate(
                {
                    "compute_target_id": str(target_id),
                    "model_version_id": str(world.local.card.id),
                    "attack_spec_id": str(attack.attack_spec_id),
                    "sec_per_image": 0.01,
                    "peak_vram_mb": 0,
                    "batch_size": 1,
                    "measured_at": clock.now.isoformat(),
                    "environment": env,
                }
            )
        )

    def crash(_run_id: UUID, _ids: Sequence[str]) -> None:
        raise Crash

    def lease_and_run(cache: str, on_batch: BatchHook | None = None) -> None:
        lease = worker.lease()
        assert lease is not None and lease.experiment_id == experiment_id
        _runner(client, token, tmp_path / cache, clock, on_batch).run_lease(lease)

    with pytest.raises(Crash):
        lease_and_run("a", crash)
    monkeypatch.setenv("GIT_COMMIT", "2" * 40)  # code đã đổi trước khi chạy tiếp
    clock.advance(61)
    lease_and_run("b")  # start trả 409: worker bỏ job
    runs = _runs(app_engine, experiment_id)
    assert runs[0].status == RunStatus.FAILED
    assert all(r.status == RunStatus.QUEUED for r in runs[1:])

    clock.advance(61)  # lease của lần trước hết hạn
    lease_and_run("c")
    runs = _runs(app_engine, experiment_id)
    assert [r.status for r in runs] == [RunStatus.FAILED, RunStatus.COMPLETED, RunStatus.COMPLETED]
    with Session(app_engine) as session:
        assert session.get_one(m.Experiment, experiment_id).status == ExperimentStatus.COMPLETED
