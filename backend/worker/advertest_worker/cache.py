"""Cache tài nguyên của job trên máy worker (requirements.md Phase 3, Luồng xử lý bước 2).

- `<cache>/images/<sha256>`: ảnh của slice, chỉ tải ảnh chưa có (`ShaCacheLoader`).
- `<cache>/store/`: `LocalStore` chứa weights, card, manifest, slice, mapping (bố cục của `ml_core`)
  và cache prediction ảnh sạch theo (model, slice), dùng lại giữa các job.

Mọi file tải về được kiểm tra sha256 trước khi dùng.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

import httpx

from advertest_contracts.hashing import sha256_of
from advertest_contracts.models import DatasetManifest, WorkerJobBundle
from ml_core.data.dataset import manifest_key
from ml_core.data.mapping import save_mapping
from ml_core.data.slice import save_slice
from ml_core.models.register import card_key, weights_key
from ml_core.runner.cache_loader import ShaCacheLoader, cached_image_path
from ml_core.store import LocalStore


class DownloadError(RuntimeError):
    pass


class JobCache:
    def __init__(self, root: Path, http: httpx.Client | None = None) -> None:
        self.root = root
        self.store = LocalStore(root / "store")
        self.image_dir = root / "images"
        self.http = http or httpx.Client(timeout=120.0)

    def _download(self, url: str) -> bytes:
        response = self.http.get(url)
        response.raise_for_status()
        return response.content

    def _download_checked(self, url: str, sha256: str, what: str) -> bytes:
        data = self._download(url)
        if hashlib.sha256(data).hexdigest() != sha256:
            raise DownloadError(f"{what} tải về sai sha256")
        return data

    def _write_image(self, sha256: str, data: bytes) -> None:
        self.image_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.image_dir, prefix=".tmp-")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, cached_image_path(self.image_dir, sha256))

    def prepare(self, bundle: WorkerJobBundle) -> ShaCacheLoader:
        """Tải những gì còn thiếu, trả loader đọc ảnh từ cache."""
        card = bundle.model_card
        sha = card.weights_sha256
        if not self.store.exists(weights_key(sha)):
            self.store.put(
                weights_key(sha), self._download_checked(bundle.downloads.weights, sha, "Weights")
            )
        self.store.put(card_key(sha), card.model_dump_json(indent=2).encode())

        dataset_sha = bundle.slice.dataset_version_sha256
        if not self.store.exists(manifest_key(dataset_sha)):
            data = self._download(bundle.downloads.dataset_manifest)
            if sha256_of(DatasetManifest.model_validate_json(data)) != dataset_sha:
                raise DownloadError("Manifest tải về không khớp dataset version")
            self.store.put(manifest_key(dataset_sha), data)
        save_slice(self.store, bundle.slice)
        save_mapping(self.store, bundle.class_mapping)

        loader = ShaCacheLoader(
            self.store, bundle.slice, bundle.class_mapping, card, self.image_dir
        )
        for image_id in loader.missing_images():
            image_sha = loader.image_sha256(image_id)
            url = bundle.downloads.images[image_id]
            self._write_image(image_sha, self._download_checked(url, image_sha, f"Ảnh {image_id}"))
        return loader
