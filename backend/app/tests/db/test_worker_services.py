"""Service experiments, leasing, runs, estimate (validation.md Phase 3: lease, chạy và kết quả,
giới hạn và hủy, calibration và ước lượng, kiểm toán). Postgres và MinIO thật (`make test-db`)."""

from __future__ import annotations

import json
import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from advertest_contracts.enums import ExperimentStatus, RunStatus
from advertest_contracts.hashing import sha256_of
from advertest_contracts.models import (
    CostProfile,
    FailureCaseRecord,
    ProgressReport,
    RunCompletion,
    RunStartRequest,
    compute_failure_case_id,
)
from attacks.registry import get_spec, load_catalog
from backend.admin_cli.seed import load_attack_specs
from backend.app.db import models as m
from backend.app.services import compute_targets, estimate, experiments, leasing, registry, runs
from backend.app.services.errors import Conflict, Forbidden, Invalid, NotFound
from backend.app.storage import Buckets
from ml_core.runner.config import LocalRunConfig

from .conftest import make_user
from .local_store_factory import LocalData, build_local_store

pytestmark = pytest.mark.db

MOCKS = Path(__file__).resolve().parents[4] / "contracts" / "mocks"
T0 = datetime(2026, 9, 29, 8, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def _status(run: m.Run) -> RunStatus:
    """Đọc trạng thái hiện tại (tránh mypy thu hẹp kiểu qua các assert trước đó)."""
    return run.status


def _experiment_status(experiment: m.Experiment) -> ExperimentStatus:
    return experiment.status


def _mock(path: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((MOCKS / path).read_text())
    return data


@dataclass(frozen=True)
class World:
    admin_id: UUID
    local: LocalData


@pytest.fixture(scope="module")
def world(app_engine: Engine, buckets: Buckets, tmp_path_factory: pytest.TempPathFactory) -> World:
    local = build_local_store(tmp_path_factory.mktemp("worker-services"))
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
        return World(admin_id=admin.id, local=local)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def admin(db: Session, world: World) -> m.User:
    user = db.get(m.User, world.admin_id)
    assert user is not None
    return user


def _target(db: Session, admin: m.User, time_limit_s: int = 7200) -> tuple[m.ComputeTarget, str]:
    issued = compute_targets.create(
        db, actor=admin, name=f"t-{uuid.uuid4().hex[:8]}", time_limit_s=time_limit_s
    )
    return issued.target, issued.token


def _attack(name: str, levels: list[float]) -> dict[str, Any]:
    spec = get_spec(load_catalog(), name=name)
    return {
        "attack_spec_id": str(spec.id),
        "spec_sha256": spec.spec_sha256,
        "mode": "grid",
        "grid": {"levels": levels},
        "seed": 0,
    }


def _config(world: World, attacks: list[dict[str, Any]] | None = None) -> LocalRunConfig:
    return LocalRunConfig.model_validate(
        {
            "model_id": str(world.local.card.id),
            "slice_id": str(world.local.slice.id),
            "mapping_id": str(world.local.mapping.id),
            "attacks": attacks or [_attack("fgsm", [4, 8]), _attack("pgd_linf", [4])],
            "device": "cpu",
            "batch_size": 2,
        }
    )


def _submit(
    db: Session,
    admin: m.User,
    world: World,
    target: m.ComputeTarget,
    clock: FakeClock,
    **kwargs: Any,
) -> m.Experiment:
    return experiments.submit(
        db, actor=admin, config=_config(world), target=target, clock=clock, **kwargs
    )


def _start_request(lease_id: UUID, seed: int | None = None) -> RunStartRequest:
    data = _mock("run_start_request/gpu_local.json")
    data["lease_id"] = str(lease_id)
    data["fingerprint_inputs"]["seed"] = random.randrange(1 << 30) if seed is None else seed
    data["fingerprint"] = sha256_of(data["fingerprint_inputs"])
    return RunStartRequest.model_validate(data)


def _completion(
    run: m.Run,
    lease_id: UUID,
    buckets: Buckets | None,
    *,
    status: str = "completed",
    cases: int = 1,
    thumbs: bool = True,
) -> RunCompletion:
    """Kết quả hợp lệ của `run`; artifact được đặt vào MinIO khi có `buckets`."""
    assert run.fingerprint is not None
    result = _mock("run_result/completed.json")
    template = _mock("failure_case_record/worker_minio.json")
    records = []
    for i in range(cases):
        image_id = f"00005{i}"
        case_id = compute_failure_case_id(run.fingerprint, run.id, image_id)
        base = f"runs/{run.id}/cases/{case_id}"
        artifacts = {
            "clean_png": f"{base}/clean.png",
            "adversarial_png": f"{base}/adversarial.png",
            "perturbation_png": f"{base}/perturbation.png",
            "clean_thumb": f"{base}/clean_thumb.webp" if thumbs else None,
            "adversarial_thumb": f"{base}/adversarial_thumb.webp" if thumbs else None,
        }
        if buckets is not None:
            for key in artifacts.values():
                if key is not None:
                    buckets.artifacts.put(key, key.encode())
        records.append(
            FailureCaseRecord.model_validate(
                {
                    **template,
                    "id": str(case_id),
                    "run_id": str(run.id),
                    "fingerprint": run.fingerprint,
                    "image_id": image_id,
                    "artifacts": artifacts,
                }
            )
        )
    manifest_key = f"runs/{run.id}/manifest.json"
    if buckets is not None:
        buckets.artifacts.put(manifest_key, b"{}")
    done = run.images_total if status == "completed" else 1
    metrics = dict(result["metrics"], partial=status == "stopped_limit")
    result.update(
        run_id=str(run.id),
        experiment_id=str(run.experiment_id),
        fingerprint=run.fingerprint,
        attack_spec_id=str(run.attack_spec_id),
        level=run.level,
        status=status,
        status_reason={
            "completed": None,
            "stopped_limit": {"code": "time", "message": "Chạm giới hạn"},
            "cancelled": {"code": "cancelled", "message": "Bị hủy"},
            "failed": {"code": "error", "message": "RuntimeError: lỗi"},
        }[status],
        progress={"images_done": done, "images_total": run.images_total},
        metrics=metrics if status in ("completed", "stopped_limit") else None,
        failure_case_ids=[str(r.id) for r in records],
        manifest_uri=f"s3://artifacts/{manifest_key}",
        cost=None,
    )
    return RunCompletion.model_validate(
        {"lease_id": str(lease_id), "run_result": result, "failure_cases": records}
    )


def _leased(
    db: Session, admin: m.User, world: World, clock: FakeClock, **kwargs: Any
) -> tuple[m.ComputeTarget, m.Experiment, list[m.Run]]:
    target, _ = _target(db, admin, **kwargs)
    experiment = _submit(db, admin, world, target, clock)
    leased = leasing.lease(db, target, clock)
    assert leased is experiment
    return target, experiment, experiments.runs_of(db, experiment.id)


def _run_to_completion(
    db: Session,
    target: m.ComputeTarget,
    experiment: m.Experiment,
    run: m.Run,
    buckets: Buckets,
    clock: FakeClock,
) -> RunStartRequest:
    assert experiment.lease_id is not None
    request = _start_request(experiment.lease_id)
    assert runs.start(db, target, run.id, request, clock).action == "run"
    runs.complete(
        db,
        target,
        run.id,
        _completion(run, experiment.lease_id, buckets),
        buckets.artifacts.exists,
        clock,
    )
    return request


# ---------------------------------------------------------------- submit


def test_submit_creates_queued_experiment_with_ordered_runs(
    db: Session, admin: m.User, world: World, clock: FakeClock
) -> None:
    target, _ = _target(db, admin, time_limit_s=900)
    experiment = _submit(db, admin, world, target, clock)
    assert experiment.status == ExperimentStatus.QUEUED
    assert experiment.protocol_id == experiments.DEV_OPEN_PROTOCOL_ID
    assert experiment.limit_value == Decimal(900) and experiment.submitted_at == T0
    assert experiment.failure_cases_per_run == 20
    planned = experiments.runs_of(db, experiment.id)
    assert [(r.level, r.status, r.fingerprint) for r in planned] == [
        (4.0, RunStatus.QUEUED, None),
        (8.0, RunStatus.QUEUED, None),
        (4.0, RunStatus.QUEUED, None),
    ]
    assert all(r.images_total == 2 for r in planned)
    assert planned[0].params == {"eps": 4.0}
    audit_row = db.scalars(
        select(m.AuditLog).where(
            m.AuditLog.entity_id == experiment.id, m.AuditLog.action == "experiment.submit"
        )
    ).one()
    assert audit_row.actor_id == admin.id

    override = _submit(db, admin, world, target, clock, time_limit_s=60)
    assert override.limit_value == Decimal(60)


def test_submit_rejects_unknown_or_inconsistent_inputs(
    db: Session, admin: m.User, world: World, clock: FakeClock
) -> None:
    target, _ = _target(db, admin)
    config = _config(world)
    with pytest.raises(NotFound):
        experiments.submit(
            db, actor=admin, config=config.model_copy(update={"model_id": uuid.uuid4()}),
            target=target,
        )  # fmt: skip
    bad_spec = _attack("fgsm", [4])
    bad_spec["spec_sha256"] = "0" * 64
    with pytest.raises(Invalid):
        experiments.submit(db, actor=admin, config=_config(world, [bad_spec]), target=target)
    with pytest.raises(Invalid):
        experiments.submit(db, actor=admin, config=config, target=target, time_limit_s=0)


# ---------------------------------------------------------------- lease


def test_lease_first_come_first_served_per_target(
    db: Session, admin: m.User, world: World, clock: FakeClock
) -> None:
    target, _ = _target(db, admin)
    other, _ = _target(db, admin)
    first = _submit(db, admin, world, target, clock)
    clock.advance(1)
    second = _submit(db, admin, world, target, clock)
    assert leasing.lease(db, other, clock) is None
    leased = leasing.lease(db, target, clock)
    assert leased is first and first.status == ExperimentStatus.RUNNING
    assert first.lease_id is not None and first.lease_expires_at == clock.now + timedelta(
        seconds=60
    )
    assert leasing.lease(db, target, clock) is second  # không trả lại experiment đang được giữ
    assert leasing.lease(db, target, clock) is None
    assert target.last_heartbeat_at == clock.now


def test_expired_lease_is_released_and_old_lease_id_rejected(
    db: Session, admin: m.User, world: World, clock: FakeClock
) -> None:
    target, experiment, planned = _leased(db, admin, world, clock)
    old_lease = experiment.lease_id
    assert old_lease is not None
    clock.advance(30)
    assert leasing.heartbeat(db, target, experiment.id, old_lease, clock).action == "continue"
    clock.advance(59)
    assert leasing.lease(db, target, clock) is None  # heartbeat đã gia hạn
    clock.advance(2)
    again = leasing.lease(db, target, clock)
    assert again is experiment and experiment.lease_id not in (None, old_lease)
    with pytest.raises(Conflict):
        leasing.heartbeat(db, target, experiment.id, old_lease, clock)
    with pytest.raises(Conflict):
        runs.start(db, target, planned[0].id, _start_request(old_lease), clock)


def test_other_target_forbidden(
    db: Session, admin: m.User, world: World, clock: FakeClock, buckets: Buckets
) -> None:
    target, experiment, planned = _leased(db, admin, world, clock)
    other, _ = _target(db, admin)
    lease_id = experiment.lease_id
    assert lease_id is not None
    with pytest.raises(Forbidden):
        leasing.heartbeat(db, other, experiment.id, lease_id, clock)
    with pytest.raises(Forbidden):
        runs.start(db, other, planned[0].id, _start_request(lease_id), clock)
    report = ProgressReport(
        lease_id=lease_id,
        images_done=1,
        batch_index=0,
        checkpoint_key=f"runs/{planned[0].id}/checkpoints/0.json",
        processing_seconds_delta=1.0,
    )
    with pytest.raises(Forbidden):
        runs.progress(db, other, planned[0].id, report, clock)
    with pytest.raises(NotFound):
        runs.progress(db, target, uuid.uuid4(), report, clock)


# ---------------------------------------------------------------- start, progress, complete


def test_full_run_flow_completes_experiment(
    db: Session, admin: m.User, world: World, clock: FakeClock, buckets: Buckets
) -> None:
    target, experiment, planned = _leased(db, admin, world, clock)
    lease_id = experiment.lease_id
    assert lease_id is not None
    first = planned[0]
    with pytest.raises(Conflict):  # chưa start
        runs.complete(
            db, target, first.id, _start_and_fake(first, lease_id), buckets.artifacts.exists, clock
        )
    request = _start_request(lease_id)
    assert runs.start(db, target, first.id, request, clock).action == "run"
    assert first.status == RunStatus.RUNNING and first.fingerprint == request.fingerprint
    # Chạy tiếp sau gián đoạn: cùng fingerprint → tiếp tục; khác → xung đột.
    assert runs.start(db, target, first.id, request, clock).action == "run"
    with pytest.raises(Conflict):
        runs.start(db, target, first.id, _start_request(lease_id), clock)

    report = ProgressReport(
        lease_id=lease_id,
        images_done=1,
        batch_index=0,
        checkpoint_key=f"runs/{first.id}/checkpoints/0.json",
        processing_seconds_delta=12.5,
    )
    clock.advance(3600)  # thời gian chờ không được tính
    directive = runs.progress(db, target, first.id, report, clock)
    assert directive.action == "continue" and directive.remaining_seconds == 7200 - 12.5
    assert experiment.processing_seconds_used == Decimal("12.5") and first.gpu_seconds == 12.5
    assert first.checkpoint_key == report.checkpoint_key and first.checkpoint_batch_index == 0
    with pytest.raises(Invalid):
        runs.progress(db, target, first.id, report.model_copy(update={"images_done": 0}), clock)
    with pytest.raises(Invalid):
        runs.progress(
            db, target, first.id,
            report.model_copy(update={"checkpoint_key": "runs/khac/checkpoints/0.json"}), clock,
        )  # fmt: skip

    completion = _completion(first, lease_id, buckets, cases=2)
    runs.complete(db, target, first.id, completion, buckets.artifacts.exists, clock)
    assert _status(first) == RunStatus.COMPLETED and first.images_done == first.images_total
    cases = db.scalars(
        select(m.FailureCase).where(m.FailureCase.run_id == first.id).order_by(m.FailureCase.rank)
    ).all()
    assert [c.id for c in cases] == completion.run_result.failure_case_ids
    assert cases[0].artifacts["clean_thumb"].endswith("clean_thumb.webp")
    assert runs.result_of(db, first).failure_case_ids == completion.run_result.failure_case_ids
    with pytest.raises(Conflict):  # đã completed
        runs.complete(db, target, first.id, completion, buckets.artifacts.exists, clock)

    assert experiment.status == ExperimentStatus.RUNNING
    for run in planned[1:]:
        _run_to_completion(db, target, experiment, run, buckets, clock)
    assert _experiment_status(experiment) == ExperimentStatus.COMPLETED
    assert experiment.lease_id is None


def _start_and_fake(run: m.Run, lease_id: UUID) -> RunCompletion:
    """Kết quả cho run chưa start (fingerprint giả) để kiểm tra bị từ chối."""
    run.fingerprint = "f" * 64
    completion = _completion(run, lease_id, None, cases=0)
    run.fingerprint = None
    return completion


def test_complete_checks_artifacts_and_result(
    db: Session, admin: m.User, world: World, clock: FakeClock, buckets: Buckets
) -> None:
    target, experiment, planned = _leased(db, admin, world, clock)
    lease_id = experiment.lease_id
    assert lease_id is not None
    run = planned[0]
    runs.start(db, target, run.id, _start_request(lease_id), clock)
    exists = buckets.artifacts.exists
    with pytest.raises(Invalid, match="chưa có"):
        runs.complete(db, target, run.id, _completion(run, lease_id, None), exists, clock)
    with pytest.raises(Invalid, match="thumbnail"):
        runs.complete(
            db, target, run.id, _completion(run, lease_id, buckets, thumbs=False), exists, clock
        )
    wrong = _completion(run, lease_id, buckets)
    bad = wrong.run_result.model_copy(update={"level": 99.0})
    with pytest.raises(Invalid, match="level"):
        runs.complete(
            db, target, run.id, wrong.model_copy(update={"run_result": bad}), exists, clock
        )
    with pytest.raises(Invalid, match="cancelled"):
        runs.complete(
            db,
            target,
            run.id,
            _completion(run, lease_id, buckets, status="cancelled", cases=0),
            exists,
            clock,
        )
    assert run.status == RunStatus.RUNNING
    runs.complete(
        db,
        target,
        run.id,
        _completion(run, lease_id, buckets, status="failed", cases=0),
        exists,
        clock,
    )
    assert _status(run) == RunStatus.FAILED and run.status_reason is not None


def test_same_fingerprint_is_skipped_as_cached(
    db: Session, admin: m.User, world: World, clock: FakeClock, buckets: Buckets
) -> None:
    target, experiment, planned = _leased(db, admin, world, clock)
    request = _run_to_completion(db, target, experiment, planned[0], buckets, clock)
    origin = planned[0]

    target2, experiment2, planned2 = _leased(db, admin, world, clock)
    lease2 = experiment2.lease_id
    assert lease2 is not None
    same = request.model_copy(update={"lease_id": lease2})
    response = runs.start(db, target2, planned2[0].id, same, clock)
    assert response.action == "skip_cached" and response.cached_from_run_id == origin.id
    assert response.cached_result is not None
    assert response.cached_result.failure_case_ids == runs.failure_case_ids(db, origin.id)
    cached = planned2[0]
    assert cached.status == RunStatus.SKIPPED and cached.cached_from_run_id == origin.id
    assert cached.status_reason is not None and cached.status_reason["code"] == "cached"
    assert cached.metrics == origin.metrics
    result = runs.result_of(db, cached)
    assert result.cached_from_run_id == origin.id
    assert result.failure_case_ids == response.cached_result.failure_case_ids


def test_time_limit_stops_remaining_runs(
    db: Session, admin: m.User, world: World, clock: FakeClock, buckets: Buckets
) -> None:
    target, experiment, planned = _leased(db, admin, world, clock, time_limit_s=10)
    lease_id = experiment.lease_id
    assert lease_id is not None
    run = planned[0]
    runs.start(db, target, run.id, _start_request(lease_id), clock)
    report = ProgressReport(
        lease_id=lease_id,
        images_done=1,
        batch_index=0,
        checkpoint_key=f"runs/{run.id}/checkpoints/0.json",
        processing_seconds_delta=11.0,
    )
    directive = runs.progress(db, target, run.id, report, clock)
    assert directive.action == "stop_limit" and directive.remaining_seconds == 0
    assert leasing.heartbeat(db, target, experiment.id, lease_id, clock).action == "stop_limit"
    completion = _completion(run, lease_id, buckets, status="stopped_limit", cases=0)
    runs.complete(db, target, run.id, completion, buckets.artifacts.exists, clock)
    assert run.status == RunStatus.STOPPED_LIMIT and run.metrics is not None
    assert run.metrics["partial"] is True and run.images_done < run.images_total
    for other in planned[1:]:
        assert other.status == RunStatus.STOPPED_LIMIT and other.images_done == 0
        assert other.status_reason is not None and other.status_reason["code"] == "time"
    assert experiment.status == ExperimentStatus.COMPLETED


def test_cancel_running_experiment(
    db: Session, admin: m.User, world: World, clock: FakeClock, buckets: Buckets
) -> None:
    target, experiment, planned = _leased(db, admin, world, clock)
    lease_id = experiment.lease_id
    assert lease_id is not None
    run = planned[0]
    runs.start(db, target, run.id, _start_request(lease_id), clock)
    experiments.cancel(db, actor=admin, experiment_id=experiment.id, clock=clock)
    assert experiment.status == ExperimentStatus.CANCELLED
    assert run.status == RunStatus.RUNNING  # worker còn giữ lease: đợi worker báo
    assert [r.status for r in planned[1:]] == [RunStatus.CANCELLED, RunStatus.CANCELLED]
    assert leasing.heartbeat(db, target, experiment.id, lease_id, clock).action == "cancel"
    assert leasing.lease(db, target, clock) is None
    completion = _completion(run, lease_id, buckets, status="cancelled", cases=0)
    runs.complete(db, target, run.id, completion, buckets.artifacts.exists, clock)
    assert _status(run) == RunStatus.CANCELLED
    assert experiment.status == ExperimentStatus.CANCELLED and experiment.lease_id is None
    with pytest.raises(Conflict):
        experiments.cancel(db, actor=admin, experiment_id=experiment.id, clock=clock)
    actions = db.scalars(
        select(m.AuditLog.action).where(m.AuditLog.entity_id == experiment.id)
    ).all()
    assert "experiment.cancel" in actions


def test_cancel_with_expired_lease_cancels_running_run(
    db: Session, admin: m.User, world: World, clock: FakeClock
) -> None:
    target, experiment, planned = _leased(db, admin, world, clock)
    assert experiment.lease_id is not None
    runs.start(db, target, planned[0].id, _start_request(experiment.lease_id), clock)
    clock.advance(120)
    experiments.cancel(db, actor=admin, experiment_id=experiment.id, clock=clock)
    assert all(r.status == RunStatus.CANCELLED for r in planned)
    assert experiment.lease_id is None


# ---------------------------------------------------------------- cost profile, ước lượng


def test_cost_profiles_and_estimate(
    db: Session, admin: m.User, world: World, clock: FakeClock
) -> None:
    target, _ = _target(db, admin)
    experiment = _submit(db, admin, world, target, clock)
    assert estimate.estimate_experiment(db, experiment) is None
    fgsm = get_spec(load_catalog(), name="fgsm")
    pgd = get_spec(load_catalog(), name="pgd_linf")
    env = {"compute_target_id": str(target.id), "gpu_model": None, "cuda_version": None,
           "driver_version": None}  # fmt: skip

    def profile(spec_id: UUID, sec: float, measured: datetime) -> CostProfile:
        return CostProfile.model_validate(
            {
                "compute_target_id": str(target.id),
                "model_version_id": str(world.local.card.id),
                "attack_spec_id": str(spec_id),
                "sec_per_image": sec,
                "peak_vram_mb": 0,
                "batch_size": 2,
                "measured_at": measured.isoformat(),
                "environment": env,
            }
        )

    runs.record_cost_profile(db, target, profile(fgsm.id, 9.0, T0))
    assert estimate.estimate_experiment(db, experiment) is None  # thiếu pgd
    runs.record_cost_profile(db, target, profile(fgsm.id, 0.5, T0 + timedelta(hours=1)))
    runs.record_cost_profile(db, target, profile(pgd.id, 2.0, T0))
    # 2 run FGSM * 2 ảnh * 0.5 + 1 run PGD * 2 ảnh * 2.0 = 6.0; nhân 1.2
    assert estimate.estimate_experiment(db, experiment) == pytest.approx(7.2)
    other, _ = _target(db, admin)
    with pytest.raises(Forbidden):
        runs.record_cost_profile(db, other, profile(fgsm.id, 1.0, T0))
    assert estimate.estimate_seconds([], {}) == 0.0


def test_concurrent_lease_never_returns_same_experiment(
    app_engine: Engine, world: World, clock: FakeClock
) -> None:
    """Hai worker (hai transaction) lease cùng lúc: SKIP LOCKED cho mỗi bên một experiment."""
    with Session(app_engine) as setup, setup.begin():
        actor = setup.get(m.User, world.admin_id)
        assert actor is not None
        target, _ = _target(setup, actor)
        first = _submit(setup, actor, world, target, clock).id
        clock.advance(1)
        second = _submit(setup, actor, world, target, clock).id
        target_id = target.id
    with Session(app_engine) as a, Session(app_engine) as b, a.begin():
        leased_a = leasing.lease(a, a.get_one(m.ComputeTarget, target_id), clock)
        with b.begin():  # a chưa commit: dòng của a vẫn đang bị khóa
            # Nếu b phải chờ khóa của a thì fail sau 5 giây thay vì treo.
            b.execute(text("SET LOCAL lock_timeout = '5s'"))
            leased_b = leasing.lease(b, b.get_one(m.ComputeTarget, target_id), clock)
            assert leased_b is not None and leased_b.id == second
        assert leased_a is not None and leased_a.id == first
