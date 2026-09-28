"""Class mapping: preset `kitti-coco`, tạo `ClassMapping`, áp mapping lên manifest.

Khi áp mapping (requirements.md Phase 1, mục Class mapping mặc định KITTI → COCO):
- annotation có class đích và đạt ngưỡng độ khó → ground truth với class đích;
- có class đích nhưng không đạt ngưỡng → ignore region `difficulty:<class gốc>`;
- class đích `null` hoặc class không có trong mapping → ignore region `unmapped:<class gốc>`;
- ignore region của manifest (`dont_care`) giữ nguyên.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from advertest_contracts.ids import content_id
from advertest_contracts.models import (
    ClassMapping,
    ClassMappingBody,
    DatasetManifest,
    DifficultyFilter,
    ManifestAnnotation,
    ModelCard,
    compute_mapping_sha256,
)
from ml_core.store import ArtifactStore, KeyNotFoundError, register_id

# Mức Moderate của KITTI: giữ GT khi cao ≥ 25 px, occluded ≤ 1, truncated ≤ 0.30.
KITTI_MODERATE = DifficultyFilter(min_height_px=25, max_occluded=1, max_truncated=0.30)


@dataclass(frozen=True)
class Preset:
    classes: dict[str, str | None]
    difficulty: DifficultyFilter | None


PRESETS: dict[str, Preset] = {
    "kitti-coco": Preset(
        classes={
            "Car": "car",
            "Van": "car",
            "Truck": "truck",
            "Pedestrian": "person",
            "Person_sitting": "person",
            "Cyclist": None,
            "Tram": None,
            "Misc": None,
        },
        difficulty=KITTI_MODERATE,
    ),
}


def get_preset(name: str) -> Preset:
    if name not in PRESETS:
        raise ValueError(f"Preset không biết: {name!r}; có: {', '.join(sorted(PRESETS))}")
    return PRESETS[name]


def passes_difficulty(ann: ManifestAnnotation, difficulty: DifficultyFilter | None) -> bool:
    """Ngưỡng tính cả biên. Thiếu thuộc tính `truncated`/`occluded` thì không xét điều kiện đó."""
    if difficulty is None:
        return True
    _, y1, _, y2 = ann.bbox
    if y2 - y1 < difficulty.min_height_px:
        return False
    occluded = ann.attributes.get("occluded")
    if isinstance(occluded, int | float) and occluded > difficulty.max_occluded:
        return False
    truncated = ann.attributes.get("truncated")
    return not (isinstance(truncated, int | float) and truncated > difficulty.max_truncated)


def build_mapping(dataset_sha256: str, card: ModelCard, preset_name: str) -> ClassMapping:
    preset = get_preset(preset_name)
    unknown = {t for t in preset.classes.values() if t is not None} - set(card.class_names)
    if unknown:
        raise ValueError(f"Class đích không có trong model {card.name}: {sorted(unknown)}")
    body = ClassMappingBody(
        dataset_version_sha256=dataset_sha256,
        model_id=card.id,
        preset=preset_name,
        classes=preset.classes,
        difficulty=preset.difficulty,
    )
    sha = compute_mapping_sha256(body)
    return ClassMapping(**body.model_dump(), id=content_id(sha), mapping_sha256=sha)


def mapping_key(mapping_sha256: str) -> str:
    return f"mappings/{mapping_sha256}.json"


def save_mapping(store: ArtifactStore, mapping: ClassMapping) -> None:
    store.put(mapping_key(mapping.mapping_sha256), mapping.model_dump_json(indent=2).encode())
    register_id(store, "mapping", mapping.mapping_sha256)


def load_mapping(store: ArtifactStore, mapping_sha256: str) -> ClassMapping:
    try:
        return ClassMapping.model_validate_json(store.get(mapping_key(mapping_sha256)))
    except KeyNotFoundError:
        raise KeyNotFoundError(f"Không tìm thấy mapping {mapping_sha256} trong store") from None


@dataclass
class MappedImage:
    """Ground truth và ignore region của một ảnh sau khi áp mapping, tọa độ ảnh gốc."""

    image_id: str
    boxes: NDArray[np.float64] = field(default_factory=lambda: np.zeros((0, 4)))
    classes: list[str] = field(default_factory=list)  # class đích (class của model)
    ignore_boxes: NDArray[np.float64] = field(default_factory=lambda: np.zeros((0, 4)))
    ignore_sources: list[str] = field(default_factory=list)


def apply_mapping(manifest: DatasetManifest, mapping: ClassMapping) -> dict[str, MappedImage]:
    """Kết quả cho mọi ảnh của manifest, kể cả ảnh không còn ground truth."""
    boxes: dict[str, list[tuple[float, float, float, float]]] = {}
    classes: dict[str, list[str]] = {}
    ignore: dict[str, list[tuple[float, float, float, float]]] = {}
    sources: dict[str, list[str]] = {}
    for img in manifest.images:
        for d in (boxes, classes, ignore, sources):
            d[img.image_id] = []

    for region in manifest.ignore_regions:
        ignore[region.image_id].append(region.bbox)
        sources[region.image_id].append(region.source)
    for ann in manifest.annotations:
        target = mapping.classes.get(ann.category)
        if target is None:
            ignore[ann.image_id].append(ann.bbox)
            sources[ann.image_id].append(f"unmapped:{ann.category}")
        elif not passes_difficulty(ann, mapping.difficulty):
            ignore[ann.image_id].append(ann.bbox)
            sources[ann.image_id].append(f"difficulty:{ann.category}")
        else:
            boxes[ann.image_id].append(ann.bbox)
            classes[ann.image_id].append(target)

    return {
        image_id: MappedImage(
            image_id=image_id,
            boxes=np.asarray(boxes[image_id], dtype=np.float64).reshape(-1, 4),
            classes=classes[image_id],
            ignore_boxes=np.asarray(ignore[image_id], dtype=np.float64).reshape(-1, 4),
            ignore_sources=sources[image_id],
        )
        for image_id in boxes
    }
