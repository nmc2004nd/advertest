"""Letterbox: resize giữ tỉ lệ để cạnh dài bằng `size`, pad căn giữa bằng 114/255.

Toàn bộ pipeline tính trong không gian letterbox; manifest luôn lưu tọa độ ảnh gốc
(requirements.md Phase 1, mục Letterbox).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray
from PIL import Image

INPUT_SIZE = 640
PAD_VALUE = 114 / 255

# Cấu hình letterbox, giống nhau cho mọi ảnh. Đây là phần "cấu hình letterbox" trong khóa cache
# (requirements.md Phase 1, mục Cache) và trong fingerprint (Phase 2). Đổi cách letterbox phải đổi
# hằng này để cache và fingerprint cũ không bị dùng nhầm.
LETTERBOX_CONFIG: Final[dict[str, int | str]] = {
    "size": INPUT_SIZE,
    "pad_value": 114,  # trên thang 0-255; trong ảnh float là 114/255
    "resample": "pillow_bilinear",
    "align": "center",
}


@dataclass(frozen=True)
class LetterboxInfo:
    """Đủ để chuyển tọa độ giữa ảnh gốc và ảnh letterbox."""

    scale: float
    pad: tuple[int, int]  # (trái, trên), pixel
    orig_size: tuple[int, int]  # (rộng, cao) của ảnh gốc
    size: int = INPUT_SIZE

    def as_dict(self) -> dict[str, object]:
        """Thông tin letterbox riêng của một ảnh, dạng JSON.

        Không dùng cho khóa cache hay fingerprint; dùng `LETTERBOX_CONFIG`.
        """
        return {
            "scale": self.scale,
            "pad": list(self.pad),
            "orig_size": list(self.orig_size),
            "size": self.size,
        }


def letterbox(
    image: Image.Image | NDArray[np.uint8], size: int = INPUT_SIZE
) -> tuple[NDArray[np.float32], LetterboxInfo]:
    """Ảnh RGB (PIL hoặc mảng HWC uint8) → mảng (3, size, size) float32 trong [0, 1]."""
    pil = image if isinstance(image, Image.Image) else Image.fromarray(image)
    pil = pil.convert("RGB")
    w, h = pil.size
    scale = min(size / w, size / h)
    new_w = max(1, min(size, round(w * scale)))
    new_h = max(1, min(size, round(h * scale)))
    left = (size - new_w) // 2
    top = (size - new_h) // 2

    resized = pil.resize((new_w, new_h), Image.Resampling.BILINEAR)
    out = np.full((size, size, 3), PAD_VALUE, dtype=np.float32)
    out[top : top + new_h, left : left + new_w] = np.asarray(resized, dtype=np.float32) / 255.0
    info = LetterboxInfo(scale=scale, pad=(left, top), orig_size=(w, h), size=size)
    return np.ascontiguousarray(out.transpose(2, 0, 1)), info


def _as_boxes(boxes: NDArray[np.floating] | list[list[float]]) -> NDArray[np.float64]:
    arr = np.asarray(boxes, dtype=np.float64).reshape(-1, 4)
    return arr.copy()


def boxes_to_letterbox(
    boxes: NDArray[np.floating] | list[list[float]], info: LetterboxInfo
) -> NDArray[np.float64]:
    """Box xyxy pixel ảnh gốc (N, 4) → pixel ảnh letterbox, cắt trong [0, size]."""
    out = _as_boxes(boxes) * info.scale
    out[:, [0, 2]] += info.pad[0]
    out[:, [1, 3]] += info.pad[1]
    return np.clip(out, 0, info.size)


def boxes_from_letterbox(
    boxes: NDArray[np.floating] | list[list[float]], info: LetterboxInfo
) -> NDArray[np.float64]:
    """Box xyxy pixel ảnh letterbox (N, 4) → pixel ảnh gốc, cắt trong khung ảnh gốc."""
    out = _as_boxes(boxes)
    out[:, [0, 2]] -= info.pad[0]
    out[:, [1, 3]] -= info.pad[1]
    out /= info.scale
    w, h = info.orig_size
    out[:, [0, 2]] = np.clip(out[:, [0, 2]], 0, w)
    out[:, [1, 3]] = np.clip(out[:, [1, 3]], 0, h)
    return out
