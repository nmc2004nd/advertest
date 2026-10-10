"""API nội bộ của job công cụ (`/internal/worker/tool-*`): nối hàng đợi `tool_jobs` với service
của từng loại job (requirements.md Phase R2, mục Job công cụ).

Chỉ token worker gọi được các hàm này (mission.md nguyên tắc 3). Kiểm tra fail vẫn là `report`
với `passed = false`; `error` là lỗi hạ tầng và đưa đối tượng của job sang trạng thái lỗi.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from advertest_contracts.enums import ToolJobKind
from advertest_contracts.models import (
    SpecCheckReport,
    ToolJobBundle,
    ToolJobResult,
    ToolLease,
    ToolPayload,
)
from backend.app import storage
from backend.app.db import models as m
from backend.app.presign import Presigner
from backend.app.services import attack_catalog, tool_jobs
from backend.app.services.errors import Invalid


def _on_error(session: Session, job: m.ToolJob, error: str, now: datetime) -> None:
    if job.kind == ToolJobKind.SPEC_CHECK:
        attack_catalog.check_error(session, job, error, now)


def _on_lost(session: Session, job: m.ToolJob, now: datetime) -> None:
    _on_error(session, job, job.error or tool_jobs.LOST_LEASE_ERROR, now)


def lease(session: Session, target: m.ComputeTarget, now: datetime) -> ToolLease | None:
    job = tool_jobs.lease(session, target, now, _on_lost)
    if job is None:
        return None
    assert job.lease_id is not None and job.lease_expires_at is not None
    return ToolLease(
        kind=job.kind, job_id=job.id, lease_id=job.lease_id, lease_expires_at=job.lease_expires_at
    )


def bundle(
    session: Session,
    target: m.ComputeTarget,
    job_id: UUID,
    buckets: storage.Buckets,
    presigner: Presigner,
    now: datetime,
) -> ToolJobBundle:
    """Payload của job, presigned URL hết hạn sau 15 phút (gọi lại để lấy URL mới)."""
    job = tool_jobs.running(session, target, job_id)
    payload: ToolPayload
    if job.kind == ToolJobKind.SPEC_CHECK:
        payload = attack_catalog.check_payload(session, job)
    else:
        raise Invalid(f"Loại job {job.kind} chưa hỗ trợ")
    return ToolJobBundle(
        job_id=job.id,
        payload=payload,
        expires_at=now + timedelta(seconds=presigner.expires_s),
    )


def submit(
    session: Session,
    target: m.ComputeTarget,
    job_id: UUID,
    body: ToolJobResult,
    buckets: storage.Buckets,
    now: datetime,
) -> None:
    job = tool_jobs.leased(session, target, job_id, body.lease_id)
    if body.error is not None:
        tool_jobs.finish(job, now, error=body.error)
        _on_error(session, job, body.error, now)
        return
    report = body.report
    assert report is not None  # ToolJobResult: đúng một trong report hoặc error
    if report.kind != job.kind:
        raise Invalid(f"report.kind = {report.kind} khác loại job {job.kind}")
    if isinstance(report, SpecCheckReport):
        attack_catalog.apply_check(session, job, report.result)
    tool_jobs.finish(job, now, result=report.model_dump(mode="json"))
    session.flush()
