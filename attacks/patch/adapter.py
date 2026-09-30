"""Đánh giá patch theo interface `Perturbation` (requirements.md Phase 6, Patch attack; task 13).

Dán patch đã train vào tâm vùng ảnh thật của từng ảnh (vị trí cố định, không ngẫu nhiên). `level`
phải bằng `area_ratio` mà patch được train; patch không vừa vùng ảnh thật thì báo lỗi. Điểm ảnh có
mask = 0 giữ nguyên.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from advertest_contracts.models import AttackSpec
from advertest_contracts.perturbation import ImageBatch, MaskBatch
from attacks.common.checks import check_inputs, image_region
from attacks.patch.geometry import Region, centered
from attacks.patch.training import PatchArray, paste, training_params


class PatchPerturbation:
    def __init__(self, spec: AttackSpec, patch: PatchArray, *, area_ratio: float) -> None:
        training_params(spec)
        if patch.dtype != np.float32 or patch.ndim != 3 or patch.shape[0] != 3:
            raise ValueError(
                f"patch phải là float32 (3, side, side), nhận {patch.dtype} {patch.shape}"
            )
        if patch.shape[1] != patch.shape[2]:
            raise ValueError(f"patch phải vuông, nhận {patch.shape}")
        self.spec = spec
        self.patch = patch
        self.area_ratio = area_ratio

    def apply(
        self,
        images: ImageBatch,
        targets: list[dict[str, Any]],
        level: float,
        seed: int,
        mask: MaskBatch | None = None,
    ) -> ImageBatch:
        """`seed` không dùng: vị trí patch cố định."""
        check_inputs(self.spec, images, targets, level, mask)
        if level != self.area_ratio:
            raise ValueError(
                f"{self.spec.name}: level {level} khác area_ratio {self.area_ratio} của patch"
            )
        n, _, height, width = images.shape
        side = self.patch.shape[1]
        tops: list[int] = []
        lefts: list[int] = []
        for i in range(n):
            top, left = centered(side, Region(*image_region(mask, i, height, width)))
            tops.append(top)
            lefts.append(left)
        result = paste(images, self.patch, tops, lefts)
        if mask is not None:
            result = np.where(mask == 0, images, result).astype(np.float32)
        return result
