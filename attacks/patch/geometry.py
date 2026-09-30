"""Khóa, kích thước và vị trí của patch (requirements.md Phase 6, mục Patch attack; plan task 11).

- Patch vuông, cạnh `side = round(sqrt(area_ratio * diện tích vùng tham chiếu))`.
- Khi train (người dùng chốt ở Group 2): vùng tham chiếu là phần giao các vùng ảnh thật của slice
  huấn luyện; patch đặt ở tâm phần giao nên nằm trọn trong vùng thật của mọi ảnh huấn luyện
  (RobustDPatch chỉ nhận một vị trí cho cả batch).
- Khi đánh giá: cùng cạnh, đặt ở tâm vùng ảnh thật của từng ảnh; không vừa thì báo lỗi.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from advertest_contracts.models import AttackSpec, compute_patch_key
from advertest_contracts.perturbation import MaskBatch
from attacks.common.checks import image_region


class PatchDoesNotFit(ValueError):
    """Patch không nằm trọn trong vùng ảnh thật."""


@dataclass(frozen=True)
class Region:
    """Hình chữ nhật hàng [top, bottom), cột [left, right) trong không gian letterbox."""

    top: int
    bottom: int
    left: int
    right: int

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def area(self) -> int:
        return max(0, self.height) * max(0, self.width)


def patch_key(
    spec: AttackSpec,
    *,
    weights_sha256: str,
    training_slice_sha256: str,
    area_ratio: float,
    seed: int,
) -> str:
    """Khóa patch của contract (`compute_patch_key`); mỗi khóa chỉ train một lần."""
    return compute_patch_key(
        spec_sha256=spec.spec_sha256,
        weights_sha256=weights_sha256,
        training_slice_sha256=training_slice_sha256,
        area_ratio=area_ratio,
        seed=seed,
    )


def image_regions(mask: MaskBatch | None, n: int, height: int, width: int) -> list[Region]:
    return [Region(*image_region(mask, i, height, width)) for i in range(n)]


def common_region(regions: list[Region]) -> Region:
    """Phần giao các vùng ảnh thật; rỗng thì báo lỗi."""
    if not regions:
        raise ValueError("Cần ít nhất một ảnh")
    region = Region(
        top=max(r.top for r in regions),
        bottom=min(r.bottom for r in regions),
        left=max(r.left for r in regions),
        right=min(r.right for r in regions),
    )
    if region.height <= 0 or region.width <= 0:
        raise PatchDoesNotFit("Vùng ảnh thật của các ảnh huấn luyện không giao nhau")
    return region


def patch_side(area_ratio: float, region: Region) -> int:
    if not 0 < area_ratio <= 1:
        raise ValueError(f"area_ratio phải trong (0, 1], nhận {area_ratio}")
    side = round(math.sqrt(area_ratio * region.area))
    if side < 1:
        raise PatchDoesNotFit(f"area_ratio {area_ratio} cho patch nhỏ hơn 1 pixel")
    return side


def centered(side: int, region: Region) -> tuple[int, int]:
    """(top, left) để patch cạnh `side` nằm giữa `region`; không vừa thì báo lỗi."""
    if side > region.height or side > region.width:
        raise PatchDoesNotFit(
            f"Patch {side}x{side} không vừa vùng ảnh thật {region.width}x{region.height}"
        )
    return (region.top + (region.height - side) // 2, region.left + (region.width - side) // 2)
