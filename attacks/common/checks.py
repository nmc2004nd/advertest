"""Kiểm tra đầu vào chung của `Perturbation.apply` và tìm vùng ảnh thật theo mask (Phase 6)."""

from __future__ import annotations

from typing import Any

import numpy as np

from advertest_contracts.models import AttackSpec
from advertest_contracts.perturbation import ImageBatch, MaskBatch


class UnsupportedTransform(ValueError):
    """Spec không dựng được bằng adapter corruption hoặc occlusion."""


def check_inputs(
    spec: AttackSpec,
    images: ImageBatch,
    targets: list[dict[str, Any]],
    level: float,
    mask: MaskBatch | None,
) -> None:
    if images.ndim != 4 or images.dtype != np.float32:
        raise ValueError(f"images phải là float32 (N, C, H, W), nhận {images.dtype} {images.shape}")
    if images.shape[1] != 3:
        raise ValueError(f"images phải có 3 kênh RGB, nhận {images.shape[1]}")
    if len(targets) != len(images):
        raise ValueError(f"Cần {len(images)} targets, nhận {len(targets)}")
    n, _, height, width = images.shape
    if mask is not None and mask.shape != (n, 1, height, width):
        raise ValueError(f"mask phải có shape {(n, 1, height, width)}, nhận {mask.shape}")
    param = spec.primary_param
    if not param.min <= level <= param.max:
        raise ValueError(
            f"{spec.name}: level {level} ngoài dải [{param.min}, {param.max}] ({param.unit})"
        )
    if param.type == "discrete" and level not in (param.values or []):
        raise ValueError(f"{spec.name}: level {level} không thuộc {param.values}")


def image_region(mask: MaskBatch | None, index: int, height: int, width: int) -> tuple[int, ...]:
    """(y0, y1, x0, x1) của vùng ảnh thật (hình chữ nhật bao các điểm mask = 1); toàn ảnh khi
    không có mask; (0, 0, 0, 0) khi mask rỗng."""
    if mask is None:
        return (0, height, 0, width)
    inside = mask[index, 0] != 0
    rows = np.flatnonzero(inside.any(axis=1))
    cols = np.flatnonzero(inside.any(axis=0))
    if rows.size == 0:
        return (0, 0, 0, 0)
    return (int(rows[0]), int(rows[-1]) + 1, int(cols[0]), int(cols[-1]) + 1)
