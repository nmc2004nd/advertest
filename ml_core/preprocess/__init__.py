"""Tiền xử lý ảnh theo quy ước tech-stack.md mục 2.1."""

from ml_core.preprocess.letterbox import (
    INPUT_SIZE,
    LETTERBOX_CONFIG,
    PAD_VALUE,
    LetterboxInfo,
    boxes_from_letterbox,
    boxes_to_letterbox,
    letterbox,
    letterbox_info,
)

__all__ = [
    "INPUT_SIZE",
    "LETTERBOX_CONFIG",
    "PAD_VALUE",
    "LetterboxInfo",
    "boxes_from_letterbox",
    "boxes_to_letterbox",
    "letterbox",
    "letterbox_info",
]
