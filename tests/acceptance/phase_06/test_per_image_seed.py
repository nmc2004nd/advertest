"""validation.md Phase 6, Seed theo ảnh (`test_per_image_seed.py`): kết quả của một ảnh chỉ phụ
thuộc `seed` và `image_id`, không phụ thuộc batch, batch size hay thứ tự ảnh."""

from __future__ import annotations

import numpy as np
import pytest

from attacks.factory import build_perturbation
from attacks.registry import get_spec, load_catalog

from .conftest import Kitti

CASES = [("snow", 3.0), ("frost", 3.0), ("bbox_occlusion", 0.5)]
SEED = 11


def _apply(name: str, level: float, kitti: Kitti, order: list[int]) -> dict[str, np.ndarray]:
    perturbation = build_perturbation(get_spec(load_catalog(), name=name), None)
    images, targets, mask = kitti.subset(order)
    out = perturbation.apply(images, targets, level, SEED, mask)
    return {t["image_id"]: out[i] for i, t in enumerate(targets)}


@pytest.mark.parametrize(("name", "level"), CASES)
def test_same_seed_and_image_id_independent_of_batch(name: str, level: float, kitti: Kitti) -> None:
    n = len(kitti.targets)
    batch5 = _apply(name, level, kitti, list(range(n)))
    reversed5 = _apply(name, level, kitti, list(reversed(range(n))))
    singles: dict[str, np.ndarray] = {}
    for i in range(n):
        singles.update(_apply(name, level, kitti, [i]))
    assert set(batch5) == set(reversed5) == set(singles) and len(batch5) == n
    for image_id, image in batch5.items():
        np.testing.assert_array_equal(image, reversed5[image_id])
        np.testing.assert_array_equal(image, singles[image_id])


@pytest.mark.parametrize(("name", "level"), CASES)
def test_other_image_id_gives_other_result(name: str, level: float, kitti: Kitti) -> None:
    perturbation = build_perturbation(get_spec(load_catalog(), name=name), None)
    images, targets, mask = kitti.subset([0, 0])
    targets = [targets[0], {**targets[1], "image_id": f"{targets[1]['image_id']}-khac"}]
    out = perturbation.apply(images, targets, level, SEED, mask)
    assert not np.array_equal(out[0], out[1])
