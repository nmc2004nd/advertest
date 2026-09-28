import numpy as np
import pytest
from PIL import Image

from ml_core.preprocess import (
    PAD_VALUE,
    boxes_from_letterbox,
    boxes_to_letterbox,
    letterbox,
)

KITTI_W, KITTI_H = 1242, 375


def _image(w: int = KITTI_W, h: int = KITTI_H) -> Image.Image:
    rng = np.random.default_rng(0)
    return Image.fromarray(rng.integers(0, 256, size=(h, w, 3), dtype=np.uint8))


def test_output_shape_dtype_range() -> None:
    x, info = letterbox(_image())
    assert x.shape == (3, 640, 640)
    assert x.dtype == np.float32
    assert x.min() >= 0.0 and x.max() <= 1.0
    assert info.orig_size == (KITTI_W, KITTI_H)
    assert info.scale == pytest.approx(640 / KITTI_W)


def test_pad_value_and_centered() -> None:
    x, info = letterbox(_image())
    left, top = info.pad
    new_h = round(KITTI_H * info.scale)
    bottom = 640 - top - new_h
    assert left == 0
    assert abs(top - bottom) <= 1  # căn giữa
    assert np.all(x[:, :top, :] == np.float32(PAD_VALUE))
    assert np.all(x[:, top + new_h :, :] == np.float32(PAD_VALUE))
    # Vùng ảnh không phải toàn pad.
    assert not np.all(x[:, top : top + new_h, :] == np.float32(PAD_VALUE))


def test_tall_image_pads_left_right() -> None:
    x, info = letterbox(_image(w=300, h=900))
    left, top = info.pad
    new_w = round(300 * info.scale)
    assert top == 0
    assert abs(left - (640 - left - new_w)) <= 1
    assert np.all(x[:, :, :left] == np.float32(PAD_VALUE))


def test_accepts_hwc_uint8_array() -> None:
    arr = np.asarray(_image())
    x_arr, _ = letterbox(arr)
    x_pil, _ = letterbox(_image())
    np.testing.assert_array_equal(x_arr, x_pil)


def test_pixel_content_scaled() -> None:
    # Ảnh một màu: vùng ảnh sau letterbox giữ đúng màu.
    img = Image.new("RGB", (KITTI_W, KITTI_H), (255, 0, 51))
    x, info = letterbox(img)
    _, top = info.pad
    center = x[:, top + 10, 320]
    np.testing.assert_allclose(center, [1.0, 0.0, 0.2], atol=1e-6)


def test_box_roundtrip_within_one_pixel() -> None:
    _, info = letterbox(_image())
    boxes = np.array(
        [
            [599.41, 156.4, 629.75, 189.25],
            [0, 0, KITTI_W, KITTI_H],
            [387.63, 181.54, 423.81, 203.12],
        ]
    )
    back = boxes_from_letterbox(boxes_to_letterbox(boxes, info), info)
    assert np.abs(back - boxes).max() <= 1.0


def test_boxes_in_frame() -> None:
    _, info = letterbox(_image())
    boxes = np.array([[0, 0, KITTI_W, KITTI_H], [-5, -5, KITTI_W + 20, KITTI_H + 20]])
    lb = boxes_to_letterbox(boxes, info)
    assert lb.min() >= 0 and lb.max() <= 640
    # Box phủ toàn ảnh gốc nằm đúng trong vùng ảnh (không phủ vùng pad).
    left, top = info.pad
    assert lb[0, 0] == pytest.approx(left) and lb[0, 1] == pytest.approx(top)
    assert lb[0, 3] == pytest.approx(top + KITTI_H * info.scale)


def test_empty_boxes() -> None:
    _, info = letterbox(_image())
    assert boxes_to_letterbox(np.zeros((0, 4)), info).shape == (0, 4)
