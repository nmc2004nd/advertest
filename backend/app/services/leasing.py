"""Lease experiment cho worker (requirements.md Phase 3, `POST /lease`, `POST /heartbeat`).

- Thứ tự đến trước (`submitted_at`), chỉ experiment của target gắn với token.
- Lease 60 giây; mỗi lần lease có `lease_id` mới. Request của worker mang `lease_id`; khác lease
  hiện tại (lease đã hết hạn và được cấp cho worker khác) → `Conflict` (API trả 409).
- `FOR UPDATE SKIP LOCKED`: hai worker gọi `lease` cùng lúc không nhận cùng một experiment.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, object_session

from advertest_contracts.enums import ExperimentStatus, LimitKind
from advertest_contracts.models import WorkerDirective
from backend.app.db import models as m
from backend.app.services.clock import Clock, utcnow
from backend.app.services.errors import Conflict, Forbidden, NotFound

LEASE_SECONDS = 60


def touch_target(session: Session, target: m.ComputeTarget, now: datetime) -> None:
    """Ghi heartbeat của target nếu lấy được khóa dòng ngay; worker khác đang giữ khóa thì bỏ qua
    (nó cũng vừa ghi heartbeat). Không để các worker cùng target chờ nhau."""
    locked = session.scalar(
        select(m.ComputeTarget.id)
        .where(m.ComputeTarget.id == target.id)
        .with_for_update(skip_locked=True)
    )
    if locked is not None:
        target.last_heartbeat_at = now


def lease(session: Session, target: m.ComputeTarget, clock: Clock = utcnow) -> m.Experiment | None:
    """Experiment `queued` cũ nhất của target, hoặc experiment `running` có lease đã hết hạn;
    `None` khi không có (API trả 204)."""
    now = clock()
    experiment = session.scalar(
        select(m.Experiment)
        .where(
            m.Experiment.compute_target_id == target.id,
            or_(
                m.Experiment.status == ExperimentStatus.QUEUED,
                and_(
                    m.Experiment.status == ExperimentStatus.RUNNING,
                    or_(
                        m.Experiment.lease_expires_at.is_(None),
                        m.Experiment.lease_expires_at < now,
                    ),
                ),
            ),
        )
        .order_by(m.Experiment.submitted_at, m.Experiment.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    touch_target(session, target, now)
    if experiment is None:
        session.flush()
        return None
    experiment.status = ExperimentStatus.RUNNING
    experiment.lease_id = uuid4()
    experiment.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    session.flush()
    return experiment


def leased_experiment(
    session: Session, target: m.ComputeTarget, experiment_id: UUID, lease_id: UUID
) -> m.Experiment:
    """Experiment mà worker đang giữ lease (khóa dòng tới hết transaction)."""
    experiment = session.get(m.Experiment, experiment_id, with_for_update=True)
    if experiment is None:
        raise NotFound(f"Không có experiment {experiment_id}")
    if experiment.compute_target_id != target.id:
        raise Forbidden("Experiment thuộc compute target khác")
    if experiment.lease_id != lease_id:
        raise Conflict("lease_id không còn hiệu lực (experiment đã được lease cho worker khác)")
    return experiment


def extend(experiment: m.Experiment, target: m.ComputeTarget, clock: Clock = utcnow) -> None:
    now = clock()
    experiment.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    session = object_session(experiment)
    if session is not None:
        touch_target(session, target, now)


def remaining_seconds(experiment: m.Experiment) -> Decimal | None:
    if experiment.limit_kind != LimitKind.TIME:
        return None
    return max(Decimal(0), experiment.limit_value - experiment.processing_seconds_used)


def directive(experiment: m.Experiment) -> WorkerDirective:
    remaining = remaining_seconds(experiment)
    seconds = float(remaining) if remaining is not None else None
    if experiment.status == ExperimentStatus.CANCELLED:
        return WorkerDirective(action="cancel", remaining_seconds=seconds)
    if remaining is not None and remaining <= 0:
        return WorkerDirective(action="stop_limit", remaining_seconds=0.0)
    return WorkerDirective(action="continue", remaining_seconds=seconds)


def heartbeat(
    session: Session,
    target: m.ComputeTarget,
    experiment_id: UUID,
    lease_id: UUID,
    clock: Clock = utcnow,
) -> WorkerDirective:
    experiment = leased_experiment(session, target, experiment_id, lease_id)
    if experiment.status not in (ExperimentStatus.RUNNING, ExperimentStatus.CANCELLED):
        raise Conflict(f"Experiment đã ở trạng thái {experiment.status}")
    extend(experiment, target, clock)
    session.flush()
    return directive(experiment)
