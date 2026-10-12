"""Đọc tài nguyên cho wizard tạo experiment (requirements.md Phase 5, API đọc tài nguyên).

Chỉ đọc; mọi hàm trả schema contract. Danh sách sắp xếp ổn định để giao diện không nhảy thứ tự.
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import ARRAY, Text, cast, func, or_, select, tuple_
from sqlalchemy.orm import Session

from advertest_contracts.enums import AttackSpecStatus, ExperimentStatus, ProtocolStatus, Role
from advertest_contracts.models import (
    AttackSpecAdminPage,
    AttackSpecView,
    ClassMappingSummary,
    ComputeTargetPublic,
    DatasetSummary,
    DatasetVersionSummary,
    ModelCheckResult,
    ModelSummary,
    ProtocolSummary,
    SliceSummary,
)
from backend.app.db import models as m
from backend.app.services import attack_catalog
from backend.app.services.errors import Invalid, NotFound

# Worker được coi là online nếu có heartbeat trong 60 giây gần nhất.
ONLINE_WINDOW = timedelta(seconds=60)
LISTED_PROTOCOLS = (ProtocolStatus.ACTIVE, ProtocolStatus.DEV)


def _model_summary(
    version: m.ModelVersion, model: m.Model, owner: m.User | None = None
) -> ModelSummary:
    return ModelSummary(
        id=version.id,
        name=model.name,
        framework=version.framework,
        weights_sha256=version.weights_sha256,
        class_names=version.class_names,
        input_size=version.input_size,
        supports_gradients=version.supports_gradients,
        created_at=version.created_at,
        status=version.status,
        check=ModelCheckResult.model_validate(version.check) if version.check else None,
        archived_at=version.archived_at,
        owner_id=model.created_by,
        owner_name=owner.full_name if owner is not None else None,
    )


def model_visibility(session: Session, actor: m.User) -> Any | None:
    """Điều kiện SQL trên `m.Model` cho model `actor` thấy (Phase R3, người dùng chốt
    2026-10-12); `None` là thấy hết. Admin và reviewer thấy mọi model; engineer thấy model mình
    đăng ký và model của người có vai trò admin (dùng chung)."""
    roles = set(session.scalars(select(m.UserRole.role).where(m.UserRole.user_id == actor.id)))
    if roles & {Role.ADMIN, Role.REVIEWER}:
        return None
    admins = select(m.UserRole.user_id).where(m.UserRole.role == Role.ADMIN)
    return or_(m.Model.created_by == actor.id, m.Model.created_by.in_(admins))


def can_see_model(session: Session, actor: m.User, model_version_id: UUID) -> bool:
    query = (
        select(m.ModelVersion.id)
        .join(m.Model, m.Model.id == m.ModelVersion.model_id)
        .where(m.ModelVersion.id == model_version_id)
    )
    condition = model_visibility(session, actor)
    if condition is not None:
        query = query.where(condition)
    return session.scalar(query) is not None


def list_models(session: Session, actor: m.User | None = None) -> list[ModelSummary]:
    """Mọi model, hoặc chỉ model `actor` thấy được (`model_visibility`)."""
    query = (
        select(m.ModelVersion, m.Model, m.User)
        .join(m.Model, m.Model.id == m.ModelVersion.model_id)
        .outerjoin(m.User, m.User.id == m.Model.created_by)
        .order_by(m.Model.name, m.ModelVersion.created_at.desc(), m.ModelVersion.id)
    )
    condition = model_visibility(session, actor) if actor is not None else None
    if condition is not None:
        query = query.where(condition)
    return [
        _model_summary(version, model, owner) for version, model, owner in session.execute(query)
    ]


def get_model(
    session: Session, model_version_id: UUID, actor: m.User | None = None
) -> ModelSummary:
    """Model không thấy được với `actor` cũng là 404 (không lộ sự tồn tại)."""
    if actor is not None and not can_see_model(session, actor, model_version_id):
        raise NotFound("Không có model này")
    row = session.execute(
        select(m.ModelVersion, m.Model, m.User)
        .join(m.Model, m.Model.id == m.ModelVersion.model_id)
        .outerjoin(m.User, m.User.id == m.Model.created_by)
        .where(m.ModelVersion.id == model_version_id)
    ).one_or_none()
    if row is None:
        raise NotFound("Không có model này")
    version, model, owner = row
    return _model_summary(version, model, owner)


def _version_summary(version: m.DatasetVersion) -> DatasetVersionSummary:
    return DatasetVersionSummary(
        id=version.id,
        dataset_id=version.dataset_id,
        manifest_sha256=version.manifest_sha256,
        num_images=version.num_images,
        class_names=version.class_names,
        created_at=version.created_at,
    )


def list_datasets(session: Session) -> list[DatasetSummary]:
    datasets = session.scalars(select(m.Dataset).order_by(m.Dataset.name, m.Dataset.id)).all()
    versions: dict[UUID, list[DatasetVersionSummary]] = {d.id: [] for d in datasets}
    for version in session.scalars(
        select(m.DatasetVersion).order_by(m.DatasetVersion.created_at.desc(), m.DatasetVersion.id)
    ):
        versions.setdefault(version.dataset_id, []).append(_version_summary(version))
    return [
        DatasetSummary(id=d.id, name=d.name, anonymized=d.anonymized, versions=versions[d.id])
        for d in datasets
    ]


def get_dataset_version(session: Session, dataset_version_id: UUID) -> DatasetVersionSummary:
    version = session.get(m.DatasetVersion, dataset_version_id)
    if version is None:
        raise NotFound("Không có dataset version này")
    return _version_summary(version)


def list_slices(
    session: Session, dataset_version_id: UUID | None = None, disjoint_from: UUID | None = None
) -> list[SliceSummary]:
    """`disjoint_from` (Phase 6, plan task 24b): bỏ slice có ảnh chung với slice đó (kể cả chính
    nó); slice không tồn tại → `NotFound`."""
    query = select(m.Slice).order_by(m.Slice.name, m.Slice.id)
    if dataset_version_id is not None:
        query = query.where(m.Slice.dataset_version_id == dataset_version_id)
    if disjoint_from is not None:
        other = session.get(m.Slice, disjoint_from)
        if other is None:
            raise NotFound(f"Không có slice {disjoint_from}")
        query = query.where(~m.Slice.image_ids.op("&&")(cast(list(other.image_ids), ARRAY(Text))))
    return [
        SliceSummary(
            id=row.id,
            name=row.name,
            dataset_version_id=row.dataset_version_id,
            slice_sha256=row.slice_sha256,
            size=len(row.image_ids),
            seed=row.seed,
            classes=list(row.filter.get("classes", [])),
        )
        for row in session.scalars(query)
    ]


def list_class_mappings(
    session: Session,
    dataset_version_id: UUID | None = None,
    model_version_id: UUID | None = None,
) -> list[ClassMappingSummary]:
    query = select(m.ClassMapping).order_by(m.ClassMapping.mapping_sha256)
    if dataset_version_id is not None:
        query = query.where(m.ClassMapping.dataset_version_id == dataset_version_id)
    if model_version_id is not None:
        query = query.where(m.ClassMapping.model_version_id == model_version_id)
    return [
        ClassMappingSummary(
            id=row.id,
            dataset_version_id=row.dataset_version_id,
            model_version_id=row.model_version_id,
            mapping_sha256=row.mapping_sha256,
            preset=row.mapping.get("preset"),
            classes=dict(row.mapping.get("classes", {})),
        )
        for row in session.scalars(query)
    ]


def list_attack_specs(session: Session) -> list[AttackSpecView]:
    """Chỉ spec `active` (requirements.md Phase 5, Phase R2), kèm metadata."""
    rows = session.scalars(
        select(m.AttackSpecRow)
        .where(m.AttackSpecRow.status == AttackSpecStatus.ACTIVE)
        .order_by(m.AttackSpecRow.kind, m.AttackSpecRow.name, m.AttackSpecRow.version)
    )
    return [attack_catalog.public_view(row) for row in rows]


def list_protocols(session: Session, *, include_retired: bool = False) -> list[ProtocolSummary]:
    """Protocol `active` và `dev`; `retired` chỉ khi `include_retired` (Phase 8)."""
    statuses = set(LISTED_PROTOCOLS) | ({ProtocolStatus.RETIRED} if include_retired else set())
    rows = session.scalars(
        select(m.Protocol)
        .where(m.Protocol.status.in_(statuses))
        .order_by(m.Protocol.name, m.Protocol.version)
    )
    return [
        ProtocolSummary(
            id=row.id,
            name=row.name,
            version=row.version,
            status=row.status,
            body_sha256=row.body_sha256,
        )
        for row in rows
    ]


def is_online(target: m.ComputeTarget, now: datetime) -> bool:
    last = target.last_heartbeat_at
    return last is not None and now - last <= ONLINE_WINDOW


def list_compute_targets(session: Session, now: datetime) -> list[ComputeTargetPublic]:
    """`queue_length`: số experiment đang `queued` trên target."""
    rows = session.execute(
        select(m.Experiment.compute_target_id, func.count())
        .where(m.Experiment.status == ExperimentStatus.QUEUED)
        .group_by(m.Experiment.compute_target_id)
    )
    queued = {target_id: count for target_id, count in rows}
    targets = session.scalars(select(m.ComputeTarget).order_by(m.ComputeTarget.name))
    return [
        ComputeTargetPublic(
            id=target.id,
            name=target.name,
            kind=target.kind,
            gpu_model=target.gpu_model,
            online=is_online(target, now),
            queue_length=queued.get(target.id, 0),
            default_time_limit_s=target.default_time_limit_s,
            max_time_limit_s=target.max_time_limit_s,
        )
        for target in targets
    ]


# ---------------------------------------------------------------- catalog cho admin (Phase 6)


def _encode_spec_cursor(name: str, version: int) -> str:
    raw = json.dumps({"name": name, "version": version}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_spec_cursor(value: str) -> tuple[str, int]:
    try:
        padded = value + "=" * (-len(value) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()))
        name, version = data["name"], data["version"]
    except (ValueError, KeyError, TypeError, binascii.Error) as exc:
        raise Invalid("Cursor không hợp lệ") from exc
    if not isinstance(name, str) or not isinstance(version, int):
        raise Invalid("Cursor không hợp lệ")
    return name, version


def list_attack_specs_admin(
    session: Session, cursor: str | None = None, limit: int = 50
) -> AttackSpecAdminPage:
    """Mọi spec, mọi version, mọi trạng thái (plan task 29, Phase R2); keyset theo
    `(name, version)`."""
    query = select(m.AttackSpecRow)
    if cursor is not None:
        name, version = _decode_spec_cursor(cursor)
        query = query.where(
            tuple_(m.AttackSpecRow.name, m.AttackSpecRow.version) > tuple_(name, version)
        )
    rows = list(
        session.scalars(
            query.order_by(m.AttackSpecRow.name, m.AttackSpecRow.version).limit(limit + 1)
        )
    )
    page, more = rows[:limit], len(rows) > limit
    items = attack_catalog.admin_views(session, page)
    last = page[-1] if page and more else None
    return AttackSpecAdminPage(
        items=items,
        next_cursor=_encode_spec_cursor(last.name, last.version) if last is not None else None,
    )
