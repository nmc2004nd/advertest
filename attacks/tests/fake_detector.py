"""Estimator giả cho test attack: `PyTorchYolo` của ART bọc một model rất nhỏ trên ảnh 64x64.

Loss là tổng theo từng ảnh, phi tuyến theo ảnh (để các bước PGD khác nhau) và phụ thuộc số box
ground truth của ảnh đó. Model không có trạng thái thay đổi theo batch nên kết quả không phụ
thuộc batch size.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
from art.estimators.object_detection import PyTorchYolo
from torch import nn

SIZE = 64
PAD = 16  # letterbox giả: hàng [0, PAD) và [SIZE - PAD, SIZE) là vùng pad


class TinyDetector(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        generator = torch.Generator().manual_seed(0)
        self.weight = nn.Parameter(torch.randn(3, SIZE, SIZE, generator=generator))
        self.weight.requires_grad_(False)

    def forward(
        self, x: torch.Tensor, targets: torch.Tensor | None = None
    ) -> dict[str, torch.Tensor] | list[dict[str, torch.Tensor]]:
        if self.training:
            assert targets is not None
            counts = torch.bincount(targets[:, 0].long(), minlength=x.shape[0]).to(x.dtype)
            per_image = (torch.sin(6.0 * x) * self.weight).flatten(1).sum(1)
            return {"loss_total": (per_image * (1.0 + counts)).sum()}
        empty = {
            "boxes": torch.zeros((0, 4)),
            "labels": torch.zeros((0,), dtype=torch.long),
            "scores": torch.zeros((0,)),
        }
        return [dict(empty) for _ in range(x.shape[0])]


def estimator() -> PyTorchYolo:
    return PyTorchYolo(
        model=TinyDetector(),
        input_shape=(3, SIZE, SIZE),
        clip_values=(0.0, 1.0),
        channels_first=True,
        attack_losses=("loss_total",),
        device_type="cpu",
    )


def images(n: int = 5, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    out = rng.uniform(0.0, 1.0, size=(n, 3, SIZE, SIZE)).astype(np.float32)
    out[:, :, :PAD] = 114 / 255
    out[:, :, SIZE - PAD :] = 114 / 255
    # Có điểm ảnh sát biên [0, 1] để kiểm tra clip.
    out[:, :, PAD, :4] = 0.0
    out[:, :, PAD + 1, :4] = 1.0
    return out


def mask(n: int = 5) -> np.ndarray:
    out = np.zeros((n, 1, SIZE, SIZE), dtype=np.float32)
    out[:, :, PAD : SIZE - PAD] = 1.0
    return out


def targets(n: int = 5) -> list[dict[str, Any]]:
    """Box ground truth xyxy; ảnh cuối không có box nào."""
    out = []
    for i in range(n):
        k = 0 if i == n - 1 else 1 + i % 2
        boxes = np.asarray([[4.0 + j, 20.0, 30.0 + j, 40.0] for j in range(k)], dtype=np.float32)
        out.append({"boxes": boxes.reshape(k, 4), "labels": np.zeros((k,), dtype=np.int64)})
    return out
