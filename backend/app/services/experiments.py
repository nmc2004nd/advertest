"""Gửi và hủy experiment (requirements.md Phase 3, CLI quản trị `submit`, `experiment cancel`).

Phase này chưa có endpoint công khai: experiment chỉ được tạo qua CLI quản trị phía server.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from advertest_contracts.enums import ExperimentStatus, LimitKind, RunStatus
from advertest_contracts.hashing import sha256_of
from advertest_contracts.models import (
    AttackSpec,
    ExperimentConfig,
    InferenceParams,
    Limit,
    StatusReason,
)
from backend.app.db import models as m
from backend.app.services import audit
from backend.app.services.clock import Clock, utcnow
from backend.app.services.errors import Conflict, Invalid, NotFound
from ml_core.models.wrapper import DEFAULT_INFERENCE_PARAMS
from ml_core.runner.config import LocalRunConfig

# Seed trong migration 0002 (`content_id(sha256_of({"protocol": "dev-open"}))`).
DEV_OPEN_PROTOCOL_ID = UUID("2edcdef5-0d3a-5d5f-98ac-b02637fa6718")
ACTIVE = (ExperimentStatus.QUEUED, ExperimentStatus.RUNNING)
TERMINAL_RUN = (
    RunStatus.COMPLETED,
    RunStatus.FAILED,
    RunStatus.SKIPPED,
    RunStatus.STOPPED_LIMIT,
    RunStatus.CANCELLED,
)


def reason(code: str, message: str) -> dict[str, str]:
    return StatusReason.model_validate({"code": code, "message": message}).model_dump(mode="json")


def _spec(session: Session, spec_id: UUID, spec_sha256: str) -> AttackSpec:
    row = session.scalar(select(m.AttackSpecRow).where(m.AttackSpecRow.spec_sha256 == spec_sha256))
    if row is None or row.id != spec_id:
        raise Invalid(f"Attack spec {spec_id} ({spec_sha256[:12]}) không có trong catalog")
    if not row.is_active:
        raise Invalid(f"Attack spec {row.name} v{row.version} không còn hoạt động")
    return AttackSpec.model_validate(
        {**row.spec, "id": str(row.id), "spec_sha256": row.spec_sha256}
    )


def submit(
    session: Session,
    *,
    actor: m.User,
    config: LocalRunConfig,
    target: m.ComputeTarget,
    time_limit_s: int | None = None,
    params: InferenceParams = DEFAULT_INFERENCE_PARAMS,
    clock: Clock = utcnow,
) -> m.Experiment:
    """Tạo experiment `queued` gắn protocol `dev-open` và lập danh sách run (mỗi cặp attack,
    level là một run, theo thứ tự trong cấu hình). `device`, `batch_size` của cấu hình bị bỏ qua:
    worker dùng cost profile."""
    model = session.get(m.ModelVersion, config.model_id)
    slice_row = session.get(m.Slice, config.slice_id)
    mapping = session.get(m.ClassMapping, config.mapping_id)
    if model is None or slice_row is None or mapping is None:
        raise NotFound("Model, slice hoặc mapping chưa được đăng ký (chạy import-local)")
    if mapping.model_version_id != model.id:
        raise Invalid("Mapping không thuộc model đã chọn")
    if mapping.dataset_version_id != slice_row.dataset_version_id:
        raise Invalid("Mapping và slice thuộc hai dataset version khác nhau")
    limit_s = time_limit_s if time_limit_s is not None else target.default_time_limit_s
    if limit_s <= 0:
        raise Invalid("Giới hạn thời gian phải lớn hơn 0")
    specs = [_spec(session, a.attack_spec_id, a.spec_sha256) for a in config.attacks]

    experiment_config = ExperimentConfig(
        protocol_id=DEV_OPEN_PROTOCOL_ID,
        model_version_id=model.id,
        slice_id=slice_row.id,
        class_mapping_id=mapping.id,
        compute_target_id=target.id,
        attacks=config.attacks,
        limit=Limit(kind=LimitKind.TIME, value=Decimal(limit_s)),
    )
    experiment = m.Experiment(
        created_by=actor.id,
        protocol_id=DEV_OPEN_PROTOCOL_ID,
        model_version_id=model.id,
        slice_id=slice_row.id,
        class_mapping_id=mapping.id,
        compute_target_id=target.id,
        config=experiment_config.model_dump(mode="json"),
        config_sha256=sha256_of(experiment_config),
        status=ExperimentStatus.QUEUED,
        limit_kind=LimitKind.TIME,
        limit_value=Decimal(limit_s),
        submitted_at=clock(),
        inference_params=params.model_dump(mode="json"),
        failure_cases_per_run=config.failure_cases_per_run,
    )
    session.add(experiment)
    session.flush()
    ordinal = 0
    for attack, spec in zip(config.attacks, specs, strict=True):
        assert attack.grid is not None  # LocalRunConfig chỉ nhận mode = grid
        for level in attack.grid.levels:
            session.add(
                m.Run(
                    experiment_id=experiment.id,
                    attack_spec_id=spec.id,
                    level=float(level),
                    params={spec.primary_param.name: float(level)},
                    seed=attack.seed,
                    images_total=len(slice_row.image_ids),
                    status=RunStatus.QUEUED,
                    ordinal=ordinal,
                )
            )
            ordinal += 1
    session.flush()
    audit.record(
        session,
        actor=actor,
        action="experiment.submit",
        entity_type="experiment",
        entity_id=experiment.id,
        after={
            "compute_target": target.name,
            "config_sha256": experiment.config_sha256,
            "runs": ordinal,
            "time_limit_s": limit_s,
        },
    )
    return experiment


def runs_of(session: Session, experiment_id: UUID) -> list[m.Run]:
    return list(
        session.scalars(
            select(m.Run)
            .where(m.Run.experiment_id == experiment_id)
            .order_by(m.Run.ordinal, m.Run.level)
        )
    )


def get(session: Session, experiment_id: UUID) -> m.Experiment:
    experiment = session.get(m.Experiment, experiment_id)
    if experiment is None:
        raise NotFound(f"Không có experiment {experiment_id}")
    return experiment


def _cancel_run(run: m.Run, now: datetime) -> None:
    run.status = RunStatus.CANCELLED
    run.status_reason = reason("cancelled", "Experiment bị hủy")
    run.finished_at = now


def finish_cancelled(session: Session, experiment: m.Experiment, now: datetime) -> None:
    """Experiment đã hủy mà không còn worker giữ lease: run còn `running` thành `cancelled`
    (không để run kẹt ở `running`, mission.md nguyên tắc 6) và bỏ lease."""
    for run in runs_of(session, experiment.id):
        if run.status in (RunStatus.QUEUED, RunStatus.RUNNING):
            _cancel_run(run, now)
    experiment.lease_id = None
    experiment.lease_expires_at = None
    session.flush()


def sweep_cancelled(session: Session, target_id: UUID | None, now: datetime) -> int:
    """Dọn mọi experiment `cancelled` có lease đã hết hạn (của một target, hoặc tất cả khi
    `target_id = None`); trả số experiment đã dọn. `lease()` gọi hàm này mỗi lần worker hỏi job."""
    query = (
        select(m.Experiment)
        .where(
            m.Experiment.status == ExperimentStatus.CANCELLED,
            m.Experiment.lease_id.is_not(None),
            m.Experiment.lease_expires_at < now,
        )
        .with_for_update(skip_locked=True)
    )
    if target_id is not None:
        query = query.where(m.Experiment.compute_target_id == target_id)
    swept = list(session.scalars(query))
    for experiment in swept:
        finish_cancelled(session, experiment, now)
    return len(swept)


def cancel(
    session: Session, *, actor: m.User, experiment_id: UUID, clock: Clock = utcnow
) -> m.Experiment:
    """Experiment `cancelled`; run chưa chạy `cancelled` ngay. Run đang chạy thành `cancelled`
    khi worker báo lại (worker nhận `WorkerDirective.cancel`), hoặc ngay nếu lease đã hết hạn
    (không còn worker nào giữ)."""
    experiment = session.get(m.Experiment, experiment_id, with_for_update=True)
    if experiment is None:
        raise NotFound(f"Không có experiment {experiment_id}")
    if experiment.status not in ACTIVE:
        raise Conflict(f"Experiment đang ở trạng thái {experiment.status}, không hủy được")
    now = clock()
    before = str(experiment.status)
    experiment.status = ExperimentStatus.CANCELLED
    lease_alive = experiment.lease_expires_at is not None and experiment.lease_expires_at > now
    for run in runs_of(session, experiment.id):
        if run.status == RunStatus.QUEUED:
            _cancel_run(run, now)
    if not lease_alive:
        finish_cancelled(session, experiment, now)
    session.flush()
    audit.record(
        session,
        actor=actor,
        action="experiment.cancel",
        entity_type="experiment",
        entity_id=experiment.id,
        before={"status": before},
        after={"status": str(experiment.status)},
    )
    return experiment
