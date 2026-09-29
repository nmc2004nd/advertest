"""Đăng ký model, dataset version, slice, mapping từ `LocalStore` vào DB và MinIO
(requirements.md Phase 3, `import-local`; plan.md task 12).

- id trong DB là `content_id` của hash (như `LocalStore`), nên cấu hình `LocalRunConfig` dùng
  được nguyên id sau khi import.
- Chỉ upload ảnh thuộc các slice được đăng ký (không nhân đôi cả dataset).
- Chạy lại nhiều lần an toàn: bản ghi đã có được giữ nguyên, object đã có trong MinIO bỏ qua.
- Chỉ admin được đăng ký (weights nạp bằng pickle); người gọi kiểm tra bằng
  `audit.require_admin` trước.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from advertest_contracts.hashing import sha256_of
from advertest_contracts.ids import content_id
from advertest_contracts.models import ClassMapping, DatasetManifest, ModelCard, SliceSpec
from backend.app import storage
from backend.app.db import models as m
from backend.app.services import audit
from backend.app.services.errors import Invalid
from ml_core.data.dataset import dataset_roots, load_manifest
from ml_core.data.dataset import manifest_key as local_manifest_key
from ml_core.data.mapping import load_mapping
from ml_core.data.mapping import mapping_key as local_mapping_key
from ml_core.data.slice import load_slice
from ml_core.data.slice import slice_key as local_slice_key
from ml_core.models.register import card_key as local_card_key
from ml_core.models.register import load_card
from ml_core.models.register import weights_key as local_weights_key
from ml_core.store import ArtifactStore, resolve_id
from ml_core.store.index import IdKind


@dataclass
class ImportReport:
    models: list[UUID] = field(default_factory=list)
    datasets: list[UUID] = field(default_factory=list)
    mappings: list[UUID] = field(default_factory=list)
    slices: list[UUID] = field(default_factory=list)
    images_uploaded: int = 0
    images_present: int = 0  # đã có trong MinIO từ lần import trước

    def summary(self) -> dict[str, object]:
        return {
            "models": [str(i) for i in self.models],
            "datasets": [str(i) for i in self.datasets],
            "mappings": [str(i) for i in self.mappings],
            "slices": [str(i) for i in self.slices],
            "images_uploaded": self.images_uploaded,
            "images_present": self.images_present,
        }


def _ids(store: ArtifactStore, kind: IdKind) -> list[tuple[UUID, str]]:
    prefix = f"index/{kind}/"
    ids = [UUID(key.removeprefix(prefix)) for key in store.list(prefix)]
    return [(id_, resolve_id(store, kind, id_)) for id_ in ids]


def _upload(target: ArtifactStore, key: str, data: bytes) -> None:
    target.put(key, data)  # MinioStore: cùng nội dung là no-op, khác nội dung báo xung đột


def _model(
    session: Session, local: ArtifactStore, buckets: storage.Buckets, actor: m.User, sha: str
) -> ModelCard:
    card = load_card(local, sha)
    _upload(buckets.models, storage.weights_key(sha), local.get(local_weights_key(sha)))
    _upload(buckets.models, storage.card_key(sha), local.get(local_card_key(sha)))
    if session.get(m.ModelVersion, card.id) is None:
        model = session.scalar(select(m.Model).where(m.Model.name == card.name))
        if model is None:
            model = m.Model(name=card.name, created_by=actor.id)
            session.add(model)
            session.flush()
        session.add(
            m.ModelVersion(
                id=card.id,
                model_id=model.id,
                weights_sha256=card.weights_sha256,
                weights_uri=f"s3://{storage.BUCKET_MODELS}/{storage.weights_key(sha)}",
                framework=card.framework,
                class_names=card.class_names,
                input_size=card.input_size,
                supports_gradients=card.supports_gradients,
            )
        )
        session.flush()
    return card


def _dataset(
    session: Session, local: ArtifactStore, buckets: storage.Buckets, actor: m.User, sha: str
) -> DatasetManifest:
    manifest = load_manifest(local, sha)
    _upload(buckets.datasets, storage.manifest_key(sha), local.get(local_manifest_key(sha)))
    version_id = content_id(sha)
    if session.get(m.DatasetVersion, version_id) is None:
        name = f"{manifest.source.format}-{manifest.source.split}"
        dataset = session.scalar(select(m.Dataset).where(m.Dataset.name == name))
        if dataset is None:
            dataset = m.Dataset(name=name, created_by=actor.id)
            session.add(dataset)
            session.flush()
        session.add(
            m.DatasetVersion(
                id=version_id,
                dataset_id=dataset.id,
                manifest_sha256=sha,
                manifest_uri=f"s3://{storage.BUCKET_DATASETS}/{storage.manifest_key(sha)}",
                num_images=len(manifest.images),
                class_names=manifest.categories,
            )
        )
        session.flush()
    return manifest


def _mapping(
    session: Session, local: ArtifactStore, buckets: storage.Buckets, sha: str
) -> ClassMapping:
    mapping = load_mapping(local, sha)
    _upload(buckets.datasets, storage.mapping_key(sha), local.get(local_mapping_key(sha)))
    dataset_version_id = content_id(mapping.dataset_version_sha256)
    if session.get(m.DatasetVersion, dataset_version_id) is None:
        raise Invalid(f"Mapping {mapping.id} thuộc dataset chưa đăng ký")
    if session.get(m.ModelVersion, mapping.model_id) is None:
        raise Invalid(f"Mapping {mapping.id} thuộc model chưa đăng ký")
    if session.get(m.ClassMapping, mapping.id) is None:
        session.add(
            m.ClassMapping(
                id=mapping.id,
                dataset_version_id=dataset_version_id,
                model_version_id=mapping.model_id,
                mapping=mapping.model_dump(mode="json"),
                mapping_sha256=mapping.mapping_sha256,
            )
        )
        session.flush()
    return mapping


def _slice_images(
    local: ArtifactStore,
    buckets: storage.Buckets,
    manifest: DatasetManifest,
    slice_spec: SliceSpec,
    report: ImportReport,
) -> None:
    """Upload ảnh thuộc slice, khóa theo sha256; đọc từ thư mục gốc lúc import (kiểm tra sha256)."""
    dataset_sha = slice_spec.dataset_version_sha256
    roots = dataset_roots(local, dataset_sha)
    entries = {img.image_id: img for img in manifest.images}
    for image_id in slice_spec.image_ids:
        entry = entries[image_id]
        key = storage.image_key(dataset_sha, entry.sha256)
        if buckets.datasets.exists(key):
            report.images_present += 1
            continue
        for root in roots:
            path = root / entry.file_name
            if path.is_file():
                data = path.read_bytes()
                if hashlib.sha256(data).hexdigest() == entry.sha256:
                    buckets.datasets.put(key, data)
                    report.images_uploaded += 1
                    break
        else:
            raise Invalid(
                f"Không tìm thấy ảnh {entry.file_name} đúng sha256 trong: {[str(r) for r in roots]}"
            )


def _slice(
    session: Session,
    local: ArtifactStore,
    buckets: storage.Buckets,
    sha: str,
    report: ImportReport,
) -> SliceSpec:
    slice_spec = load_slice(local, sha)
    dataset_sha = slice_spec.dataset_version_sha256
    dataset_version_id = content_id(dataset_sha)
    if session.get(m.DatasetVersion, dataset_version_id) is None:
        raise Invalid(f"Slice {slice_spec.id} thuộc dataset chưa đăng ký")
    _slice_images(local, buckets, load_manifest(local, dataset_sha), slice_spec, report)
    _upload(buckets.datasets, storage.slice_key(sha), local.get(local_slice_key(sha)))
    if session.get(m.Slice, slice_spec.id) is None:
        session.add(
            m.Slice(
                id=slice_spec.id,
                dataset_version_id=dataset_version_id,
                name=f"slice-{sha[:12]}",
                filter=slice_spec.filter.model_dump(mode="json"),
                seed=slice_spec.seed,
                image_ids=slice_spec.image_ids,
                image_ids_sha256=slice_spec.image_ids_sha256,
                slice_sha256=slice_spec.slice_sha256,
            )
        )
        session.flush()
    return slice_spec


def import_local(
    session: Session, local: ArtifactStore, buckets: storage.Buckets, *, actor: m.User
) -> ImportReport:
    """Đăng ký mọi model, dataset, mapping, slice trong chỉ mục của `local`."""
    report = ImportReport()
    for id_, sha in _ids(local, "model"):
        card = _model(session, local, buckets, actor, sha)
        if card.id != id_:
            raise Invalid(f"Chỉ mục model {id_} trỏ tới card {card.id}")
        report.models.append(card.id)
    for id_, sha in _ids(local, "dataset"):
        manifest = _dataset(session, local, buckets, actor, sha)
        if sha256_of(manifest) != sha:
            raise Invalid(f"Manifest của dataset {id_} không khớp hash")
        report.datasets.append(id_)
    for _, sha in _ids(local, "mapping"):
        report.mappings.append(_mapping(session, local, buckets, sha).id)
    for _, sha in _ids(local, "slice"):
        report.slices.append(_slice(session, local, buckets, sha, report).id)
    audit.record(
        session,
        actor=actor,
        action="registry.import_local",
        entity_type="registry",
        entity_id=None,
        after=report.summary(),
    )
    return report
