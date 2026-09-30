"""Bản vá nội bộ của 5 hàm corruption trong imagecorruptions 1.1.2 (requirements.md Phase 6, mục
Corruption; người dùng chọn ở Group 1).

Nguồn: https://github.com/bethgelab/imagecorruptions (Apache License 2.0, xem
`LICENSE.imagecorruptions`), vốn dựa trên ImageNet-C của Hendrycks và Dietterich. Ảnh trong
`frost/` lấy nguyên từ gói đó.

Thay đổi so với bản gốc:
- `np.float_` (đã bỏ ở numpy 2) → `np.float64` trong `plasma_fractal`, nên `fog` chạy được.
- Mọi số ngẫu nhiên lấy từ `rng` truyền vào (`np.random.Generator`) thay cho trạng thái chung của
  `np.random`: seed theo từng ảnh, không phụ thuộc thứ tự gọi.
- Đọc ảnh frost theo đường dẫn tương đối với file này (không cần `pkg_resources`), có cache.
- Chỉ giữ ảnh RGB (H, W, 3) uint8, bỏ nhánh ảnh xám.

Hằng số của từng severity giữ nguyên bản gốc.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray
from scipy.ndimage import zoom as scizoom

FloatArray = NDArray[np.floating]
Uint8Image = NDArray[np.uint8]

FROST_DIR = Path(__file__).resolve().parent / "frost"
# Bản gốc chọn `np.random.randint(5)` nên frost6.jpg không bao giờ được dùng; giữ nguyên hành vi.
_FROST_FILES = ("frost1.png", "frost2.png", "frost3.png", "frost4.jpg", "frost5.jpg")
MIN_SIDE = 32  # bản gốc từ chối ảnh nhỏ hơn 32 pixel mỗi chiều

# ---------------------------------------------------------------- helper


def _plasma_fractal(rng: np.random.Generator, mapsize: int, wibbledecay: float) -> FloatArray:
    """Bản đồ độ cao bằng thuật toán diamond-square, giá trị trong [0, 1]; mapsize là lũy thừa 2."""
    if mapsize & (mapsize - 1) != 0:
        raise ValueError("mapsize phải là lũy thừa của 2")
    maparray = np.empty((mapsize, mapsize), dtype=np.float64)
    maparray[0, 0] = 0
    stepsize = mapsize
    wibble = 100.0

    def wibbledmean(array: FloatArray) -> FloatArray:
        return array / 4 + wibble * rng.uniform(-wibble, wibble, array.shape)

    def fillsquares() -> None:
        cornerref = maparray[0:mapsize:stepsize, 0:mapsize:stepsize]
        squareaccum = cornerref + np.roll(cornerref, shift=-1, axis=0)
        squareaccum += np.roll(squareaccum, shift=-1, axis=1)
        maparray[stepsize // 2 : mapsize : stepsize, stepsize // 2 : mapsize : stepsize] = (
            wibbledmean(squareaccum)
        )

    def filldiamonds() -> None:
        size = maparray.shape[0]
        drgrid = maparray[stepsize // 2 : size : stepsize, stepsize // 2 : size : stepsize]
        ulgrid = maparray[0:size:stepsize, 0:size:stepsize]
        ldrsum = drgrid + np.roll(drgrid, 1, axis=0)
        lulsum = ulgrid + np.roll(ulgrid, -1, axis=1)
        maparray[0:size:stepsize, stepsize // 2 : size : stepsize] = wibbledmean(ldrsum + lulsum)
        tdrsum = drgrid + np.roll(drgrid, 1, axis=1)
        tulsum = ulgrid + np.roll(ulgrid, -1, axis=0)
        maparray[stepsize // 2 : size : stepsize, 0:size:stepsize] = wibbledmean(tdrsum + tulsum)

    while stepsize >= 2:
        fillsquares()
        filldiamonds()
        stepsize //= 2
        wibble /= wibbledecay

    maparray -= maparray.min()
    result: FloatArray = maparray / maparray.max()
    return result


def _clipped_zoom(img: FloatArray, zoom_factor: float) -> FloatArray:
    ch0 = int(np.ceil(img.shape[0] / float(zoom_factor)))
    top0 = (img.shape[0] - ch0) // 2
    ch1 = int(np.ceil(img.shape[1] / float(zoom_factor)))
    top1 = (img.shape[1] - ch1) // 2
    zoomed: FloatArray = scizoom(
        img[top0 : top0 + ch0, top1 : top1 + ch1], (zoom_factor, zoom_factor, 1), order=1
    )
    return zoomed


def _motion_blur_kernel(width: int, sigma: float) -> FloatArray:
    x = np.arange(width)
    k = np.exp(-(x**2) / (2 * sigma**2)) / (np.sqrt(2 * np.pi) * sigma)
    result: FloatArray = k / np.sum(k)
    return result


def _shift(image: FloatArray, dx: int, dy: int) -> FloatArray:
    if dx < 0:
        shifted = np.roll(image, shift=image.shape[1] + dx, axis=1)
        shifted[:, dx:] = shifted[:, dx - 1 : dx]
    elif dx > 0:
        shifted = np.roll(image, shift=dx, axis=1)
        shifted[:, :dx] = shifted[:, dx : dx + 1]
    else:
        shifted = image
    if dy < 0:
        shifted = np.roll(shifted, shift=image.shape[0] + dy, axis=0)
        shifted[dy:, :] = shifted[dy - 1 : dy, :]
    elif dy > 0:
        shifted = np.roll(shifted, shift=dy, axis=0)
        shifted[:dy, :] = shifted[dy : dy + 1, :]
    return shifted


def _motion_blur(x: FloatArray, radius: int, sigma: float, angle: float) -> FloatArray:
    width = radius * 2 + 1
    kernel = _motion_blur_kernel(width, sigma)
    point = (width * np.sin(np.deg2rad(angle)), width * np.cos(np.deg2rad(angle)))
    hypot = math.hypot(point[0], point[1])
    blurred = np.zeros_like(x, dtype=np.float32)
    for i in range(width):
        dy = -math.ceil(((i * point[0]) / hypot) - 0.5)
        dx = -math.ceil(((i * point[1]) / hypot) - 0.5)
        if abs(dy) >= x.shape[0] or abs(dx) >= x.shape[1]:
            break  # chuyển động vượt khỏi khung ảnh
        blurred = blurred + kernel[i] * _shift(x, dx, dy)
    return blurred


def _next_power_of_2(x: int) -> int:
    return 1 if x == 0 else 2 ** (x - 1).bit_length()


@lru_cache(maxsize=len(_FROST_FILES))
def _frost_image(index: int) -> NDArray[np.uint8]:
    path = FROST_DIR / _FROST_FILES[index]
    image = cv2.imread(str(path))  # BGR
    if image is None:
        raise FileNotFoundError(f"Không đọc được ảnh frost {path}")
    frozen = np.asarray(image, dtype=np.uint8)
    frozen.setflags(write=False)
    return frozen


# ---------------------------------------------------------------- corruption (x: uint8 RGB)


def fog(x: Uint8Image, severity: int, rng: np.random.Generator) -> FloatArray:
    c = [(1.5, 2), (2.0, 2), (2.5, 1.7), (2.5, 1.5), (3.0, 1.4)][severity - 1]
    map_size = _next_power_of_2(int(max(x.shape)))
    image = x / 255.0
    max_val = image.max()
    plasma = _plasma_fractal(rng, mapsize=map_size, wibbledecay=c[1])
    image = image + c[0] * plasma[: x.shape[0], : x.shape[1]][..., np.newaxis]
    result: FloatArray = np.clip(image * max_val / (max_val + c[0]), 0, 1) * 255
    return result


def frost(x: Uint8Image, severity: int, rng: np.random.Generator) -> FloatArray:
    c = [(1, 0.4), (0.8, 0.6), (0.7, 0.7), (0.65, 0.7), (0.6, 0.75)][severity - 1]
    frost_image = _frost_image(int(rng.integers(len(_FROST_FILES))))
    frost_h, frost_w = frost_image.shape[:2]
    x_h, x_w = x.shape[:2]

    # Phóng ảnh frost cho vừa kích thước ảnh (giữ quy tắc của bản gốc).
    if frost_h >= x_h and frost_w >= x_w:
        scaling_factor = 1.0
    elif frost_h < x_h and frost_w >= x_w:
        scaling_factor = x_h / frost_h
    elif frost_h >= x_h and frost_w < x_w:
        scaling_factor = x_w / frost_w
    else:
        scaling_factor = max(x_h / frost_h, x_w / frost_w)
    scaling_factor *= 1.1
    new_size = (int(np.ceil(frost_w * scaling_factor)), int(np.ceil(frost_h * scaling_factor)))
    rescaled = cv2.resize(frost_image, dsize=new_size, interpolation=cv2.INTER_CUBIC)

    x_start = int(rng.integers(0, rescaled.shape[0] - x_h))
    y_start = int(rng.integers(0, rescaled.shape[1] - x_w))
    crop = rescaled[x_start : x_start + x_h, y_start : y_start + x_w][..., [2, 1, 0]]
    result: FloatArray = np.clip(c[0] * x.astype(np.float64) + c[1] * crop, 0, 255)
    return result


def snow(x: Uint8Image, severity: int, rng: np.random.Generator) -> FloatArray:
    c = [
        (0.1, 0.3, 3, 0.5, 10, 4, 0.8),
        (0.2, 0.3, 2, 0.5, 12, 4, 0.7),
        (0.55, 0.3, 4, 0.9, 12, 8, 0.7),
        (0.55, 0.3, 4.5, 0.85, 12, 8, 0.65),
        (0.55, 0.3, 2.5, 0.85, 12, 12, 0.55),
    ][severity - 1]
    image = np.asarray(x, dtype=np.float32) / 255.0
    noise: FloatArray = rng.normal(size=image.shape[:2], loc=c[0], scale=c[1])
    snow_layer = _clipped_zoom(noise[..., np.newaxis], c[2])
    snow_layer[snow_layer < c[3]] = 0
    snow_layer = np.clip(snow_layer.squeeze(), 0, 1)
    snow_layer = _motion_blur(
        snow_layer, radius=int(c[4]), sigma=c[5], angle=float(rng.uniform(-135, -45))
    )
    # Làm tròn lớp tuyết về 8 bit rồi cắt theo kích thước ảnh.
    snow_layer = np.round(snow_layer * 255).astype(np.uint8) / 255.0
    snow_layer = snow_layer[..., np.newaxis][: image.shape[0], : image.shape[1], :]
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY).reshape(image.shape[0], image.shape[1], 1)
    image = c[6] * image + (1 - c[6]) * np.maximum(image, gray * 1.5 + 0.5)
    result: FloatArray = np.clip(image + snow_layer + np.rot90(snow_layer, k=2), 0, 1) * 255
    return result


def motion_blur(x: Uint8Image, severity: int, rng: np.random.Generator) -> FloatArray:
    c = [(10, 3), (15, 5), (15, 8), (15, 12), (20, 15)][severity - 1]
    angle = float(rng.uniform(-45, 45))
    blurred = _motion_blur(x.astype(np.float64), radius=c[0], sigma=c[1], angle=angle)
    result: FloatArray = np.clip(blurred, 0, 255)
    return result


def contrast(x: Uint8Image, severity: int, rng: np.random.Generator) -> FloatArray:
    del rng  # contrast không ngẫu nhiên
    c = [0.4, 0.3, 0.2, 0.1, 0.05][severity - 1]
    image = x / 255.0
    means = np.mean(image, axis=(0, 1), keepdims=True)
    result: FloatArray = np.clip((image - means) * c + means, 0, 1) * 255
    return result


_FUNCTIONS: dict[str, Callable[[Uint8Image, int, np.random.Generator], FloatArray]] = {
    "fog": fog,
    "snow": snow,
    "frost": frost,
    "motion_blur": motion_blur,
    "contrast": contrast,
}
NAMES = frozenset(_FUNCTIONS)


def corrupt(image: Uint8Image, name: str, severity: int, rng: np.random.Generator) -> Uint8Image:
    """Ảnh uint8 (H, W, 3) RGB sau corruption; ép kiểu `np.uint8` như bản gốc (cắt phần lẻ)."""
    if name not in _FUNCTIONS:
        raise ValueError(f"Không có corruption {name!r} (có: {', '.join(sorted(_FUNCTIONS))})")
    if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(f"Ảnh phải là uint8 (H, W, 3), nhận {image.dtype} {image.shape}")
    if image.shape[0] < MIN_SIDE or image.shape[1] < MIN_SIDE:
        raise ValueError(f"Ảnh phải có mỗi chiều ít nhất {MIN_SIDE} pixel, nhận {image.shape[:2]}")
    if severity not in (1, 2, 3, 4, 5):
        raise ValueError(f"severity phải là số nguyên từ 1 đến 5, nhận {severity}")
    return _FUNCTIONS[name](image, severity, rng).astype(np.uint8)
