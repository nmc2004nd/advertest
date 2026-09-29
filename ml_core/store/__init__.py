"""Kho artifact theo nội dung. Phase 1 có `LocalStore`; Phase 3 thêm `MinioStore`
và `PresignedStore` (worker, chỉ ghi qua presigned URL).

Bố cục key (requirements.md Phase 1, mục Kho lưu trữ local):
`datasets/<sha>/manifest.json`, `slices/<slice_sha256>.json`, `mappings/<mapping_sha256>.json`,
`models/<weights_sha>/card.json`, `cache/predictions/<key>.json`, và chỉ mục `index/<kind>/<id>`.
"""

from __future__ import annotations

from ml_core.store.base import (
    ArtifactStore,
    DeletableStore,
    KeyConflictError,
    KeyNotFoundError,
    require_store,
    validate_key,
)
from ml_core.store.index import IdKind, register_id, resolve_id
from ml_core.store.local import DEFAULT_STORE_DIR, LocalStore
from ml_core.store.minio import MinioStore, S3Client
from ml_core.store.presigned import PresignedStore

__all__ = [
    "DEFAULT_STORE_DIR",
    "ArtifactStore",
    "DeletableStore",
    "IdKind",
    "KeyConflictError",
    "KeyNotFoundError",
    "LocalStore",
    "MinioStore",
    "PresignedStore",
    "S3Client",
    "register_id",
    "require_store",
    "resolve_id",
    "validate_key",
]
