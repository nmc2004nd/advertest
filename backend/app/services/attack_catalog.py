"""Vòng đời spec trong catalog attack (requirements.md Phase R2, mục Catalog attack).

`draft → checking → pending_approval → active`, fail kiểm tra thì `check_failed` (admin chạy lại
được), reviewer từ chối thì về `draft`. Duyệt version mới thì version `active` cũ cùng name chuyển
`retired` trong cùng giao dịch. Người duyệt phải khác người tạo (mission.md nguyên tắc 1).

Adapter và `fixed_params` kiểm bằng registry của worker (`attacks.builders.DEFAULT_REGISTRY`),
nên spec mới chỉ dùng được thuật toán đã có trong repo (nguyên tắc 10). Metadata nằm ngoài
`spec_sha256`: sửa không tạo version mới nhưng ghi audit log (tech-stack.md mục 9, luật 9).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from advertest_contracts.enums import AttackSpecStatus, ToolJobKind
from advertest_contracts.ids import content_id
from advertest_contracts.models import (
    AttackAdapterInfo,
    AttackSpec,
    AttackSpecAdminView,
    AttackSpecCreate,
    AttackSpecMetadata,
    AttackSpecView,
    SpecCheckPayload,
    SpecCheckResult,
    UserRef,
    compute_spec_sha256,
)
from attacks.builders import DEFAULT_REGISTRY, InvalidSpec
from backend.app.db import models as m
from backend.app.services import audit, tool_jobs
from backend.app.services.errors import Conflict, Forbidden, Invalid, NotFound

ENTITY = "attack_spec"


# ---------------------------------------------------------------- đọc


def spec_of(row: m.AttackSpecRow) -> AttackSpec:
    return AttackSpec.model_validate(
        {**row.spec, "id": str(row.id), "spec_sha256": row.spec_sha256}
    )


def metadata_of(row: m.AttackSpecRow) -> AttackSpecMetadata | None:
    return AttackSpecMetadata.model_validate(row.spec_metadata) if row.spec_metadata else None


def public_view(row: m.AttackSpecRow) -> AttackSpecView:
    return AttackSpecView.model_validate(
        {
            **row.spec,
            "id": str(row.id),
            "spec_sha256": row.spec_sha256,
            "metadata": row.spec_metadata,
        }
    )


def admin_views(session: Session, rows: Iterable[m.AttackSpecRow]) -> list[AttackSpecAdminView]:
    rows = list(rows)
    user_ids = {u for row in rows for u in (row.created_by, row.approved_by) if u is not None}
    users = (
        {u.id: u for u in session.scalars(select(m.User).where(m.User.id.in_(user_ids)))}
        if user_ids
        else {}
    )

    def ref(user_id: UUID | None) -> UserRef | None:
        if user_id is None:
            return None
        user = users[user_id]
        return UserRef(id=user.id, full_name=user.full_name)

    return [
        AttackSpecAdminView.model_validate(
            {
                **row.spec,
                "id": str(row.id),
                "spec_sha256": row.spec_sha256,
                "is_active": row.status == AttackSpecStatus.ACTIVE,
                "status": row.status,
                "metadata": row.spec_metadata,
                "check": row.check,
                "created_by": ref(row.created_by),
                "approved_by": ref(row.approved_by),
            }
        )
        for row in rows
    ]


def admin_view(session: Session, row: m.AttackSpecRow) -> AttackSpecAdminView:
    return admin_views(session, [row])[0]


def adapters() -> list[AttackAdapterInfo]:
    return DEFAULT_REGISTRY.adapters()


def list_pending(session: Session) -> list[AttackSpecAdminView]:
    rows = session.scalars(
        select(m.AttackSpecRow)
        .where(m.AttackSpecRow.status == AttackSpecStatus.PENDING_APPROVAL)
        .order_by(m.AttackSpecRow.name, m.AttackSpecRow.version)
    )
    return admin_views(session, rows)


def _row(session: Session, spec_id: UUID) -> m.AttackSpecRow:
    row = session.get(m.AttackSpecRow, spec_id, with_for_update=True)
    if row is None:
        raise NotFound("Không có attack spec này")
    return row


# ---------------------------------------------------------------- tạo, kiểm tra


def _enqueue_check(session: Session, row: m.AttackSpecRow, actor: m.User, now: datetime) -> None:
    row.status = AttackSpecStatus.CHECKING
    tool_jobs.enqueue(
        session, ToolJobKind.SPEC_CHECK, {"spec_id": str(row.id)}, created_by=actor.id, now=now
    )


def create(
    session: Session, *, actor: m.User, body: AttackSpecCreate, now: datetime
) -> AttackSpecAdminView:
    """Spec `draft` rồi `checking` ngay (xếp job `spec_check`).

    422: adapter không có trong registry, `kind` khác builder, `fixed_params` sai schema, version
    không phải version lớn nhất + 1 (name mới: 1). 409: trùng `spec_sha256`.
    """
    sha = compute_spec_sha256(body.body)
    spec = AttackSpec.model_validate(
        {**body.body.model_dump(mode="json"), "id": str(content_id(sha)), "spec_sha256": sha}
    )
    try:
        DEFAULT_REGISTRY.validate(spec)
    except InvalidSpec as exc:
        raise Invalid(f"Spec không hợp lệ với registry: {exc}") from exc
    if session.scalar(select(m.AttackSpecRow.id).where(m.AttackSpecRow.spec_sha256 == sha)):
        raise Conflict("Đã có spec cùng nội dung (trùng spec_sha256)")
    latest = session.scalar(
        select(func.max(m.AttackSpecRow.version)).where(m.AttackSpecRow.name == spec.name)
    )
    expected = (latest or 0) + 1
    if spec.version != expected:
        raise Invalid(f"version của {spec.name} phải là {expected}")
    row = m.AttackSpecRow(
        id=spec.id,
        name=spec.name,
        version=spec.version,
        kind=spec.kind,
        access=spec.access,
        spec=spec.model_dump(mode="json"),
        spec_sha256=sha,
        status=AttackSpecStatus.DRAFT,
        spec_metadata=body.metadata.model_dump(mode="json"),
        created_by=actor.id,
    )
    session.add(row)
    session.flush()
    audit.record(
        session,
        actor=actor,
        action="attack_spec.created",
        entity_type=ENTITY,
        entity_id=row.id,
        after={"name": row.name, "version": row.version, "spec_sha256": sha},
    )
    _enqueue_check(session, row, actor, now)
    session.flush()
    return admin_view(session, row)


def recheck(
    session: Session, *, actor: m.User, spec_id: UUID, now: datetime
) -> AttackSpecAdminView:
    row = _row(session, spec_id)
    if row.status != AttackSpecStatus.CHECK_FAILED:
        raise Conflict(f"Chỉ chạy lại kiểm tra từ check_failed (spec đang ở {row.status})")
    _enqueue_check(session, row, actor, now)
    session.flush()
    return admin_view(session, row)


def check_payload(session: Session, job: m.ToolJob) -> SpecCheckPayload:
    row = session.get(m.AttackSpecRow, UUID(job.payload["spec_id"]))
    if row is None:
        raise NotFound("Spec của job không còn")
    return SpecCheckPayload(spec=spec_of(row))


def apply_check(session: Session, job: m.ToolJob, result: SpecCheckResult) -> None:
    """Kết quả `spec_check`: pass → `pending_approval`, fail → `check_failed`."""
    row = _row(session, UUID(job.payload["spec_id"]))
    if result.spec_id != row.id:
        raise Invalid("result.spec_id khác spec của job")
    if row.status != AttackSpecStatus.CHECKING:
        raise Conflict(f"Spec đang ở trạng thái {row.status}, không chờ kết quả kiểm tra")
    row.check = result.model_dump(mode="json")
    row.status = (
        AttackSpecStatus.PENDING_APPROVAL if result.passed else AttackSpecStatus.CHECK_FAILED
    )
    session.flush()


def check_error(session: Session, job: m.ToolJob, error: str, now: datetime) -> None:
    """Lỗi hạ tầng hoặc mất lease quá số lần: spec chuyển `check_failed`, lỗi ghi vào `check`."""
    row = _row(session, UUID(job.payload["spec_id"]))
    if row.status != AttackSpecStatus.CHECKING or job.leased_by is None:
        return
    result = SpecCheckResult(
        spec_id=row.id,
        items=[],
        passed=False,
        error=error,
        checked_at=now,
        worker_target_id=job.leased_by,
    )
    row.check = result.model_dump(mode="json")
    row.status = AttackSpecStatus.CHECK_FAILED
    session.flush()


# ---------------------------------------------------------------- duyệt


def approve(
    session: Session, *, actor: m.User, spec_id: UUID, now: datetime
) -> AttackSpecAdminView:
    row = _row(session, spec_id)
    if row.status != AttackSpecStatus.PENDING_APPROVAL:
        raise Conflict(f"Chỉ duyệt spec pending_approval (spec đang ở {row.status})")
    if row.created_by == actor.id:
        raise Forbidden("Không được tự duyệt spec do mình tạo")
    previous = session.scalars(
        select(m.AttackSpecRow)
        .where(
            m.AttackSpecRow.name == row.name,
            m.AttackSpecRow.status == AttackSpecStatus.ACTIVE,
            m.AttackSpecRow.id != row.id,
        )
        .with_for_update()
    ).all()
    for old in previous:
        old.status = AttackSpecStatus.RETIRED
    row.status = AttackSpecStatus.ACTIVE
    row.approved_by = actor.id
    row.approved_at = now
    session.flush()
    audit.record(
        session,
        actor=actor,
        action="attack_spec.approved",
        entity_type=ENTITY,
        entity_id=row.id,
        after={"status": row.status.value, "retired": [str(old.id) for old in previous]},
    )
    return admin_view(session, row)


def reject(session: Session, *, actor: m.User, spec_id: UUID, reason: str) -> AttackSpecAdminView:
    row = _row(session, spec_id)
    if row.status != AttackSpecStatus.PENDING_APPROVAL:
        raise Conflict(f"Chỉ từ chối spec pending_approval (spec đang ở {row.status})")
    row.status = AttackSpecStatus.DRAFT
    session.flush()
    audit.record(
        session,
        actor=actor,
        action="attack_spec.rejected",
        entity_type=ENTITY,
        entity_id=row.id,
        after={"status": row.status.value, "reason": reason},
    )
    return admin_view(session, row)


def update_metadata(
    session: Session, *, actor: m.User, spec_id: UUID, metadata: AttackSpecMetadata
) -> AttackSpecAdminView:
    row = _row(session, spec_id)
    before: dict[str, Any] | None = row.spec_metadata
    row.spec_metadata = metadata.model_dump(mode="json")
    session.flush()
    audit.record(
        session,
        actor=actor,
        action="attack_spec.metadata_updated",
        entity_type=ENTITY,
        entity_id=row.id,
        before={"metadata": before},
        after={"metadata": row.spec_metadata},
    )
    return admin_view(session, row)
