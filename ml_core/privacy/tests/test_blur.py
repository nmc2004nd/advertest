"""Làm mờ vùng (validation.md Phase 6, mục Làm mờ)."""

import numpy as np
import pytest

from ml_core.privacy.blur import blur_regions, pixel_bounds, region_mask


def _scene(height: int = 120, width: int = 160) -> np.ndarray:
    """Ảnh có chi tiết (sọc + nhiễu) để làm mờ thấy được khác biệt."""
    rng = np.random.default_rng(0)
    yy, xx = np.mgrid[0:height, 0:width]
    stripes = 0.5 + 0.4 * np.sin(xx / 2.0) * np.cos(yy / 3.0)
    image = np.stack([stripes, 1 - stripes, stripes]) + rng.normal(0, 0.05, (3, height, width))
    return np.clip(image, 0, 1).astype(np.float32)


REGIONS = [(10.5, 20.2, 60.7, 50.9), (100.0, 80.0, 150.0, 118.0), (0.0, 0.0, 3.0, 2.0)]


def test_pixels_inside_change_and_outside_identical() -> None:
    image = _scene()
    out = blur_regions(image, REGIONS)
    inside = region_mask(REGIONS, 160, 120)
    np.testing.assert_array_equal(out[:, ~inside], image[:, ~inside])
    for box in REGIONS:
        bounds = pixel_bounds(box, 160, 120)
        assert bounds is not None
        top, bottom, left, right = bounds
        region = (slice(None), slice(top, bottom), slice(left, right))
        assert np.abs(out[region] - image[region]).mean() > 0.05
    assert out.dtype == np.float32 and out.min() >= 0 and out.max() <= 1


def test_detail_removed() -> None:
    image = _scene()
    out = blur_regions(image, [(20.0, 20.0, 140.0, 100.0)])
    region = out[:, 20:100, 20:140]
    # Sau pixelate (khối khoảng 12 px), mỗi kênh trong một khối 8x8 là một màu.
    for channel in range(3):
        assert np.ptp(region[channel, :8, :8]) == 0
    # Chi tiết (độ lệch giữa pixel kề nhau) giảm mạnh.
    original = np.abs(np.diff(image[:, 20:100, 20:140], axis=2)).mean()
    assert np.abs(np.diff(region, axis=2)).mean() < original / 5


def test_deterministic_and_input_untouched() -> None:
    image = _scene()
    copy = image.copy()
    a = blur_regions(image, REGIONS)
    b = blur_regions(image, REGIONS)
    np.testing.assert_array_equal(a, b)
    np.testing.assert_array_equal(image, copy)


def test_bounds_cover_touched_pixels_and_clip() -> None:
    assert pixel_bounds((10.5, 20.2, 60.7, 50.9), 160, 120) == (20, 51, 10, 61)
    assert pixel_bounds((-5.0, -5.0, 3.0, 2.0), 160, 120) == (0, 2, 0, 3)
    assert pixel_bounds((170.0, 0.0, 180.0, 5.0), 160, 120) is None


def test_rejects_non_rgb() -> None:
    with pytest.raises(ValueError, match="shape"):
        blur_regions(np.zeros((1, 4, 4), dtype=np.float32), [])
