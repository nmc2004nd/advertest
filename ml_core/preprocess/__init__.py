"""Tiền xử lý ảnh theo quy ước tech-stack.md mục 2.1."""

from ml_core.preprocess.letterbox import (
    INPUT_SIZE,
    PAD_VALUE,
    LetterboxInfo,
    boxes_from_letterbox,
    boxes_to_letterbox,
    letterbox,
)

__all__ = [
    "INPUT_SIZE",
    "PAD_VALUE",
    "LetterboxInfo",
    "boxes_from_letterbox",
    "boxes_to_letterbox",
    "letterbox",
]
