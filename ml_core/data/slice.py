"""Slice: danh sách image ID cố định, định danh bằng `slice_sha256`.

Bộ lọc tự mô tả (không phụ thuộc model hay mapping): ảnh được chọn khi có ít nhất `min_objects`
annotation thuộc `filter.classes` và đạt ngưỡng `filter.difficulty`. Lấy mẫu bằng
`random.Random(seed).sample` trên danh sách ảnh hợp lệ đã sắp xếp, rồi sắp xếp lại ID.

Phase 6 (plan task 20a): `exclude` bỏ các ảnh cho trước khỏi danh sách hợp lệ (tạo slice huấn
luyện patch không giao với slice đánh giá). Danh sách loại trừ không thuộc hash: `image_ids` của
slice đã đủ định danh.
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Collection

from advertest_contracts.hashing import sha256_of
from advertest_contracts.ids import content_id
from advertest_contracts.models import (
    DatasetManifest,
    SliceFilter,
    SliceSpec,
    compute_slice_sha256,
)
from ml_core.data.mapping import get_preset, passes_difficulty
from ml_core.store import ArtifactStore, KeyNotFoundError, register_id

DEFAULT_SIZE = 300


def preset_filter(preset_name: str) -> SliceFilter:
    """Bộ lọc mặc định: class gốc có class đích trong preset, ngưỡng độ khó của preset."""
    preset = get_preset(preset_name)
    return SliceFilter(
        classes=sorted(c for c, target in preset.classes.items() if target is not None),
        difficulty=preset.difficulty,
        min_objects=1,
    )


def eligible_image_ids(manifest: DatasetManifest, slice_filter: SliceFilter) -> list[str]:
    classes = set(slice_filter.classes)
    counts = Counter(
        ann.image_id
        for ann in manifest.annotations
        if ann.category in classes and passes_difficulty(ann, slice_filter.difficulty)
    )
    return sorted(
        img.image_id for img in manifest.images if counts[img.image_id] >= slice_filter.min_objects
    )


def create_slice(
    manifest: DatasetManifest,
    size: int = DEFAULT_SIZE,
    seed: int = 42,
    slice_filter: SliceFilter | None = None,
    exclude: Collection[str] = (),
) -> SliceSpec:
    slice_filter = slice_filter or preset_filter("kitti-coco")
    excluded = set(exclude)
    eligible = [i for i in eligible_image_ids(manifest, slice_filter) if i not in excluded]
    if len(eligible) < size:
        raise ValueError(
            f"Chỉ có {len(eligible)} ảnh đạt bộ lọc (sau khi loại {len(excluded)} ảnh), không đủ"
            f" {size} ảnh cho slice"
        )
    image_ids = sorted(random.Random(seed).sample(eligible, size))
    body = {
        "dataset_version_sha256": sha256_of(manifest),
        "filter": slice_filter.model_dump(mode="json"),
        "seed": seed,
        "size": size,
        "image_ids": image_ids,
    }
    slice_sha = compute_slice_sha256(body)
    return SliceSpec(
        id=content_id(slice_sha),
        slice_sha256=slice_sha,
        image_ids_sha256=sha256_of(image_ids),
        **body,
    )


def slice_key(slice_sha256: str) -> str:
    return f"slices/{slice_sha256}.json"


def save_slice(store: ArtifactStore, spec: SliceSpec) -> None:
    store.put(slice_key(spec.slice_sha256), spec.model_dump_json(indent=2).encode())
    register_id(store, "slice", spec.slice_sha256)


def load_slice(store: ArtifactStore, slice_sha256: str) -> SliceSpec:
    try:
        return SliceSpec.model_validate_json(store.get(slice_key(slice_sha256)))
    except KeyNotFoundError:
        raise KeyNotFoundError(f"Không tìm thấy slice {slice_sha256} trong store") from None
