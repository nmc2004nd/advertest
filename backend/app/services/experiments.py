"""Gửi và hủy experiment (requirements.md Phase 3, CLI quản trị `submit`, `experiment cancel`).

Phase này chưa có endpoint công khai: experiment chỉ được tạo qua CLI quản trị phía server.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from advertest_contracts.enums import ExperimentStatus, LimitKind, RunStatus
from advertest_contracts.hashing import sha256_of
from advertest_contracts.models import (
    AttackSpec,
    ExperimentConfig,
    ExperimentCreate,
    InferenceParams,
    Limit,
    StatusReason,
)
from backend.app.db import models as m
from backend.app.services import audit, experiment_config, notifications
from backend.app.services.clock import Clock, utcnow
from backend.app.services.errors import Conflict, Forbidden, Invalid, NotFound, QueueLimitReached
from ml_core.models.wrapper import DEFAULT_INFERENCE_PARAMS
from ml_core.runner.config import DEFAULT_FAILURE_CASES, LocalRunConfig
from ml_core.runner.grid import coarse_to_fine

# Seed trong migration 0002 (`content_id(sha256_of({"protocol": "dev-open"}))`).
DEV_OPEN_PROTOCOL_ID = UUID("2edcdef5-0d3a-5d5f-98ac-b02637fa6718")
ACTIVE = (ExperimentStatus.QUEUED, ExperimentStatus.RUNNING)
MAX_QUEUED_PER_USER = 3  # requirements.md Phase 5, Decisions
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
    return create_experiment(
        session,
        actor=actor,
        config=experiment_config,
        slice_row=slice_row,
        specs=specs,
        params=params,
        failure_cases_per_run=config.failure_cases_per_run,
        clock=clock,
    )


def create_experiment(
    session: Session,
    *,
    actor: m.User,
    config: ExperimentConfig,
    slice_row: m.Slice,
    specs: list[AttackSpec],
    name: str | None = None,
    cloned_from: UUID | None = None,
    params: InferenceParams = DEFAULT_INFERENCE_PARAMS,
    failure_cases_per_run: int = DEFAULT_FAILURE_CASES,
    clock: Clock = utcnow,
) -> m.Experiment:
    """Tạo experiment `queued` và lập danh sách run (mỗi cặp attack, level là một run, theo thứ
    tự trong cấu hình); dùng chung cho CLI `submit` (Phase 3) và `POST /experiments` (Phase 5).
    `name = None`: trigger DB đặt `<model> · <slice> · <ngày UTC>`."""
    now = clock()
    experiment = m.Experiment(
        name=name,
        created_by=actor.id,
        protocol_id=config.protocol_id,
        model_version_id=config.model_version_id,
        slice_id=config.slice_id,
        class_mapping_id=config.class_mapping_id,
        compute_target_id=config.compute_target_id,
        config=config.model_dump(mode="json"),
        config_sha256=sha256_of(config),
        status=ExperimentStatus.QUEUED,
        limit_kind=config.limit.kind,
        limit_value=config.limit.value,
        created_at=now,
        submitted_at=now,
        cloned_from=cloned_from,
        inference_params=params.model_dump(mode="json"),
        failure_cases_per_run=failure_cases_per_run,
    )
    session.add(experiment)
    session.flush()
    ordinal = 0
    for attack, spec in zip(config.attacks, specs, strict=True):
        if attack.grid is None:
            continue  # Phase 7: run của attack tìm ngưỡng do worker tạo động
        # Phase 6 (plan task 24a): trong mỗi attack, level thô trước, mịn sau.
        for level in coarse_to_fine(attack.grid.levels):
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
            "compute_target_id": str(config.compute_target_id),
            "config_sha256": experiment.config_sha256,
            "runs": ordinal,
            "time_limit_s": str(config.limit.value),
            "cloned_from": str(cloned_from) if cloned_from else None,
        },
    )
    return experiment


def create_from_body(
    session: Session, *, actor: m.User, body: ExperimentCreate, clock: Clock = utcnow
) -> m.Experiment:
    """`POST /experiments`: kiểm tra cấu hình (422 có đường dẫn trường), rồi giới hạn số
    experiment đang chờ của người dùng (409 `queue_limit_reached`)."""
    checked = experiment_config.check(session, body)
    # Khóa dòng user: hai request đồng thời của cùng người không cùng lọt qua giới hạn.
    session.execute(select(m.User.id).where(m.User.id == actor.id).with_for_update())
    queued = session.scalar(
        select(func.count())
        .select_from(m.Experiment)
        .where(m.Experiment.created_by == actor.id, m.Experiment.status == ExperimentStatus.QUEUED)
    )
    if (queued or 0) >= MAX_QUEUED_PER_USER:
        raise QueueLimitReached(
            f"Bạn đã có {MAX_QUEUED_PER_USER} experiment đang chờ; hãy chờ một experiment"
            " chạy rồi tạo tiếp"
        )
    config = ExperimentConfig.model_validate(body.model_dump(exclude={"name", "cloned_from"}))
    return create_experiment(
        session,
        actor=actor,
        config=config,
        slice_row=checked.slice,
        specs=checked.specs,
        name=body.name,
        cloned_from=body.cloned_from,
        clock=clock,
    )


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
    from backend.app.services import searches  # tránh import vòng (searches dùng runs_of)

    for run in runs_of(session, experiment.id):
        if run.status in (RunStatus.QUEUED, RunStatus.RUNNING):
            _cancel_run(run, now)
    # Phase 7: kết quả tìm ngưỡng còn tạm thời → stopped_limit (quyết định Group 4).
    searches.finalize_unfinished(session, experiment, lambda: now)
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
    session: Session,
    *,
    actor: m.User,
    experiment_id: UUID,
    owner_only: bool = False,
    clock: Clock = utcnow,
) -> m.Experiment:
    """Experiment `cancelled`; run chưa chạy `cancelled` ngay. Run đang chạy thành `cancelled`
    khi worker báo lại (worker nhận `WorkerDirective.cancel`), hoặc ngay nếu lease đã hết hạn
    (không còn worker nào giữ). `owner_only` (API, `experiment.cancel_own`): chỉ chủ sở hữu hủy
    được; CLI quản trị không có luật này."""
    experiment = session.get(m.Experiment, experiment_id, with_for_update=True)
    if experiment is None:
        raise NotFound(f"Không có experiment {experiment_id}")
    if owner_only and experiment.created_by != actor.id:
        raise Forbidden("Chỉ người tạo experiment mới hủy được")
    if experiment.status not in ACTIVE:
        raise Conflict(f"Experiment đang ở trạng thái {experiment.status}, không hủy được")
    now = clock()
    before = str(experiment.status)
    experiment.status = ExperimentStatus.CANCELLED
    experiment.finished_at = now
    lease_alive = experiment.lease_expires_at is not None and experiment.lease_expires_at > now
    for run in runs_of(session, experiment.id):
        if run.status == RunStatus.QUEUED:
            _cancel_run(run, now)
    if not lease_alive:
        finish_cancelled(session, experiment, now)
    session.flush()
    notifications.enqueue_experiment_finished(session, experiment)
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
