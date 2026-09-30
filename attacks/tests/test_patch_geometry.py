"""Kích thước, vị trí và khóa patch (validation.md Phase 6, mục Patch)."""

import numpy as np
import pytest

from advertest_contracts.models import compute_patch_key
from attacks.patch.geometry import (
    PatchDoesNotFit,
    Region,
    centered,
    common_region,
    image_regions,
    patch_key,
    patch_side,
)
from attacks.tests.transform_helpers import spec

KITTI = Region(top=223, bottom=416, left=0, right=640)


@pytest.mark.parametrize("ratio", [0.02, 0.05, 0.1, 0.25])
def test_area_within_one_percent_and_inside_region(ratio: float) -> None:
    side = patch_side(ratio, KITTI)
    # Sai số ±1% diện tích vùng ảnh thật (người dùng chốt ở Group 2): patch vuông cạnh nguyên không
    # đạt được ±1% tương đối ở tỉ lệ nhỏ (0,02 trên KITTI lệch tối thiểu 1,2%).
    assert abs(side * side - ratio * KITTI.area) <= 0.01 * KITTI.area
    # Cạnh làm tròn là cạnh nguyên tốt nhất.
    best = min(range(1, 200), key=lambda s: abs(s * s - ratio * KITTI.area))
    assert side == best
    top, left = centered(side, KITTI)
    assert KITTI.top <= top and top + side <= KITTI.bottom
    assert KITTI.left <= left and left + side <= KITTI.right


def test_common_region_is_intersection() -> None:
    mask = np.zeros((2, 1, 640, 640), dtype=np.float32)
    mask[0, :, 223:416] = 1
    mask[1, :, 223:417] = 1
    regions = image_regions(mask, 2, 640, 640)
    assert regions[1].height == 194
    assert common_region(regions) == KITTI
    assert image_regions(None, 1, 64, 64) == [Region(0, 64, 0, 64)]


def test_does_not_fit() -> None:
    with pytest.raises(PatchDoesNotFit):
        centered(200, KITTI)
    with pytest.raises(PatchDoesNotFit):
        common_region([Region(0, 10, 0, 10), Region(20, 30, 20, 30)])
    with pytest.raises(PatchDoesNotFit):
        patch_side(0.0001, Region(0, 10, 0, 10))
    with pytest.raises(ValueError, match="area_ratio"):
        patch_side(0, KITTI)


def test_patch_key_matches_contract() -> None:
    adv = spec("adv_patch")
    key = patch_key(
        adv, weights_sha256="a" * 64, training_slice_sha256="b" * 64, area_ratio=0.1, seed=0
    )
    assert key == compute_patch_key(
        spec_sha256=adv.spec_sha256,
        weights_sha256="a" * 64,
        training_slice_sha256="b" * 64,
        area_ratio=0.1,
        seed=0,
    )
    other = patch_key(
        adv, weights_sha256="a" * 64, training_slice_sha256="b" * 64, area_ratio=0.1, seed=1
    )
    assert key != other
