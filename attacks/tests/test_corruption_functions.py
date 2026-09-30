"""Bản vá nội bộ của imagecorruptions (requirements.md Phase 6, mục Corruption)."""

import numpy as np
import pytest

from attacks.corruptions.functions import NAMES, corrupt

# Vùng ảnh thật của KITTI sau letterbox 640 (1242x375 → 640x193; một số ảnh 1224x370 → 640x194).
SHAPES = [(193, 640, 3), (194, 640, 3), (640, 640, 3), (32, 32, 3)]


def _image(shape: tuple[int, int, int]) -> np.ndarray:
    return (np.random.default_rng(0).random(shape) * 255).astype(np.uint8)


def test_names() -> None:
    assert {"fog", "snow", "frost", "motion_blur", "contrast"} == NAMES


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("name", sorted(NAMES))
@pytest.mark.parametrize("severity", [1, 2, 3, 4, 5])
def test_every_corruption_runs_at_every_severity(
    shape: tuple[int, int, int], name: str, severity: int
) -> None:
    image = _image(shape)
    out = corrupt(image, name, severity, np.random.default_rng(5))
    assert out.shape == image.shape and out.dtype == np.uint8
    again = corrupt(image, name, severity, np.random.default_rng(5))
    np.testing.assert_array_equal(out, again)


@pytest.mark.parametrize("name", ["fog", "snow", "frost", "motion_blur"])
def test_random_corruptions_depend_on_rng(name: str) -> None:
    image = _image((193, 640, 3))
    a = corrupt(image, name, 3, np.random.default_rng(1))
    b = corrupt(image, name, 3, np.random.default_rng(2))
    assert not np.array_equal(a, b)


def test_contrast_is_deterministic() -> None:
    image = _image((64, 64, 3))
    a = corrupt(image, "contrast", 2, np.random.default_rng(1))
    b = corrupt(image, "contrast", 2, np.random.default_rng(2))
    np.testing.assert_array_equal(a, b)


def test_invalid_inputs() -> None:
    rng = np.random.default_rng(0)
    image = _image((64, 64, 3))
    with pytest.raises(ValueError, match="Không có corruption"):
        corrupt(image, "rain", 1, rng)
    with pytest.raises(ValueError, match="severity"):
        corrupt(image, "fog", 6, rng)
    with pytest.raises(ValueError, match="32 pixel"):
        corrupt(_image((31, 64, 3)), "fog", 1, rng)
    with pytest.raises(ValueError, match="uint8"):
        corrupt(image.astype(np.float32), "fog", 1, rng)
