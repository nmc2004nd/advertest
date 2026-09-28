"""Lọc prediction trước khi tính metric (requirements.md Phase 1, mục Đánh giá).

Prediction và ground truth dùng chung không gian: box xyxy pixel ảnh letterbox, label là chỉ số
class trong model (`ModelCard.class_names`).
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

import numpy as np
from numpy.typing import NDArray

IOA_THRESHOLD = 0.5

Prediction = dict[str, NDArray[Any]]  # {"boxes": (K, 4), "labels": (K,), "scores": (K,)}


def _select(pred: Prediction, keep: NDArray[np.bool_]) -> Prediction:
    return {
        "boxes": np.asarray(pred["boxes"]).reshape(-1, 4)[keep],
        "labels": np.asarray(pred["labels"])[keep],
        "scores": np.asarray(pred["scores"])[keep],
    }


def filter_classes(pred: Prediction, target_labels: Collection[int]) -> Prediction:
    """Bỏ prediction thuộc class model không có trong mapping (không phải class đích)."""
    labels = np.asarray(pred["labels"])
    return _select(pred, np.isin(labels, np.fromiter(target_labels, dtype=np.int64)))


def ioa(boxes: NDArray[Any], regions: NDArray[Any]) -> NDArray[np.float64]:
    """IoA (N, M) = diện tích giao / diện tích box. Box có diện tích 0 cho IoA = 0."""
    a = np.asarray(boxes, dtype=np.float64).reshape(-1, 4)
    b = np.asarray(regions, dtype=np.float64).reshape(-1, 4)
    lt = np.maximum(a[:, None, :2], b[None, :, :2])
    rb = np.minimum(a[:, None, 2:], b[None, :, 2:])
    inter = np.clip(rb - lt, 0, None).prod(axis=2)
    area = np.clip(a[:, 2:] - a[:, :2], 0, None).prod(axis=1)
    out: NDArray[np.float64] = np.zeros(inter.shape, dtype=np.float64)
    np.divide(inter, area[:, None], out=out, where=area[:, None] > 0)
    return out


def filter_ignored(
    pred: Prediction, ignore_boxes: NDArray[Any], threshold: float = IOA_THRESHOLD
) -> Prediction:
    """Bỏ prediction có IoA ≥ `threshold` với bất kỳ ignore region nào của ảnh."""
    boxes = np.asarray(pred["boxes"]).reshape(-1, 4)
    regions = np.asarray(ignore_boxes).reshape(-1, 4)
    if len(boxes) == 0 or len(regions) == 0:
        return _select(pred, np.ones(len(boxes), dtype=bool))
    keep = np.asarray(~(ioa(boxes, regions) >= threshold).any(axis=1), dtype=bool)
    return _select(pred, keep)
