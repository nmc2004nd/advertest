"""Loader đọc ảnh theo sha256 từ thư mục cache của worker (Phase 3).

Worker tải ảnh của slice qua presigned URL về `<image_dir>/<sha256>` (chỉ tải ảnh chưa có), thay
cho thư mục gốc lúc import (`datasets/<sha>/sources/`, đường dẫn tuyệt đối trên máy import).
Manifest, slice, mapping, card vẫn đọc từ store như `SliceLoader`; sha256 từng ảnh được kiểm tra
khi nạp.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

from PIL import Image

from advertest_contracts.models import ClassMapping, ModelCard, SliceSpec
from ml_core.data.loader import ImageNotFoundError, SliceLoader
from ml_core.store import ArtifactStore


def cached_image_path(image_dir: Path, sha256: str) -> Path:
    return image_dir / sha256


class ShaCacheLoader(SliceLoader):
    def __init__(
        self,
        store: ArtifactStore,
        slice_spec: SliceSpec,
        mapping: ClassMapping,
        card: ModelCard,
        image_dir: Path,
    ) -> None:
        super().__init__(store, slice_spec, mapping, card)
        self.image_dir = image_dir
        self._sha = {img.image_id: img.sha256 for img in self.manifest.images}

    def image_sha256(self, image_id: str) -> str:
        return self._sha[image_id]

    def missing_images(self) -> list[str]:
        """Ảnh của slice chưa có trong cache (worker cần tải)."""
        return [
            i
            for i in self.slice.image_ids
            if not cached_image_path(self.image_dir, self._sha[i]).is_file()
        ]

    def read_image(self, image_id: str) -> Image.Image:
        sha = self._sha[image_id]
        path = cached_image_path(self.image_dir, sha)
        if not path.is_file():
            raise ImageNotFoundError(f"Ảnh {image_id} ({sha}) chưa có trong cache {self.image_dir}")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != sha:
            raise ImageNotFoundError(f"Ảnh {image_id} trong cache sai sha256 ({path})")
        return Image.open(io.BytesIO(data)).convert("RGB")
