"""Vùng làm mờ `rule_v1` (requirements.md Phase 6, mục Làm mờ ảnh; plan task 21).

Lấy từ hợp của ground truth, prediction trên ảnh sạch và prediction sau biến đổi
(score ≥ `MIN_SCORE`), xyxy pixel letterbox:
- `person`: 1/3 phía trên của box (vùng đầu);
- `car`, `truck`: dải 40% phía dưới của box (vùng biển số);
- toàn bộ ignore region (vùng `DontCare` thường chứa người và xe ở xa).

Vùng được cắt theo khung ảnh; vùng rỗng bị bỏ. Không gộp các vùng chồng nhau (làm mờ lặp lại vẫn
đúng), để số vùng phản ánh số object.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

MIN_SCORE = 0.25
PERSON_CLASSES = frozenset({"person"})
VEHICLE_CLASSES = frozenset({"car", "truck"})
PERSON_TOP_FRACTION = 1 / 3
VEHICLE_BOTTOM_FRACTION = 0.4

Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class Detection:
    """Box xyxy letterbox kèm tên class của model; `score = None` với ground truth."""

    box: Box
    class_name: str
    score: float | None = None


def _clip(box: Box, width: int, height: int) -> Box | None:
    x1, y1, x2, y2 = box
    x1, x2 = max(0.0, min(float(width), x1)), max(0.0, min(float(width), x2))
    y1, y2 = max(0.0, min(float(height), y1)), max(0.0, min(float(height), y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return (x1, y1, x2, y2)


def object_region(detection: Detection) -> Box | None:
    """Vùng cần làm mờ của một object; `None` với class không thuộc quy tắc."""
    x1, y1, x2, y2 = detection.box
    height = y2 - y1
    if detection.class_name in PERSON_CLASSES:
        return (x1, y1, x2, y1 + height * PERSON_TOP_FRACTION)
    if detection.class_name in VEHICLE_CLASSES:
        return (x1, y2 - height * VEHICLE_BOTTOM_FRACTION, x2, y2)
    return None


def rule_v1_regions(
    *,
    ground_truth: Iterable[Detection],
    clean: Iterable[Detection],
    attacked: Iterable[Detection],
    ignore_boxes: Sequence[Box],
    width: int,
    height: int,
    min_score: float = MIN_SCORE,
) -> list[Box]:
    """Danh sách vùng làm mờ (xyxy letterbox, đã cắt theo khung ảnh)."""
    candidates: list[Box] = []
    for detection in ground_truth:
        region = object_region(detection)
        if region is not None:
            candidates.append(region)
    for detection in [*clean, *attacked]:
        if detection.score is None or detection.score < min_score:
            continue
        region = object_region(detection)
        if region is not None:
            candidates.append(region)
    candidates.extend((float(b[0]), float(b[1]), float(b[2]), float(b[3])) for b in ignore_boxes)
    regions = [_clip(box, width, height) for box in candidates]
    return [region for region in regions if region is not None]
