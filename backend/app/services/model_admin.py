"""Gỡ model và tạo class mapping qua web (Phase R3, đề xuất contract 002).

- Xóa (`DELETE /models/{id}`) chỉ khi model chưa có experiment hay lượt thử nhanh và không đang
  `checking`; xóa kèm class mapping, cost profile, weights và card trên MinIO. Model đã dùng thì
  chỉ lưu trữ (`archived_at`) để run và report cũ vẫn truy vết được (mission.md nguyên tắc 3).
- Model lưu trữ không chọn được cho experiment mới, thử nhanh hay mapping mới; khôi phục được.
- Class mapping: class gốc phải thuộc dataset version, class đích thuộc model; `preset` suy ra khi
  nội dung trùng một preset của `ml_core.data.mapping.PRESETS`.
- Như đăng ký model: chỉ người đăng ký model hoặc admin được thao tác (403).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session

from advertest_contracts.enums import ModelStatus, Role
from advertest_contracts.ids import content_id
from advertest_contracts.models import (
    ClassMapping,
    ClassMappingBody,
    ClassMappingCreate,
    ClassMappingSummary,
    ModelSummary,
    compute_mapping_sha256,
)
from backend.app import storage
from backend.app.db import models as m
from backend.app.services import audit, catalog
from backend.app.services.errors import Conflict, Forbidden, Invalid, NotFound
from ml_core.data.mapping import PRESETS


def _owned_version(session: Session, actor: m.User, model_id: UUID) -> m.ModelVersion:
    version = session.get(m.ModelVersion, model_id, with_for_update=True)
    if version is None:
        raise NotFound("Không có model này")
    model = session.get(m.Model, version.model_id)
    admin = session.scalar(
        select(m.UserRole.user_id).where(
            m.UserRole.user_id == actor.id, m.UserRole.role == Role.ADMIN
        )
    )
    if (model is None or model.created_by != actor.id) and admin is None:
        raise Forbidden("Chỉ người đăng ký model hoặc admin được thao tác trên model này")
    return version


def _used(session: Session, model_id: UUID) -> bool:
    experiment = exists().where(m.Experiment.model_version_id == model_id)
    quick_try = exists().where(m.QuickTry.model_version_id == model_id)
    return bool(session.scalar(select(experiment | quick_try)))


def delete_model(
    session: Session, *, actor: m.User, model_id: UUID, buckets: storage.Buckets
) -> None:
    version = _owned_version(session, actor, model_id)
    if version.status == ModelStatus.CHECKING:
        raise Conflict("Model đang được kiểm tra; chờ kiểm tra xong rồi xóa")
    if _used(session, version.id):
        raise Conflict("Model đã dùng trong experiment hoặc thử nhanh; chỉ lưu trữ được")
    model = session.get(m.Model, version.model_id)
    mappings = session.scalars(
        select(m.ClassMapping.mapping_sha256).where(m.ClassMapping.model_version_id == version.id)
    ).all()
    session.execute(delete(m.ClassMapping).where(m.ClassMapping.model_version_id == version.id))
    session.execute(delete(m.CostProfile).where(m.CostProfile.model_version_id == version.id))
    audit.record(
        session,
        actor=actor,
        action="model.deleted",
        entity_type="model_version",
        entity_id=version.id,
        before={
            "name": model.name if model is not None else None,
            "framework": version.framework,
            "weights_sha256": version.weights_sha256,
            "status": version.status.value,
            "class_mappings": list(mappings),
        },
    )
    sha = version.weights_sha256
    session.delete(version)
    session.flush()
    if model is not None and not session.scalar(
        select(exists().where(m.ModelVersion.model_id == model.id))
    ):
        session.delete(model)
        session.flush()
    # Object MinIO xóa sau cùng: lỗi DB ở trên thì weights vẫn còn.
    for key in (storage.weights_key(sha), storage.card_key(sha)):
        if buckets.models.exists(key):
            buckets.models.delete(key)
    for mapping_sha in mappings:
        if buckets.datasets.exists(storage.mapping_key(mapping_sha)):
            buckets.datasets.delete(storage.mapping_key(mapping_sha))


def set_archived(
    session: Session, *, actor: m.User, model_id: UUID, archived: bool, now: datetime
) -> ModelSummary:
    version = _owned_version(session, actor, model_id)
    if (version.archived_at is not None) == archived:
        raise Conflict("Model đã được lưu trữ" if archived else "Model chưa được lưu trữ")
    before = version.archived_at
    version.archived_at = now if archived else None
    audit.record(
        session,
        actor=actor,
        action="model.archived" if archived else "model.restored",
        entity_type="model_version",
        entity_id=version.id,
        before={"archived_at": before.isoformat() if before else None},
        after={"archived_at": version.archived_at.isoformat() if version.archived_at else None},
    )
    session.flush()
    return catalog.get_model(session, version.id)


def _preset(body: ClassMappingCreate) -> str | None:
    for name, preset in PRESETS.items():
        if preset.classes == body.classes and preset.difficulty == body.difficulty:
            return name
    return None


def create_mapping(
    session: Session, *, actor: m.User, body: ClassMappingCreate
) -> ClassMappingSummary:
    version = _owned_version(session, actor, body.model_version_id)
    if version.archived_at is not None:
        raise Conflict("Model đã lưu trữ; khôi phục trước khi thêm class mapping")
    dataset_version = session.get(m.DatasetVersion, body.dataset_version_id)
    if dataset_version is None:
        raise Invalid("Không có dataset version này")
    unknown_sources = sorted(set(body.classes) - set(dataset_version.class_names))
    if unknown_sources:
        raise Invalid(f"Class không có trong dataset: {', '.join(unknown_sources)}")
    targets = {target for target in body.classes.values() if target is not None}
    unknown_targets = sorted(targets - set(version.class_names))
    if unknown_targets:
        raise Invalid(f"Class không có trong model: {', '.join(unknown_targets)}")
    mapping = ClassMappingBody(
        dataset_version_sha256=dataset_version.manifest_sha256,
        model_id=version.id,
        preset=_preset(body),
        classes=body.classes,
        difficulty=body.difficulty,
    )
    sha = compute_mapping_sha256(mapping)
    if session.scalar(select(m.ClassMapping.id).where(m.ClassMapping.mapping_sha256 == sha)):
        raise Conflict("Đã có class mapping giống hệt cho model và dataset này")
    row = m.ClassMapping(
        id=content_id(sha),
        dataset_version_id=dataset_version.id,
        model_version_id=version.id,
        mapping=ClassMapping(
            **mapping.model_dump(), id=content_id(sha), mapping_sha256=sha
        ).model_dump(mode="json"),
        mapping_sha256=sha,
    )
    session.add(row)
    session.flush()
    audit.record(
        session,
        actor=actor,
        action="class_mapping.created",
        entity_type="class_mapping",
        entity_id=row.id,
        after={"model_version_id": str(version.id), "preset": mapping.preset},
    )
    return ClassMappingSummary(
        id=row.id,
        dataset_version_id=row.dataset_version_id,
        model_version_id=row.model_version_id,
        mapping_sha256=sha,
        preset=mapping.preset,
        classes=mapping.classes,
    )
