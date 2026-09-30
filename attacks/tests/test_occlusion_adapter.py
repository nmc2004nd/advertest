"""Adapter occlusion (validation.md Phase 6: Occlusion, Seed theo ảnh)."""

import numpy as np
import pytest

from attacks.common.checks import UnsupportedTransform
from attacks.occlusion.adapter import OcclusionPerturbation, rectangle_size
from attacks.tests.transform_helpers import letterbox_batch, spec, targets

FILL = np.float32(114 / 255)
# Box trong vùng ảnh thật (hàng 223–416), có tọa độ lẻ và nhiều tỉ lệ khác nhau.
BOXES = [
    [30.0, 240.0, 130.0, 290.0],
    [200.5, 250.2, 260.7, 380.9],
    [400.0, 300.0, 437.5, 323.3],
    [500.0, 230.0, 630.0, 410.0],
]


def _painted(out: np.ndarray, original: np.ndarray) -> np.ndarray:
    """(H, W) pixel bị tô ở ảnh đầu tiên."""
    changed = np.any(out[0] != original[0], axis=0)
    return changed & np.all(out[0] == FILL, axis=0)


def test_zero_ratio_leaves_image_unchanged() -> None:
    images, mask = letterbox_batch(1)
    out = OcclusionPerturbation(spec("bbox_occlusion")).apply(
        images, targets(1, [BOXES]), 0, 0, mask
    )
    np.testing.assert_array_equal(out, images)


@pytest.mark.parametrize("ratio", [0.1, 0.25, 0.5, 0.75, 0.9])
def test_area_within_two_percent_and_inside_box(ratio: float) -> None:
    images, mask = letterbox_batch(1)
    out = OcclusionPerturbation(spec("bbox_occlusion")).apply(
        images, targets(1, [BOXES]), ratio, 3, mask
    )
    painted = _painted(out, images)
    covered = np.zeros_like(painted)
    for x1, y1, x2, y2 in BOXES:
        inside = np.zeros_like(painted)
        inside[int(np.ceil(y1)) : int(np.floor(y2)), int(np.ceil(x1)) : int(np.floor(x2))] = True
        area = (x2 - x1) * (y2 - y1)
        assert abs(int((painted & inside).sum()) - ratio * area) <= 0.02 * area
        covered |= inside
    assert not (painted & ~covered).any(), "vùng tô phải nằm trong box"
    np.testing.assert_array_equal(out[:, :, ~covered], images[:, :, ~covered])


def test_ignore_region_and_pad_unchanged() -> None:
    images, mask = letterbox_batch(1)
    box = [100.0, 250.0, 300.0, 400.0]
    ignore = [150.0, 260.0, 250.0, 390.0]  # nằm trong box
    target = targets(1, [[box]])
    target[0]["ignore_boxes"] = np.asarray([ignore], dtype=np.float32)
    out = OcclusionPerturbation(spec("bbox_occlusion")).apply(images, target, 0.9, 0, mask)
    np.testing.assert_array_equal(out[0, :, 260:390, 150:250], images[0, :, 260:390, 150:250])
    assert _painted(out, images).any()
    pad = mask.repeat(3, axis=1) == 0
    np.testing.assert_array_equal(out[pad], images[pad])


def test_per_image_seed_independent_of_batch_and_order() -> None:
    images, mask = letterbox_batch(5)
    perturbation = OcclusionPerturbation(spec("bbox_occlusion"))
    ts = targets(5, [BOXES] * 5)
    whole = perturbation.apply(images, ts, 0.3, 11, mask)
    for i in range(5):
        single = perturbation.apply(images[i : i + 1], ts[i : i + 1], 0.3, 11, mask[i : i + 1])
        np.testing.assert_array_equal(single[0], whole[i])
    order = [3, 0, 4, 1, 2]
    shuffled = perturbation.apply(images[order], [ts[i] for i in order], 0.3, 11, mask[order])
    np.testing.assert_array_equal(shuffled, whole[order])


def test_different_image_id_moves_rectangle() -> None:
    images, mask = letterbox_batch(1)
    perturbation = OcclusionPerturbation(spec("bbox_occlusion"))
    box = np.asarray([[500.0, 230.0, 630.0, 410.0]], dtype=np.float32)
    a = perturbation.apply(images, [{"image_id": "a", "boxes": box}], 0.2, 0, mask)
    b = perturbation.apply(images, [{"image_id": "b", "boxes": box}], 0.2, 0, mask)
    assert not np.array_equal(a, b)


def test_rectangle_size_keeps_aspect_and_area() -> None:
    w, h = rectangle_size(200, 100, 0.5, 200, 100)
    assert abs(w * h - 10000) <= 200 and abs(w / h - 2) < 0.05
    assert rectangle_size(10, 10, 0, 10, 10) == (0, 0)
    assert rectangle_size(1.2, 1.2, 0.1, 1, 1) == (0, 0)  # 1 pixel xa hơn 0 pixel


def test_invalid_inputs() -> None:
    images, mask = letterbox_batch(1)
    perturbation = OcclusionPerturbation(spec("bbox_occlusion"))
    with pytest.raises(ValueError, match="ngoài dải"):
        perturbation.apply(images, targets(1, [BOXES]), 0.95, 0, mask)
    with pytest.raises(ValueError, match="image_id"):
        perturbation.apply(images, [{"boxes": np.zeros((0, 4))}], 0.5, 0, mask)
    with pytest.raises(UnsupportedTransform):
        OcclusionPerturbation(spec("fog"))
