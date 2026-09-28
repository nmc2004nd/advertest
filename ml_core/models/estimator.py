"""Estimator ART cho model Ultralytics."""

from __future__ import annotations

import torch
from art.estimators.object_detection import PyTorchYolo
from ultralytics.nn.tasks import DetectionModel

from advertest_contracts.models import InferenceParams
from ml_core.models.wrapper import DEFAULT_INFERENCE_PARAMS, UltralyticsDetector
from ml_core.preprocess import INPUT_SIZE


def build_estimator(
    model: torch.nn.Module,
    params: InferenceParams = DEFAULT_INFERENCE_PARAMS,
    device: str = "cpu",
) -> PyTorchYolo:
    """`PyTorchYolo` với input (3, 640, 640) float32 [0, 1], channels_first.

    `model` là `DetectionModel` (được bọc bằng `UltralyticsDetector`) hoặc một module theo cùng
    giao diện với `UltralyticsDetector`.

    Dùng wrapper tự viết (không dùng `is_ultralytics=True` của ART) vì nhánh đó bật `train()`
    cho model khi tính loss và cố định `conf` của NMS.
    """
    torch_device = torch.device(device)
    if isinstance(model, DetectionModel):
        # Loss của Ultralytics giữ tensor theo device của model lúc tạo: chuyển device trước.
        model = UltralyticsDetector(model.to(torch_device), params)
    return PyTorchYolo(
        model=model,
        input_shape=(3, INPUT_SIZE, INPUT_SIZE),
        clip_values=(0.0, 1.0),
        channels_first=True,
        attack_losses=("loss_total",),
        device_type="cpu" if torch_device.type == "cpu" else "gpu",
    )
