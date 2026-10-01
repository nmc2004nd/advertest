"""validation.md Phase 6, Occlusion (`test_occlusion.py`) trên ảnh letterbox KITTI thật."""

from __future__ import annotations

import math

import numpy as np
import pytest

from attacks.factory import build_perturbation
from attacks.registry import get_spec, load_catalog

from .conftest import Kitti

SPEC = get_spec(load_catalog(), name="bbox_occlusion")
_FILL_255 = SPEC.fixed_params.get("fill_255", 114)
assert isinstance(_FILL_255, int)
FILL = np.float32(_FILL_255 / 255.0)


def _occlude(kitti: Kitti, ratio: float) -> np.ndarray:
    images, targets, mask = kitti.subset(list(range(len(kitti.targets))))
    return build_perturbation(SPEC, None).apply(images, targets, ratio, 3, mask)


def _pixels(box: np.ndarray) -> tuple[int, int, int, int]:
    """Hàng, cột của pixel nằm trọn trong box (như adapter)."""
    x1, y1, x2, y2 = (float(v) for v in box)
    return math.ceil(y1), math.floor(y2), math.ceil(x1), math.floor(x2)


def _overlaps(a: np.ndarray, b: np.ndarray) -> bool:
    return bool(a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3])


def test_ratio_zero_changes_nothing(kitti: Kitti) -> None:
    np.testing.assert_array_equal(_occlude(kitti, 0.0), kitti.batch.images)


@pytest.mark.parametrize("ratio", [0.25, 0.5, 0.75])
def test_area_inside_box_and_untouched_outside(kitti: Kitti, ratio: float) -> None:
    out = _occlude(kitti, ratio)
    images = kitti.batch.images
    checked = 0
    for i, target in enumerate(kitti.targets):
        changed = np.any(out[i] != images[i], axis=0)
        painted = np.all(out[i] == FILL, axis=0) & changed
        assert np.array_equal(painted, changed)  # mọi điểm đổi đều là màu tô
        boxes = np.asarray(target["boxes"], dtype=np.float64).reshape(-1, 4)
        ignore = np.asarray(target["ignore_boxes"], dtype=np.float64).reshape(-1, 4)
        inside_any = np.zeros_like(changed)
        for box in boxes:
            r0, r1, c0, c1 = _pixels(box)
            inside_any[max(r0, 0) : r1, max(c0, 0) : c1] = True
        # Điểm ảnh ngoài mọi box không đổi.
        assert not changed[~inside_any].any()
        # Điểm ảnh chạm ignore region không đổi.
        for box in ignore:
            r0, c0 = max(0, math.floor(box[1])), max(0, math.floor(box[0]))
            r1, c1 = math.ceil(box[3]), math.ceil(box[2])
            assert not changed[r0:r1, c0:c1].any()
        # Diện tích tô của box đứng riêng (không chồng box khác, không chạm ignore region).
        for k, box in enumerate(boxes):
            others = [b for j, b in enumerate(boxes) if j != k] + list(ignore)
            if any(_overlaps(box, other) for other in others):
                continue
            r0, r1, c0, c1 = _pixels(box)
            area = (box[2] - box[0]) * (box[3] - box[1])
            if ratio * area < 50:  # box vài pixel: sai số làm tròn vượt 2%
                continue
            count = int(painted[r0:r1, c0:c1].sum())
            assert abs(count - ratio * area) <= 0.02 * area, (i, k, count, ratio * area)
            checked += 1
    assert checked >= 3  # đủ box để kết luận
