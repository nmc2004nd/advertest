"""Adapter corruption (validation.md Phase 6: Corruption, Seed theo ảnh)."""

import numpy as np
import pytest

from attacks.corruptions.adapter import CorruptionPerturbation, UnsupportedTransform
from attacks.tests.transform_helpers import letterbox_batch, spec, targets

NAMES = ["fog", "snow", "frost", "motion_blur", "contrast"]


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("severity", [1, 2, 3, 4, 5])
def test_pad_unchanged_range_shape_dtype(name: str, severity: int) -> None:
    images, mask = letterbox_batch(2)
    out = CorruptionPerturbation(spec(name)).apply(images, targets(2), severity, 0, mask)
    assert out.shape == images.shape and out.dtype == np.float32
    assert out.min() >= 0.0 and out.max() <= 1.0
    np.testing.assert_array_equal(out[mask.repeat(3, axis=1) == 0], images[mask.repeat(3, 1) == 0])
    assert not np.array_equal(out, images)


@pytest.mark.parametrize("name", ["fog", "contrast"])
def test_difference_grows_with_severity(name: str) -> None:
    images, mask = letterbox_batch(3)
    perturbation = CorruptionPerturbation(spec(name))
    diffs = [
        float(np.abs(perturbation.apply(images, targets(3), s, 0, mask) - images).mean())
        for s in [1, 2, 3, 4, 5]
    ]
    assert diffs == sorted(diffs) and diffs[0] < diffs[-1]


@pytest.mark.parametrize("name", ["snow", "frost", "fog", "motion_blur"])
def test_per_image_seed_independent_of_batch_and_order(name: str) -> None:
    images, mask = letterbox_batch(5)
    perturbation = CorruptionPerturbation(spec(name))
    ts = targets(5)
    whole = perturbation.apply(images, ts, 3, 7, mask)
    for i in range(5):
        single = perturbation.apply(images[i : i + 1], ts[i : i + 1], 3, 7, mask[i : i + 1])
        np.testing.assert_array_equal(single[0], whole[i])
    order = [4, 2, 0, 3, 1]
    shuffled = perturbation.apply(images[order], [ts[i] for i in order], 3, 7, mask[order])
    np.testing.assert_array_equal(shuffled, whole[order])


def test_different_image_id_gives_different_result() -> None:
    images, mask = letterbox_batch(1)
    perturbation = CorruptionPerturbation(spec("snow"))
    a = perturbation.apply(images, [{"image_id": "a"}], 3, 0, mask)
    b = perturbation.apply(images, [{"image_id": "b"}], 3, 0, mask)
    assert not np.array_equal(a, b)


def test_without_mask_transforms_whole_image() -> None:
    images, _ = letterbox_batch(1)
    out = CorruptionPerturbation(spec("contrast")).apply(images, targets(1), 5, 0, None)
    assert not np.array_equal(out[0, :, :10], images[0, :, :10])


def test_invalid_inputs() -> None:
    images, mask = letterbox_batch(1)
    perturbation = CorruptionPerturbation(spec("fog"))
    with pytest.raises(ValueError, match="không thuộc"):
        perturbation.apply(images, targets(1), 2.5, 0, mask)
    with pytest.raises(ValueError, match="image_id"):
        perturbation.apply(images, [{"boxes": np.zeros((0, 4))}], 1, 0, mask)
    with pytest.raises(UnsupportedTransform):
        CorruptionPerturbation(spec("bbox_occlusion"))
    with pytest.raises(UnsupportedTransform):
        CorruptionPerturbation(spec("fgsm"))
