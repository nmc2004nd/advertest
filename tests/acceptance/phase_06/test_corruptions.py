"""validation.md Phase 6, Corruption (`test_corruptions.py`) trên ảnh letterbox KITTI thật (fixture:
vùng ảnh thật khoảng 640x193)."""

from __future__ import annotations

from itertools import pairwise

import numpy as np
import pytest

from attacks.factory import build_perturbation
from attacks.registry import get_spec, load_catalog

from .conftest import Kitti

CORRUPTIONS = ["fog", "snow", "frost", "motion_blur", "contrast"]
SEVERITIES = [1.0, 2.0, 3.0, 4.0, 5.0]


def _corrupt(kitti: Kitti, name: str, severity: float) -> np.ndarray:
    perturbation = build_perturbation(get_spec(load_catalog(), name=name), None)
    images, targets, mask = kitti.subset(list(range(len(kitti.targets))))
    return perturbation.apply(images, targets, severity, 0, mask)


def test_fixture_is_kitti_letterbox(kitti: Kitti) -> None:
    rows = np.flatnonzero(kitti.mask[0, 0].any(axis=1))
    cols = np.flatnonzero(kitti.mask[0, 0].any(axis=0))
    assert cols.size == 640 and 180 <= rows.size <= 200  # vùng ảnh thật ≈ 640x193


@pytest.mark.parametrize("name", CORRUPTIONS)
@pytest.mark.parametrize("severity", SEVERITIES)
def test_runs_keeps_pad_and_range(kitti: Kitti, name: str, severity: float) -> None:
    out = _corrupt(kitti, name, severity)
    images = kitti.batch.images
    assert out.shape == images.shape and out.dtype == np.float32
    assert float(out.min()) >= 0.0 and float(out.max()) <= 1.0
    pad = kitti.mask == 0
    np.testing.assert_array_equal(out[np.broadcast_to(pad, out.shape)],
                                  images[np.broadcast_to(pad, images.shape)])  # fmt: skip
    inside = np.broadcast_to(kitti.mask == 1, out.shape)
    assert not np.array_equal(out[inside], images[inside])  # vùng ảnh thật có bị biến đổi


def _mean_difference(kitti: Kitti, name: str) -> list[float]:
    inside = np.broadcast_to(kitti.mask == 1, kitti.batch.images.shape)
    return [
        float(np.abs(_corrupt(kitti, name, s) - kitti.batch.images)[inside].mean())
        for s in SEVERITIES
    ]


def test_contrast_difference_grows_with_severity(kitti: Kitti) -> None:
    diffs = _mean_difference(kitti, "contrast")
    assert all(a < b for a, b in pairwise(diffs)), diffs


def test_fog_difference_grows_with_severity(kitti: Kitti) -> None:
    """Người dùng chốt ở Group 7: tham số gốc của imagecorruptions cho fog mức 3 và 4 cùng cường
    độ (2.5, chỉ khác độ nhám của fractal) nên không so hai mức này; các mức còn lại tăng."""
    s1, s2, s3, s4, s5 = _mean_difference(kitti, "fog")
    assert s1 < s2 < s3 and s4 < s5 and s1 < s5 and s2 < s4, (s1, s2, s3, s4, s5)
