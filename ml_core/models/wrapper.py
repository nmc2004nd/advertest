"""Wrapper Ultralytics YOLO cho estimator `PyTorchYolo` của ART.

Hai chế độ (requirements.md Phase 1, mục Wrapper và estimator):
- predict (`training = False`): NMS với `conf`, `iou`, `max_det` truyền vào, trả list dict
  `{"boxes", "labels", "scores"}`, box xyxy pixel trong không gian letterbox.
- loss (`training = True`, ART bật khi tính gradient): loss detection của Ultralytics,
  khả vi theo ảnh.

Model Ultralytics bên trong **luôn ở eval** và tham số bị đóng băng: `train()` của wrapper chỉ đổi
chế độ của wrapper, nên BatchNorm không cập nhật running stats khi ART tính gradient.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import torch
from torch import nn
from ultralytics.cfg import get_cfg
from ultralytics.models import YOLO
from ultralytics.nn.tasks import DetectionModel
from ultralytics.utils.loss import v8DetectionLoss
from ultralytics.utils.nms import non_max_suppression

from advertest_contracts.models import InferenceParams
from ml_core.preprocess import INPUT_SIZE

# Tham số inference mặc định khi tính mAP (requirements.md Phase 1, mục Đánh giá).
DEFAULT_INFERENCE_PARAMS = InferenceParams(
    conf=0.001, iou=0.7, max_det=300, operating_conf=0.25, input_size=INPUT_SIZE
)

LOSS_KEYS = ("loss_total", "loss_box", "loss_cls", "loss_dfl")


def load_detection_model(weights: Path) -> DetectionModel:
    """Nạp weights Ultralytics (.pt) thành `DetectionModel` float32."""
    model = YOLO(str(weights)).model
    if not isinstance(model, DetectionModel):
        raise ValueError(f"{weights} không phải model detection của Ultralytics")
    return model.float()


def class_names(model: DetectionModel) -> list[str]:
    """Tên class theo thứ tự index của model."""
    names = cast(dict[int, str], model.names)
    return [names[i] for i in range(len(names))]


class UltralyticsDetector(nn.Module):
    def __init__(self, model: DetectionModel, params: InferenceParams = DEFAULT_INFERENCE_PARAMS):
        super().__init__()
        model.eval()
        for p in model.parameters():
            p.requires_grad_(False)
        # Hệ số loss (box, cls, dfl) lấy từ cấu hình mặc định của Ultralytics; không phụ thuộc
        # train_args lưu trong checkpoint.
        cast(Any, model).args = get_cfg()
        self.model = model
        self.params = params
        self.criterion = v8DetectionLoss(model)
        self.training = False

    def train(self, mode: bool = True) -> UltralyticsDetector:
        """Chỉ đổi chế độ của wrapper; model bên trong giữ eval."""
        self.training = mode
        self.model.eval()
        return self

    @property
    def class_names(self) -> list[str]:
        return class_names(self.model)

    def forward(
        self, x: torch.Tensor, targets: torch.Tensor | None = None
    ) -> dict[str, torch.Tensor] | list[dict[str, torch.Tensor]]:
        if self.training:
            if targets is None:
                raise ValueError("Chế độ loss cần targets")
            return self.loss(x, targets)
        return self.predict(x)

    def loss(self, x: torch.Tensor, targets: torch.Tensor) -> dict[str, torch.Tensor]:
        """Loss detection.

        `targets` theo `PyTorchYolo._translate_labels`: (M, 6) = [ảnh, class, xc, yc, w, h],
        tọa độ chuẩn hóa về [0, 1].
        """
        batch = {
            "batch_idx": targets[:, 0],
            "cls": targets[:, 1:2],
            "bboxes": targets[:, 2:6],
        }
        loss, _ = self.criterion(self.model(x), batch)
        return {
            "loss_total": loss.sum(),
            "loss_box": loss[0],
            "loss_cls": loss[1],
            "loss_dfl": loss[2],
        }

    def predict(self, x: torch.Tensor) -> list[dict[str, torch.Tensor]]:
        raw = self.model(x)[0]
        detections = non_max_suppression(
            raw,
            conf_thres=self.params.conf,
            iou_thres=self.params.iou,
            max_det=self.params.max_det,
        )
        height, width = x.shape[-2:]
        out = []
        for det in detections:
            boxes = det[:, :4].clone()
            # Cắt về khung ảnh như postprocess của Ultralytics.
            boxes[:, [0, 2]] = boxes[:, [0, 2]].clamp(0, width)
            boxes[:, [1, 3]] = boxes[:, [1, 3]].clamp(0, height)
            out.append({"boxes": boxes, "labels": det[:, 5].long(), "scores": det[:, 4]})
        return out
