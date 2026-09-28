"""Nạp ảnh của một slice theo mapping, trả batch theo quy ước tech-stack.md mục 2.1.

- `images`: (N, 3, 640, 640) float32, [0, 1], đã letterbox.
- `targets`: list dict `{"boxes", "labels"}` theo định dạng label của ART; `boxes` xyxy pixel
  trong không gian letterbox, `labels` là **chỉ số class trong model**
  (theo `ModelCard.class_names`).
- `ignore`: list dict `{"boxes", "sources"}`, box xyxy letterbox của ignore region.

Ảnh tìm trong các thư mục gốc đã ghi khi import (`dataset_roots`); sha256 của từng ảnh được kiểm
tra với manifest khi nạp, để kết quả tái lập được.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from advertest_contracts.models import ClassMapping, DatasetManifest, ModelCard, SliceSpec
from ml_core.data.dataset import dataset_roots, load_manifest
from ml_core.data.mapping import MappedImage, apply_mapping, load_mapping
from ml_core.data.slice import load_slice
from ml_core.models.register import load_card
from ml_core.preprocess import LetterboxInfo, boxes_to_letterbox, letterbox
from ml_core.store import ArtifactStore, resolve_id


class ImageNotFoundError(FileNotFoundError):
    """Không thư mục nguồn nào có ảnh đúng sha256 của manifest."""


@dataclass
class Batch:
    image_ids: list[str]
    images: NDArray[np.float32]
    targets: list[dict[str, NDArray[Any]]]
    ignore: list[dict[str, Any]]
    infos: list[LetterboxInfo]


class SliceLoader:
    def __init__(
        self,
        store: ArtifactStore,
        slice_spec: SliceSpec,
        mapping: ClassMapping,
        card: ModelCard,
    ) -> None:
        if mapping.dataset_version_sha256 != slice_spec.dataset_version_sha256:
            raise ValueError("Mapping và slice thuộc hai dataset version khác nhau")
        if mapping.model_id != card.id:
            raise ValueError("Mapping không thuộc model đã cho")
        self.slice = slice_spec
        self.mapping = mapping
        self.card = card
        self.manifest: DatasetManifest = load_manifest(store, slice_spec.dataset_version_sha256)
        self.roots = dataset_roots(store, slice_spec.dataset_version_sha256)
        self._images = {img.image_id: img for img in self.manifest.images}
        missing = [i for i in slice_spec.image_ids if i not in self._images]
        if missing:
            raise ValueError(f"Slice có image ID không có trong manifest: {missing[:5]}")
        self._mapped: dict[str, MappedImage] = apply_mapping(self.manifest, mapping)
        self._class_index = {name: i for i, name in enumerate(card.class_names)}

    @classmethod
    def from_ids(cls, store: ArtifactStore, slice_id: UUID, mapping_id: UUID) -> SliceLoader:
        slice_spec = load_slice(store, resolve_id(store, "slice", slice_id))
        mapping = load_mapping(store, resolve_id(store, "mapping", mapping_id))
        card = load_card(store, resolve_id(store, "model", mapping.model_id))
        return cls(store, slice_spec, mapping, card)

    def __len__(self) -> int:
        return len(self.slice.image_ids)

    def read_image(self, image_id: str) -> Image.Image:
        """Ảnh gốc, đã kiểm tra sha256 với manifest."""
        entry = self._images[image_id]
        for root in self.roots:
            path = Path(root) / entry.file_name
            if not path.is_file():
                continue
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() == entry.sha256:
                return Image.open(io.BytesIO(data)).convert("RGB")
        raise ImageNotFoundError(
            f"Không tìm thấy ảnh {entry.file_name} đúng sha256 trong: "
            f"{[str(r) for r in self.roots] or 'chưa có thư mục nguồn'}"
        )

    def load(
        self, image_id: str
    ) -> tuple[NDArray[np.float32], dict[str, NDArray[Any]], dict[str, Any], LetterboxInfo]:
        image, info = letterbox(self.read_image(image_id))
        gt = self._mapped[image_id]
        target: dict[str, NDArray[Any]] = {
            "boxes": boxes_to_letterbox(gt.boxes, info).astype(np.float32),
            "labels": np.asarray([self._class_index[c] for c in gt.classes], dtype=np.int64),
        }
        ignore: dict[str, Any] = {
            "boxes": boxes_to_letterbox(gt.ignore_boxes, info).astype(np.float32),
            "sources": list(gt.ignore_sources),
        }
        return image, target, ignore, info

    def batches(self, batch_size: int) -> Iterator[Batch]:
        if batch_size < 1:
            raise ValueError("batch_size phải ≥ 1")
        ids = self.slice.image_ids
        for start in range(0, len(ids), batch_size):
            chunk = ids[start : start + batch_size]
            loaded = [self.load(image_id) for image_id in chunk]
            yield Batch(
                image_ids=list(chunk),
                images=np.stack([item[0] for item in loaded]),
                targets=[item[1] for item in loaded],
                ignore=[item[2] for item in loaded],
                infos=[item[3] for item in loaded],
            )
