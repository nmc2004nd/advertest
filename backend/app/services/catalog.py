"""Đọc tài nguyên cho wizard tạo experiment (requirements.md Phase 5, API đọc tài nguyên).

Chỉ đọc; mọi hàm trả schema contract. Danh sách sắp xếp ổn định để giao diện không nhảy thứ tự.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import ARRAY, Text, cast, func, select
from sqlalchemy.orm import Session

from advertest_contracts.enums import ExperimentStatus, ProtocolStatus
from advertest_contracts.models import (
    AttackSpec,
    ClassMappingSummary,
    ComputeTargetPublic,
    DatasetSummary,
    DatasetVersionSummary,
    ModelSummary,
    ProtocolSummary,
    SliceSummary,
)
from backend.app.db import models as m
from backend.app.services.errors import NotFound

# Worker được coi là online nếu có heartbeat trong 60 giây gần nhất.
ONLINE_WINDOW = timedelta(seconds=60)
LISTED_PROTOCOLS = (ProtocolStatus.ACTIVE, ProtocolStatus.DEV)


def _model_summary(version: m.ModelVersion, model: m.Model) -> ModelSummary:
    return ModelSummary(
        id=version.id,
        name=model.name,
        framework=version.framework,
        weights_sha256=version.weights_sha256,
        class_names=version.class_names,
        input_size=version.input_size,
        supports_gradients=version.supports_gradients,
        created_at=version.created_at,
    )


def list_models(session: Session) -> list[ModelSummary]:
    rows = session.execute(
        select(m.ModelVersion, m.Model)
        .join(m.Model, m.Model.id == m.ModelVersion.model_id)
        .order_by(m.Model.name, m.ModelVersion.created_at.desc(), m.ModelVersion.id)
    )
    return [_model_summary(version, model) for version, model in rows]


def get_model(session: Session, model_version_id: UUID) -> ModelSummary:
    row = session.execute(
        select(m.ModelVersion, m.Model)
        .join(m.Model, m.Model.id == m.ModelVersion.model_id)
        .where(m.ModelVersion.id == model_version_id)
    ).one_or_none()
    if row is None:
        raise NotFound("Không có model này")
    version, model = row
    return _model_summary(version, model)


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


def list_attack_specs(session: Session) -> list[AttackSpec]:
    """Chỉ spec đang hoạt động (requirements.md Phase 5)."""
    rows = session.scalars(
        select(m.AttackSpecRow)
        .where(m.AttackSpecRow.is_active)
        .order_by(m.AttackSpecRow.kind, m.AttackSpecRow.name, m.AttackSpecRow.version)
    )
    return [
        AttackSpec.model_validate({**row.spec, "id": str(row.id), "spec_sha256": row.spec_sha256})
        for row in rows
    ]


def list_protocols(session: Session) -> list[ProtocolSummary]:
    """Protocol `active` và `dev` (không trả `retired`)."""
    rows = session.scalars(
        select(m.Protocol)
        .where(m.Protocol.status.in_(LISTED_PROTOCOLS))
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
