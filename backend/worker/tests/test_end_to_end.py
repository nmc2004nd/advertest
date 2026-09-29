"""Worker chạy experiment qua API nội bộ thật (validation.md Phase 3: chạy và kết quả, chạy tiếp
sau gián đoạn, giới hạn và hủy, calibration). Postgres và MinIO thật (`make test-db`).

Model là YOLOv8n ngẫu nhiên trên KITTI tổng hợp (slice 2 ảnh), attack FGSM trên CPU.
"""

from __future__ import annotations

import time
import uuid
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from advertest_contracts.enums import ExperimentStatus, RunStatus
from advertest_contracts.models import CostProfile
from advertest_worker.cache import JobCache
from advertest_worker.client import LeaseLost, WorkerClient
from advertest_worker.job import JobRunner
from attacks.registry import get_spec, load_catalog
from backend.admin_cli.seed import load_attack_specs
from backend.app.api.deps import Storage, get_clock, get_sessionmaker, get_storage
from backend.app.db import models as m
from backend.app.main import create_app
from backend.app.presign import Presigner
from backend.app.services import compute_targets, experiments, registry
from backend.app.storage import Buckets
from backend.app.tests.db.conftest import _url, make_user
from backend.app.tests.db.local_store_factory import LocalData, build_local_store
from ml_core.runner import executor as executor_module
from ml_core.runner.config import LocalRunConfig
from ml_core.store import PresignedStore

pytestmark = pytest.mark.db


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 29, 8, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class Crash(BaseException):
    """Mô phỏng worker chết đột ngột (kill -9): không gửi gì thêm."""


@dataclass(frozen=True)
class World:
    admin_id: UUID
    local: LocalData


@pytest.fixture(scope="module")
def world(app_engine: Engine, buckets: Buckets, tmp_path_factory: pytest.TempPathFactory) -> World:
    local = build_local_store(tmp_path_factory.mktemp("worker-e2e"))
    with Session(app_engine) as session, session.begin():
        admin = make_user(session)
        for spec in load_attack_specs():
            session.execute(
                insert(m.AttackSpecRow)
                .values(
                    id=spec.id,
                    name=spec.name,
                    version=spec.version,
                    kind=spec.kind,
                    access=spec.access,
                    spec=spec.model_dump(mode="json"),
                    spec_sha256=spec.spec_sha256,
                )
                .on_conflict_do_nothing(index_elements=["spec_sha256"])
            )
        registry.import_local(session, local.store, buckets, actor=admin)
        return World(admin.id, local)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def api(app_engine: Engine, buckets: Buckets, clock: FakeClock) -> Iterator[TestClient]:
    app = create_app()
    factory = sessionmaker(app_engine)
    presigner = Presigner.for_endpoint(
        _url("ADVERTEST_TEST_MINIO_ENDPOINT"),
        _url("ADVERTEST_TEST_MINIO_ACCESS_KEY"),
        _url("ADVERTEST_TEST_MINIO_SECRET_KEY"),
    )
    app.dependency_overrides[get_sessionmaker] = lambda: factory
    app.dependency_overrides[get_storage] = lambda: Storage(buckets, presigner)
    app.dependency_overrides[get_clock] = lambda: clock
    with TestClient(app) as client:
        yield client


@dataclass
class Setup:
    token: str
    target_id: UUID
    experiment_id: UUID
    client: WorkerClient


def _submit(
    app_engine: Engine,
    world: World,
    api: TestClient,
    clock: FakeClock,
    *,
    seed: int,
    time_limit_s: int | None = None,
    target_id: UUID | None = None,
    token: str | None = None,
) -> Setup:
    """Target mới (hoặc target đã có) và experiment FGSM eps 4, 8 với `seed` riêng (tránh cache
    chéo giữa các test)."""
    spec = get_spec(load_catalog(), name="fgsm")
    config = LocalRunConfig.model_validate(
        {
            "model_id": str(world.local.card.id),
            "slice_id": str(world.local.slice.id),
            "mapping_id": str(world.local.mapping.id),
            "attacks": [
                {
                    "attack_spec_id": str(spec.id),
                    "spec_sha256": spec.spec_sha256,
                    "mode": "grid",
                    "grid": {"levels": [4, 8]},
                    "seed": seed,
                }
            ],
            "failure_cases_per_run": 2,
        }
    )
    with Session(app_engine) as session, session.begin():
        admin = session.get_one(m.User, world.admin_id)
        if target_id is None:
            issued = compute_targets.create(session, actor=admin, name=f"w-{uuid.uuid4().hex[:8]}")
            target, token = issued.target, issued.token
        else:
            target = session.get_one(m.ComputeTarget, target_id)
        experiment = experiments.submit(
            session, actor=admin, config=config, target=target,
            time_limit_s=time_limit_s, clock=clock,
        )  # fmt: skip
        ids = (target.id, experiment.id)
    assert token is not None
    client = WorkerClient(api, token, sleep=lambda _s: None)
    return Setup(token, ids[0], ids[1], client)


def _runner(
    setup: Setup, tmp_path: Path, clock: FakeClock, *, on_batch: Any = None, heartbeat: float = 3600
) -> JobRunner:
    return JobRunner(
        setup.client,
        JobCache(tmp_path / "cache"),
        "cpu",
        url_http=httpx.Client(timeout=60),
        heartbeat_interval_s=heartbeat,
        clock=clock,
        on_batch=on_batch,
    )


def _profile(setup: Setup, world: World, *, sec_per_image: float, batch_size: int) -> None:
    env = {"compute_target_id": str(setup.target_id), "gpu_model": None, "cuda_version": None,
           "driver_version": None}  # fmt: skip
    setup.client.cost_profile(
        CostProfile.model_validate(
            {
                "compute_target_id": str(setup.target_id),
                "model_version_id": str(world.local.card.id),
                "attack_spec_id": str(get_spec(load_catalog(), name="fgsm").id),
                "sec_per_image": sec_per_image,
                "peak_vram_mb": 0,
                "batch_size": batch_size,
                "measured_at": datetime(2026, 9, 29, tzinfo=UTC).isoformat(),
                "environment": env,
            }
        )
    )


def _state(app_engine: Engine, experiment_id: UUID) -> tuple[m.Experiment, list[m.Run]]:
    with Session(app_engine) as session:
        return session.get_one(m.Experiment, experiment_id), experiments.runs_of(
            session, experiment_id
        )


def _lease_and_run(runner: JobRunner, setup: Setup) -> None:
    lease = setup.client.lease()
    assert lease is not None and lease.experiment_id == setup.experiment_id
    runner.run_lease(lease)


def test_worker_completes_experiment_then_cache_skips(
    app_engine: Engine, world: World, api: TestClient, clock: FakeClock, buckets: Buckets,
    tmp_path: Path,
) -> None:  # fmt: skip
    setup = _submit(app_engine, world, api, clock, seed=101)
    batches: list[Sequence[str]] = []
    runner = _runner(setup, tmp_path, clock, on_batch=lambda _r, ids: batches.append(list(ids)))
    _lease_and_run(runner, setup)
    experiment, runs = _state(app_engine, setup.experiment_id)
    assert experiment.status == ExperimentStatus.COMPLETED
    assert [r.status for r in runs] == [RunStatus.COMPLETED, RunStatus.COMPLETED]
    for run in runs:
        assert run.metrics is not None and run.metrics["partial"] is False
        assert run.images_done == run.images_total == 2
        assert run.manifest_uri == f"s3://artifacts/runs/{run.id}/manifest.json"
        assert buckets.artifacts.exists(f"runs/{run.id}/manifest.json")
        assert buckets.artifacts.list(f"runs/{run.id}/candidates/") == []
    with Session(app_engine) as session:  # calibration tự chạy trước job
        profiles = session.scalars(
            select(m.CostProfile).where(m.CostProfile.compute_target_id == setup.target_id)
        ).all()
    assert len(profiles) == 1 and profiles[0].batch_size <= 2
    assert sum(len(b) for b in batches) == 4

    again = _submit(
        app_engine, world, api, clock, seed=101, target_id=setup.target_id, token=setup.token
    )
    batches.clear()
    _lease_and_run(
        _runner(again, tmp_path, clock, on_batch=lambda _r, ids: batches.append(ids)), again
    )
    experiment2, runs2 = _state(app_engine, again.experiment_id)
    assert experiment2.status == ExperimentStatus.COMPLETED
    assert [r.status for r in runs2] == [RunStatus.SKIPPED, RunStatus.SKIPPED]
    assert [r.cached_from_run_id for r in runs2] == [r.id for r in runs]
    assert [r.metrics for r in runs2] == [r.metrics for r in runs]
    assert batches == []  # attack không được gọi


def test_resume_after_worker_dies(
    app_engine: Engine, world: World, api: TestClient, clock: FakeClock, buckets: Buckets,
    tmp_path: Path,
) -> None:  # fmt: skip
    setup = _submit(app_engine, world, api, clock, seed=202)
    _profile(setup, world, sec_per_image=0.01, batch_size=1)
    processed: Counter[tuple[UUID, str]] = Counter()

    def crash_after_first(run_id: UUID, ids: Sequence[str]) -> None:
        processed.update((run_id, i) for i in ids)
        raise Crash

    with pytest.raises(Crash):
        _lease_and_run(_runner(setup, tmp_path / "a", clock, on_batch=crash_after_first), setup)
    _, runs = _state(app_engine, setup.experiment_id)
    assert runs[0].status == RunStatus.RUNNING and runs[0].images_done == 1
    assert runs[0].checkpoint_key == f"runs/{runs[0].id}/checkpoints/0.json"
    assert buckets.artifacts.list(f"runs/{runs[0].id}/checkpoints/") == [runs[0].checkpoint_key]

    clock.advance(30)
    assert setup.client.lease() is None  # lease cũ còn hạn
    clock.advance(31)

    def count(run_id: UUID, ids: Sequence[str]) -> None:
        processed.update((run_id, i) for i in ids)

    _lease_and_run(_runner(setup, tmp_path / "b", clock, on_batch=count), setup)
    experiment, runs = _state(app_engine, setup.experiment_id)
    assert experiment.status == ExperimentStatus.COMPLETED
    assert [r.status for r in runs] == [RunStatus.COMPLETED, RunStatus.COMPLETED]
    # Mỗi ảnh được xử lý đúng một lần trên tổng hai worker.
    expected = {(r.id, i) for r in runs for i in world.local.slice.image_ids}
    assert set(processed) == expected and set(processed.values()) == {1}
    assert buckets.artifacts.list(f"runs/{runs[0].id}/candidates/") == []
    # Checkpoint cũ (kể cả checkpoint trong bundle khi chạy tiếp) bị xóa; mỗi run còn đúng
    # checkpoint cuối cùng.
    for run in runs:
        assert buckets.artifacts.list(f"runs/{run.id}/checkpoints/") == [
            f"runs/{run.id}/checkpoints/1.json"
        ]


def test_time_limit_gives_partial_result(
    app_engine: Engine, world: World, api: TestClient, clock: FakeClock, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    # Mỗi batch "tốn" 25 giây; giới hạn 40 giây; ước lượng 20 giây/ảnh: batch 1 chạy, batch 2
    # không đủ thời gian → run 1 dừng với kết quả một phần, run 2 không chạy.
    ticks = iter(range(0, 10_000, 25))
    monkeypatch.setattr(executor_module, "time", SimpleNamespace(perf_counter=lambda: next(ticks)))
    setup = _submit(app_engine, world, api, clock, seed=303, time_limit_s=40)
    _profile(setup, world, sec_per_image=20.0, batch_size=1)
    _lease_and_run(_runner(setup, tmp_path, clock), setup)
    experiment, runs = _state(app_engine, setup.experiment_id)
    assert experiment.status == ExperimentStatus.COMPLETED
    assert [r.status for r in runs] == [RunStatus.STOPPED_LIMIT, RunStatus.STOPPED_LIMIT]
    first, second = runs
    assert first.images_done == 1 < first.images_total
    assert first.metrics is not None and first.metrics["partial"] is True
    assert second.images_done == 0 and second.metrics is None
    assert experiment.processing_seconds_used == 25


def test_cancel_stops_after_current_batch(
    app_engine: Engine, world: World, api: TestClient, clock: FakeClock, tmp_path: Path
) -> None:
    setup = _submit(app_engine, world, api, clock, seed=404)
    _profile(setup, world, sec_per_image=0.01, batch_size=1)
    processed: list[str] = []

    def cancel_after_first(_run_id: UUID, ids: Sequence[str]) -> None:
        processed.extend(ids)
        if len(processed) == 1:
            with Session(app_engine) as session, session.begin():
                admin = session.get_one(m.User, world.admin_id)
                experiments.cancel(
                    session, actor=admin, experiment_id=setup.experiment_id, clock=clock
                )
            time.sleep(0.5)  # để luồng heartbeat nhận chỉ thị cancel

    _lease_and_run(
        _runner(setup, tmp_path, clock, on_batch=cancel_after_first, heartbeat=0.1), setup
    )
    experiment, runs = _state(app_engine, setup.experiment_id)
    assert experiment.status == ExperimentStatus.CANCELLED
    assert [r.status for r in runs] == [RunStatus.CANCELLED, RunStatus.CANCELLED]
    assert processed == world.local.slice.image_ids[:1]
    assert runs[0].images_done == 1 and runs[1].images_done == 0


def test_corrupt_checkpoint_fails_only_that_run(
    app_engine: Engine, world: World, api: TestClient, clock: FakeClock, buckets: Buckets,
    tmp_path: Path,
) -> None:  # fmt: skip
    setup = _submit(app_engine, world, api, clock, seed=505)
    _profile(setup, world, sec_per_image=0.01, batch_size=1)

    def crash(_run_id: UUID, _ids: Sequence[str]) -> None:
        raise Crash

    with pytest.raises(Crash):
        _lease_and_run(_runner(setup, tmp_path / "a", clock, on_batch=crash), setup)
    _, runs = _state(app_engine, setup.experiment_id)
    assert runs[0].checkpoint_key is not None
    # Checkpoint trong MinIO bị hỏng (ghi thẳng bằng client S3, bỏ qua tính bất biến).
    raw: Any = buckets.artifacts.client
    raw.put_object(Bucket="artifacts", Key=runs[0].checkpoint_key, Body=b"{hong")
    clock.advance(61)
    _lease_and_run(_runner(setup, tmp_path / "b", clock), setup)
    experiment, runs = _state(app_engine, setup.experiment_id)
    assert [r.status for r in runs] == [RunStatus.FAILED, RunStatus.COMPLETED]
    assert runs[0].status_reason is not None and "Error" in runs[0].status_reason["message"]
    assert experiment.status == ExperimentStatus.COMPLETED


def test_failed_checkpoint_delete_does_not_fail_run(
    app_engine: Engine, world: World, api: TestClient, clock: FakeClock, buckets: Buckets,
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    setup = _submit(app_engine, world, api, clock, seed=707)
    _profile(setup, world, sec_per_image=0.01, batch_size=1)
    original = PresignedStore.delete

    def flaky_delete(self: PresignedStore, key: str) -> None:
        if "/checkpoints/" in key:
            raise httpx.ConnectError("MinIO tạm tắt")
        original(self, key)

    monkeypatch.setattr(PresignedStore, "delete", flaky_delete)
    _lease_and_run(_runner(setup, tmp_path, clock), setup)
    experiment, runs = _state(app_engine, setup.experiment_id)
    assert experiment.status == ExperimentStatus.COMPLETED
    assert [r.status for r in runs] == [RunStatus.COMPLETED, RunStatus.COMPLETED]
    assert len(buckets.artifacts.list(f"runs/{runs[0].id}/checkpoints/")) == 2  # không xóa được


def test_lease_lost_while_deleting_checkpoint_stops_immediately(
    app_engine: Engine, world: World, api: TestClient, clock: FakeClock, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    setup = _submit(app_engine, world, api, clock, seed=808)
    _profile(setup, world, sec_per_image=0.01, batch_size=1)
    original = WorkerClient.artifact_url

    def lease_lost_on_delete(
        self: WorkerClient, run_id: UUID, lease_id: UUID, key: str, method: Any
    ) -> str:
        if method == "DELETE" and "/checkpoints/" in key:
            raise LeaseLost(409, "conflict", "lease đã chuyển cho worker khác")
        return original(self, run_id, lease_id, key, method)

    monkeypatch.setattr(WorkerClient, "artifact_url", lease_lost_on_delete)
    batches: list[Sequence[str]] = []
    runner = _runner(setup, tmp_path, clock, on_batch=lambda _r, ids: batches.append(ids))
    _lease_and_run(runner, setup)
    _, runs = _state(app_engine, setup.experiment_id)
    # Batch 2 xong và progress thành công, rồi xóa checkpoint 0 gặp 409: worker dừng ngay (trước
    # hook của batch 2), không gửi complete, không chạy run sau.
    assert len(batches) == 1
    assert runs[0].images_done == 2
    assert [r.status for r in runs] == [RunStatus.RUNNING, RunStatus.QUEUED]
