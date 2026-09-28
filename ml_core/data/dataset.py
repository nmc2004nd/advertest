"""Lưu và đọc dataset version trong store.

- `datasets/<sha>/manifest.json`: manifest; `sha` = dataset version = `sha256_of(manifest)`.
- `datasets/<sha>/sources/<sha256(đường dẫn)>.json`: thư mục gốc chứa ảnh,
  `{"root": "<đường dẫn tuyệt đối>"}`.
  Manifest chỉ lưu `file_name` tương đối; loader thử từng thư mục và kiểm tra sha256 từng ảnh.
  Import cùng dữ liệu từ thư mục khác thêm một nguồn mới, không sửa nguồn cũ (store bất biến).
- Chỉ mục `index/dataset/<id>` với `id = content_id(sha)`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from advertest_contracts.hashing import sha256_of
from advertest_contracts.models import DatasetManifest
from ml_core.store import ArtifactStore, KeyNotFoundError, register_id


def manifest_key(dataset_sha256: str) -> str:
    return f"datasets/{dataset_sha256}/manifest.json"


def _sources_prefix(dataset_sha256: str) -> str:
    return f"datasets/{dataset_sha256}/sources/"


def save_dataset(store: ArtifactStore, manifest: DatasetManifest, root: Path) -> str:
    """Lưu manifest và thư mục gốc của ảnh; trả `dataset_version_sha256`."""
    sha = sha256_of(manifest)
    store.put(manifest_key(sha), manifest.model_dump_json(indent=2).encode())
    root_str = str(root.resolve())
    root_hash = hashlib.sha256(root_str.encode()).hexdigest()
    store.put(
        f"{_sources_prefix(sha)}{root_hash}.json",
        json.dumps({"root": root_str}, ensure_ascii=False).encode(),
    )
    register_id(store, "dataset", sha)
    return sha


def load_manifest(store: ArtifactStore, dataset_sha256: str) -> DatasetManifest:
    try:
        data = store.get(manifest_key(dataset_sha256))
    except KeyNotFoundError:
        raise KeyNotFoundError(
            f"Không tìm thấy dataset {dataset_sha256} trong store; chạy `dataset import-kitti`."
        ) from None
    manifest = DatasetManifest.model_validate_json(data)
    if sha256_of(manifest) != dataset_sha256:
        raise ValueError(f"Manifest trong store không khớp hash {dataset_sha256}")
    return manifest


def dataset_roots(store: ArtifactStore, dataset_sha256: str) -> list[Path]:
    """Các thư mục gốc đã import dataset này, theo thứ tự key."""
    return [
        Path(json.loads(store.get(key))["root"])
        for key in store.list(_sources_prefix(dataset_sha256))
    ]
