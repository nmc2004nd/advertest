"""Ảnh của run: mask letterbox, PNG hiển thị, ảnh nhiễu khuếch đại, thumbnail WebP."""

from __future__ import annotations

import io
from collections.abc import Sequence
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from advertest_contracts.enums import AttackKind, PerturbationImageKind
from advertest_contracts.models import AttackSpec
from ml_core.preprocess import LetterboxInfo

THUMB_WIDTH = 320  # requirements.md Phase 3, mục Failure case trong chế độ batch


def letterbox_mask(infos: Sequence[LetterboxInfo]) -> NDArray[np.float32]:
    """(N, 1, size, size): 1 ở vùng ảnh thật, 0 ở vùng pad (cùng hình học với `letterbox`)."""
    size = infos[0].size
    mask = np.zeros((len(infos), 1, size, size), dtype=np.float32)
    for i, info in enumerate(infos):
        width, height = info.orig_size
        new_w = max(1, min(size, round(width * info.scale)))
        new_h = max(1, min(size, round(height * info.scale)))
        left, top = info.pad
        mask[i, :, top : top + new_h, left : left + new_w] = 1.0
    return mask


def bbox(box: NDArray[Any]) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = (float(v) for v in np.asarray(box).reshape(4))
    return x1, y1, x2, y2


def _pil(image: NDArray[np.float32]) -> Image.Image:
    """(C, H, W) trong [0, 1] → ảnh RGB 8-bit (chỉ để hiển thị)."""
    pixels = np.round(np.clip(image, 0.0, 1.0) * 255).astype(np.uint8).transpose(1, 2, 0)
    return Image.fromarray(pixels)


def png_bytes(image: NDArray[np.float32]) -> bytes:
    buffer = io.BytesIO()
    _pil(image).save(buffer, format="PNG")
    return buffer.getvalue()


def thumbnail_webp(image: NDArray[np.float32], width: int = THUMB_WIDTH) -> bytes:
    """Thumbnail WebP rộng `width` px, giữ tỷ lệ ảnh (ảnh letterbox 640x640 → 320x320)."""
    pil = _pil(image)
    height = max(1, round(pil.height * width / pil.width))
    buffer = io.BytesIO()
    pil.resize((width, height), Image.Resampling.LANCZOS).save(buffer, format="WEBP", quality=85)
    return buffer.getvalue()


def amplified_perturbation(
    clean: NDArray[np.float32], adversarial: NDArray[np.float32], linf_eps: float | None
) -> NDArray[np.float32]:
    """Ảnh nhiễu khuếch đại: `0.5 + δ / (2·eps)` với L∞; `0.5 + δ / (2·max|δ|)` với L2
    (`linf_eps = None`), δ = 0 thì toàn ảnh 0.5; cắt về [0, 1]."""
    delta = adversarial.astype(np.float64) - clean.astype(np.float64)
    scale = linf_eps if linf_eps is not None else float(np.abs(delta).max())
    if scale <= 0:
        return np.full(clean.shape, 0.5, dtype=np.float32)
    return np.clip(0.5 + delta / (2 * scale), 0.0, 1.0).astype(np.float32)


def difference_image(
    clean: NDArray[np.float32], adversarial: NDArray[np.float32]
) -> NDArray[np.float32]:
    """Vùng khác biệt `|δ| / max|δ|` theo từng kênh (Phase 6, plan task 19): đen ở chỗ không đổi,
    sáng ở chỗ bị biến đổi; δ = 0 thì toàn ảnh 0."""
    delta = np.abs(adversarial.astype(np.float64) - clean.astype(np.float64))
    peak = float(delta.max())
    if peak <= 0:
        return np.zeros(clean.shape, dtype=np.float32)
    return (delta / peak).astype(np.float32)


def perturbation_kind(spec: AttackSpec) -> PerturbationImageKind:
    """Nội dung ảnh thứ ba theo loại phép thử: nhiễu khuếch đại (FGSM, PGD), vị trí patch (spec
    cần train), vùng khác biệt (corruption, occlusion)."""
    if spec.kind != AttackKind.ATTACK:
        return PerturbationImageKind.DIFFERENCE
    if spec.requires_training:
        return PerturbationImageKind.PATCH_LOCATION
    return PerturbationImageKind.AMPLIFIED_NOISE


def third_image(
    kind: PerturbationImageKind,
    clean: NDArray[np.float32],
    adversarial: NDArray[np.float32],
    linf_eps: float | None,
) -> NDArray[np.float32]:
    """Ảnh thứ ba của failure case (chưa làm mờ)."""
    if kind == PerturbationImageKind.AMPLIFIED_NOISE:
        return amplified_perturbation(clean, adversarial, linf_eps)
    return difference_image(clean, adversarial)
