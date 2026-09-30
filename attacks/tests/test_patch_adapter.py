"""Đánh giá patch (validation.md Phase 6, mục Patch)."""

from typing import Any

import numpy as np
import pytest

from attacks.patch.adapter import PatchPerturbation
from attacks.patch.geometry import PatchDoesNotFit
from attacks.tests.transform_helpers import REAL_BOTTOM, REAL_TOP, letterbox_batch, spec, targets

SIDE = 176  # round(sqrt(0.25 * 640 * 193))


def _patch(side: int = SIDE) -> np.ndarray:
    return np.random.default_rng(0).random((3, side, side)).astype(np.float32)


def test_pastes_at_center_of_real_region_and_keeps_pad() -> None:
    images, mask = letterbox_batch(2)
    patch = _patch()
    out = PatchPerturbation(spec("adv_patch"), patch, area_ratio=0.25).apply(
        images, targets(2), 0.25, 0, mask
    )
    top = REAL_TOP + (REAL_BOTTOM - REAL_TOP - SIDE) // 2
    left = (640 - SIDE) // 2
    for i in range(2):
        np.testing.assert_array_equal(out[i, :, top : top + SIDE, left : left + SIDE], patch)
    changed = np.any(out != images, axis=1)
    assert changed[:, :REAL_TOP].sum() == 0 and changed[:, REAL_BOTTOM:].sum() == 0
    assert abs(SIDE * SIDE - 0.25 * 640 * 193) <= 0.01 * 640 * 193
    assert out.dtype == np.float32


def test_deterministic_regardless_of_seed() -> None:
    images, mask = letterbox_batch(1)
    perturbation = PatchPerturbation(spec("adv_patch"), _patch(), area_ratio=0.25)
    a = perturbation.apply(images, targets(1), 0.25, 0, mask)
    b = perturbation.apply(images, targets(1), 0.25, 9, mask)
    np.testing.assert_array_equal(a, b)


def test_level_must_match_patch() -> None:
    images, mask = letterbox_batch(1)
    perturbation = PatchPerturbation(spec("adv_patch"), _patch(), area_ratio=0.25)
    with pytest.raises(ValueError, match="khác area_ratio"):
        perturbation.apply(images, targets(1), 0.1, 0, mask)


def test_patch_larger_than_region_is_rejected() -> None:
    images, mask = letterbox_batch(1)
    perturbation = PatchPerturbation(spec("adv_patch"), _patch(200), area_ratio=0.25)
    with pytest.raises(PatchDoesNotFit):
        perturbation.apply(images, targets(1), 0.25, 0, mask)


def test_invalid_patch() -> None:
    float64_patch: Any = np.zeros((3, 4, 4))  # sai dtype có chủ đích
    with pytest.raises(ValueError, match="float32"):
        PatchPerturbation(spec("adv_patch"), float64_patch, area_ratio=0.1)
    with pytest.raises(ValueError, match="vuông"):
        PatchPerturbation(spec("adv_patch"), np.zeros((3, 4, 5), np.float32), area_ratio=0.1)
