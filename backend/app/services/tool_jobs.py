"""Hàng đợi job công cụ của worker `--tools` (requirements.md Phase R2, mục Job công cụ).

- Job không gắn với compute target: mọi worker trên máy `local` đều lease được (job công cụ chỉ
  chạy trên máy local; máy thuê thuộc Phase 9).
- Thứ tự lease: `quick_try` trước, rồi `model_check` và `spec_check`, mỗi loại theo thứ tự tạo.
- Lease 60 giây, mỗi heartbeat gia hạn 60 giây; mỗi lần lease có `lease_id` mới. Request mang
  `lease_id` cũ → `Conflict` (409).
- Job mất lease được xếp lại (lease lại ở lần gọi kế tiếp); mất lease lần thứ 3 thì `failed`,
  và `on_failed` chuyển đối tượng của job (spec, model, lượt thử nhanh) sang trạng thái lỗi.

Module này không biết nội dung từng loại job; `tool_dispatch` nối job với service tương ứng.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from advertest_contracts.enums import ComputeKind, ToolJobKind, ToolJobStatus
from backend.app.db import models as m
from backend.app.services.errors import Conflict, Forbidden, NotFound
from backend.app.services.leasing import touch_target

LEASE_SECONDS = 60
# Lease tối đa 3 lần: lần đầu và 2 lần xếp lại.
MAX_ATTEMPTS = 3
LOST_LEASE_ERROR = (
    f"Worker mất lease {MAX_ATTEMPTS} lần (không heartbeat trong {LEASE_SECONDS} giây)"
)

FailHook = Callable[[Session, m.ToolJob, datetime], None]


def enqueue(
    session: Session,
    kind: ToolJobKind,
    payload: dict[str, Any],
    *,
    created_by: UUID | None,
    now: datetime,
) -> m.ToolJob:
    job = m.ToolJob(
        kind=kind,
        payload=payload,
        status=ToolJobStatus.QUEUED,
        attempts=0,
        created_by=created_by,
        created_at=now,
    )
    session.add(job)
    session.flush()
    return job


def _leasable(now: datetime) -> Any:
    return or_(
        m.ToolJob.status == ToolJobStatus.QUEUED,
        (m.ToolJob.status == ToolJobStatus.RUNNING) & (m.ToolJob.lease_expires_at < now),
    )


def finish(
    job: m.ToolJob,
    now: datetime,
    *,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    job.status = ToolJobStatus.FAILED if error is not None else ToolJobStatus.COMPLETED
    job.result = result
    job.error = error
    job.finished_at = now
    job.lease_id = None
    job.lease_expires_at = None


def lease(
    session: Session, target: m.ComputeTarget, now: datetime, on_failed: FailHook
) -> m.ToolJob | None:
    """Job kế tiếp theo thứ tự lease; `None` khi không có (API trả 204). Job hết lease ở lần thứ
    `MAX_ATTEMPTS` được chốt `failed` trên đường đi."""
    touch_target(session, target, now)
    if target.kind != ComputeKind.LOCAL:
        session.flush()
        return None
    while True:
        job = session.scalar(
            select(m.ToolJob)
            .where(_leasable(now))
            .order_by(
                case((m.ToolJob.kind == ToolJobKind.QUICK_TRY, 0), else_=1),
                m.ToolJob.created_at,
                m.ToolJob.id,
            )
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job is None:
            session.flush()
            return None
        if job.status == ToolJobStatus.RUNNING and job.attempts >= MAX_ATTEMPTS:
            finish(job, now, error=LOST_LEASE_ERROR)
            on_failed(session, job, now)
            session.flush()
            continue
        job.status = ToolJobStatus.RUNNING
        job.lease_id = uuid4()
        job.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
        job.leased_by = target.id
        job.attempts += 1
        session.flush()
        return job


def _job(session: Session, job_id: UUID) -> m.ToolJob:
    job = session.get(m.ToolJob, job_id, with_for_update=True)
    if job is None:
        raise NotFound(f"Không có job công cụ {job_id}")
    return job


def running(session: Session, target: m.ComputeTarget, job_id: UUID) -> m.ToolJob:
    """Job đang chạy mà target này giữ lease (để dựng bundle)."""
    job = _job(session, job_id)
    if job.status != ToolJobStatus.RUNNING:
        raise Conflict(f"Job công cụ đang ở trạng thái {job.status}")
    if job.leased_by != target.id:
        raise Forbidden("Job công cụ đang được lease cho compute target khác")
    return job


def leased(session: Session, target: m.ComputeTarget, job_id: UUID, lease_id: UUID) -> m.ToolJob:
    """Job mà worker đang giữ đúng lease (khóa dòng tới hết transaction)."""
    job = _job(session, job_id)
    if job.status != ToolJobStatus.RUNNING or job.lease_id != lease_id:
        raise Conflict("lease_id không còn hiệu lực (job đã được lease lại hoặc đã kết thúc)")
    if job.leased_by != target.id:
        raise Forbidden("Job công cụ đang được lease cho compute target khác")
    return job


def heartbeat(
    session: Session, target: m.ComputeTarget, job_id: UUID, lease_id: UUID, now: datetime
) -> None:
    job = leased(session, target, job_id, lease_id)
    job.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    touch_target(session, target, now)
    session.flush()
