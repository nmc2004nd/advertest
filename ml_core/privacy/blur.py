"""Làm mờ vùng ảnh (requirements.md Phase 6, mục Làm mờ ảnh; plan task 22).

Mỗi vùng: Gaussian với bán kính tỉ lệ cạnh ngắn của vùng (tối thiểu `MIN_RADIUS` px), rồi pixelate
thành khối vuông. Vùng gồm mọi pixel chạm vào box (làm mờ thừa hơn thiếu). Điểm ảnh ngoài mọi vùng
giữ nguyên chính xác. Kết quả tất định.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageFilter

from ml_core.privacy.regions import Box

MIN_RADIUS = 8.0
RADIUS_FRACTION = 0.2  # bán kính = 20% cạnh ngắn của vùng
MIN_BLOCK = 4
BLOCK_DIVISOR = 6  # khối pixelate = cạnh ngắn / 6


def pixel_bounds(box: Box, width: int, height: int) -> tuple[int, int, int, int] | None:
    """(top, bottom, left, right) của mọi pixel chạm vào box, cắt theo khung ảnh."""
    x1, y1, x2, y2 = box
    left, right = max(0, math.floor(x1)), min(width, math.ceil(x2))
    top, bottom = max(0, math.floor(y1)), min(height, math.ceil(y2))
    if right <= left or bottom <= top:
        return None
    return top, bottom, left, right


def _blur_patch(pixels: NDArray[np.uint8]) -> NDArray[np.uint8]:
    """pixels (H, W, 3) uint8 → đã làm mờ và pixelate."""
    height, width = pixels.shape[:2]
    short = min(height, width)
    radius = max(MIN_RADIUS, RADIUS_FRACTION * short)
    block = max(MIN_BLOCK, round(short / BLOCK_DIVISOR))
    image = Image.fromarray(pixels).filter(ImageFilter.GaussianBlur(radius=radius))
    small = image.resize(
        (max(1, math.ceil(width / block)), max(1, math.ceil(height / block))),
        Image.Resampling.BOX,
    )
    return np.asarray(small.resize((width, height), Image.Resampling.NEAREST), dtype=np.uint8)


def blur_regions(image: NDArray[np.float32], regions: Sequence[Box]) -> NDArray[np.float32]:
    """Bản sao của ảnh (C, H, W) float32 [0, 1] đã làm mờ các vùng (xyxy)."""
    if image.ndim != 3 or image.shape[0] != 3:
        raise ValueError(f"Ảnh phải có shape (3, H, W), nhận {image.shape}")
    result = image.copy()
    _, height, width = image.shape
    for box in regions:
        bounds = pixel_bounds(box, width, height)
        if bounds is None:
            continue
        top, bottom, left, right = bounds
        crop = result[:, top:bottom, left:right].transpose(1, 2, 0)
        pixels = np.round(np.clip(crop, 0.0, 1.0) * 255).astype(np.uint8)
        blurred = _blur_patch(pixels).astype(np.float32) / 255.0
        result[:, top:bottom, left:right] = blurred.transpose(2, 0, 1)
    return result


def region_mask(regions: Sequence[Box], width: int, height: int) -> NDArray[np.bool_]:
    """(H, W): pixel thuộc ít nhất một vùng làm mờ."""
    mask = np.zeros((height, width), dtype=bool)
    for box in regions:
        bounds = pixel_bounds(box, width, height)
        if bounds is not None:
            top, bottom, left, right = bounds
            mask[top:bottom, left:right] = True
    return mask
