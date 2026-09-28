"""Kho artifact theo nội dung. Phase 1 chỉ có `LocalStore`; Phase 3 thêm `MinioStore`.

Bố cục key (requirements.md Phase 1, mục Kho lưu trữ local):
`datasets/<sha>/manifest.json`, `slices/<slice_sha256>.json`, `mappings/<mapping_sha256>.json`,
`models/<weights_sha>/card.json`, `cache/predictions/<key>.json`, và chỉ mục `index/<kind>/<id>`.
"""

from __future__ import annotations

from ml_core.store.base import ArtifactStore, KeyConflictError, KeyNotFoundError, validate_key
from ml_core.store.index import IdKind, register_id, resolve_id
from ml_core.store.local import DEFAULT_STORE_DIR, LocalStore

__all__ = [
    "DEFAULT_STORE_DIR",
    "ArtifactStore",
    "IdKind",
    "KeyConflictError",
    "KeyNotFoundError",
    "LocalStore",
    "register_id",
    "resolve_id",
    "validate_key",
]
