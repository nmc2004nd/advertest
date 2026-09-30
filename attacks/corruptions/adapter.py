"""Corruption theo interface `Perturbation` (requirements.md Phase 6, mục Corruption).

Áp trong không gian đầu vào của model: cắt vùng ảnh thật (không gồm pad) → uint8 → corruption ở
severity = `level` → float [0, 1] → đặt lại vào ảnh letterbox. Điểm ảnh có mask = 0 giữ nguyên
(so sánh chính xác). Mỗi ảnh dùng seed riêng `per_image_seed(seed, image_id)`.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from advertest_contracts.enums import AttackKind
from advertest_contracts.models import AttackSpec
from advertest_contracts.perturbation import ImageBatch, MaskBatch
from attacks.common.checks import check_inputs, image_region
from attacks.common.seed import image_rng, target_image_id
from attacks.corruptions.functions import MIN_SIDE, NAMES, corrupt


class UnsupportedTransform(ValueError):
    """Spec không dựng được bằng adapter corruption hoặc occlusion."""


class CorruptionPerturbation:
    """Một corruption của bản vá imagecorruptions (`fixed_params.corruption`)."""

    def __init__(self, spec: AttackSpec) -> None:
        name = spec.fixed_params.get("corruption")
        if spec.kind != AttackKind.CORRUPTION or not isinstance(name, str) or name not in NAMES:
            raise UnsupportedTransform(
                f"{spec.name}: cần kind = corruption và fixed_params.corruption thuộc"
                f" {sorted(NAMES)}"
            )
        if spec.primary_param.name != "severity" or spec.primary_param.type != "discrete":
            raise UnsupportedTransform(f"{spec.name}: tham số chính phải là severity rời rạc")
        self.spec = spec
        self.corruption = name

    def apply(
        self,
        images: ImageBatch,
        targets: list[dict[str, Any]],
        level: float,
        seed: int,
        mask: MaskBatch | None = None,
    ) -> ImageBatch:
        check_inputs(self.spec, images, targets, level, mask)
        severity = int(level)
        _, _, height, width = images.shape
        result = images.copy()
        for i, target in enumerate(targets):
            image_id = target_image_id(target, i)
            y0, y1, x0, x1 = image_region(mask, i, height, width)
            if y1 - y0 < MIN_SIDE or x1 - x0 < MIN_SIDE:
                raise ValueError(
                    f"Ảnh {image_id}: vùng ảnh thật {y1 - y0}x{x1 - x0} nhỏ hơn {MIN_SIDE} pixel"
                )
            crop = images[i, :, y0:y1, x0:x1].transpose(1, 2, 0)
            as_uint8 = np.round(np.clip(crop, 0.0, 1.0) * 255.0).astype(np.uint8)
            corrupted = corrupt(as_uint8, self.corruption, severity, image_rng(seed, image_id))
            result[i, :, y0:y1, x0:x1] = corrupted.transpose(2, 0, 1).astype(np.float32) / 255.0
        if mask is not None:
            result = np.where(mask == 0, images, result).astype(np.float32)
        return result
