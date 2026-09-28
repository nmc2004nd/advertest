"""Nghiệm thu Phase 1, mục Letterbox (validation.md)."""

from __future__ import annotations

import numpy as np
from PIL import Image

from ml_core.preprocess import (
    PAD_VALUE,
    boxes_from_letterbox,
    boxes_to_letterbox,
    letterbox,
)

KITTI_SIZE = (1242, 375)


def _kitti_image() -> Image.Image:
    rng = np.random.default_rng(0)
    pixels = rng.integers(0, 256, size=(KITTI_SIZE[1], KITTI_SIZE[0], 3), dtype=np.uint8)
    return Image.fromarray(pixels)


def test_kitti_image_becomes_640_square_with_pad_value() -> None:
    x, info = letterbox(_kitti_image())
    assert x.shape == (3, 640, 640) and x.dtype == np.float32
    _, top = info.pad
    new_h = round(KITTI_SIZE[1] * info.scale)
    assert top > 0
    assert np.all(x[:, :top, :] == np.float32(PAD_VALUE))
    assert np.all(x[:, top + new_h :, :] == np.float32(PAD_VALUE))
    assert abs(top - (640 - top - new_h)) <= 1  # căn giữa


def test_box_roundtrip_within_one_pixel() -> None:
    _, info = letterbox(_kitti_image())
    boxes = np.array(
        [
            [599.41, 156.4, 629.75, 189.25],
            [0.0, 0.0, 1242.0, 375.0],
            [1187.47, 162.53, 1241.0, 305.7],
        ]
    )
    back = boxes_from_letterbox(boxes_to_letterbox(boxes, info), info)
    assert np.abs(back - boxes).max() <= 1.0


def test_letterboxed_boxes_inside_frame() -> None:
    _, info = letterbox(_kitti_image())
    boxes = np.array([[0.0, 0.0, 1242.0, 375.0], [-10.0, -10.0, 1300.0, 400.0]])
    out = boxes_to_letterbox(boxes, info)
    assert out.min() >= 0 and out.max() <= 640
