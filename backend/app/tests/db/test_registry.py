"""Service registry: import-local vào DB và MinIO (requirements.md Phase 3, CLI quản trị)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app import storage
from backend.app.db import models as m
from backend.app.services import registry
from backend.app.services.errors import Invalid
from backend.app.storage import Buckets

from .local_store_factory import LocalData, build_local_store

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def local(tmp_path_factory: pytest.TempPathFactory) -> LocalData:
    return build_local_store(tmp_path_factory.mktemp("registry"))


def test_import_local_registers_everything_with_content_ids(
    db: Session, admin: m.User, local: LocalData, buckets: Buckets
) -> None:
    report = registry.import_local(db, local.store, buckets, actor=admin)
    assert report.models == [local.card.id]
    assert report.slices == [local.slice.id] and report.mappings == [local.mapping.id]

    version = db.get(m.ModelVersion, local.card.id)
    assert version is not None and version.weights_sha256 == local.card.weights_sha256
    assert version.supports_gradients is True
    slice_row = db.get(m.Slice, local.slice.id)
    assert slice_row is not None and slice_row.image_ids == local.slice.image_ids
    assert slice_row.slice_sha256 == local.slice.slice_sha256
    mapping_row = db.get(m.ClassMapping, local.mapping.id)
    assert mapping_row is not None and mapping_row.model_version_id == local.card.id

    sha = local.card.weights_sha256
    assert buckets.models.exists(storage.weights_key(sha))
    assert buckets.models.exists(storage.card_key(sha))
    dataset_sha = local.slice.dataset_version_sha256
    assert buckets.datasets.exists(storage.manifest_key(dataset_sha))
    assert buckets.datasets.exists(storage.slice_key(local.slice.slice_sha256))
    assert buckets.datasets.exists(storage.mapping_key(local.mapping.mapping_sha256))

    audit = db.scalars(
        select(m.AuditLog).where(
            m.AuditLog.action == "registry.import_local", m.AuditLog.actor_id == admin.id
        )
    ).one()
    assert audit.after is not None and audit.after["slices"] == [str(local.slice.id)]


def test_only_slice_images_uploaded_and_reimport_is_idempotent(
    db: Session, admin: m.User, local: LocalData, buckets: Buckets
) -> None:
    registry.import_local(db, local.store, buckets, actor=admin)
    dataset_sha = local.slice.dataset_version_sha256
    images = buckets.datasets.list(f"{dataset_sha}/images/")
    by_id = {img.image_id: img.sha256 for img in local.manifest.images}
    expected = sorted(storage.image_key(dataset_sha, by_id[i]) for i in local.slice.image_ids)
    assert images == expected and len(local.manifest.images) == 4

    again = registry.import_local(db, local.store, buckets, actor=admin)
    assert again.images_uploaded == 0 and again.images_present == 2
    assert db.scalars(select(m.ModelVersion).where(m.ModelVersion.id == local.card.id)).all()


def test_missing_image_file_is_reported(
    db: Session, admin: m.User, buckets: Buckets, tmp_path: Path
) -> None:
    other = build_local_store(tmp_path, image_size=(161, 40))  # ảnh khác, chưa có trong MinIO
    # Làm hỏng ảnh gốc của slice ở thư mục nguồn.
    first = other.slice.image_ids[0]
    entry = next(img for img in other.manifest.images if img.image_id == first)
    (tmp_path / "kitti" / entry.file_name).write_bytes(b"broken")
    with pytest.raises(Invalid, match="sha256"):
        registry.import_local(db, other.store, buckets, actor=admin)
