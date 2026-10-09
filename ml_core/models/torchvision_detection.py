"""Model cho adapter `torchvision_detection`: weights safetensors cho kiến trúc torchvision trong
danh sách cho phép (requirements.md Phase R2, mục Model qua web).

- Dựng kiến trúc với `weights=None, weights_backbone=None` (không tải gì từ mạng), rồi nạp state
  dict bằng `safetensors`. Không bao giờ dùng `torch.load`: file pickle đổi đuôi bị từ chối khi đọc
  header, không chạy code (mission.md nguyên tắc 10).
- Transform của torchvision resize về đúng `input_size` (min = max = 640): model thấy ảnh letterbox
  như YOLO, box trả về trong không gian letterbox (người duyệt chốt 2026-10-09).
- `InferenceParams` thay ngưỡng hậu xử lý của torchvision: `conf` → ngưỡng score, `iou` → NMS,
  `max_det` → số box tối đa mỗi ảnh. Normalize ImageNet nằm trong transform, nên ảnh vào là [0, 1].
- Estimator là `PyTorchObjectDetector` của ART; `attack_losses` là toàn bộ loss của kiến trúc. ART
  giữ BatchNorm ở eval khi tính loss. `TorchvisionDetector` bỏ box suy biến (rộng hoặc cao bằng 0,
  FCOS có thể dự đoán) khỏi target trước khi tính loss, vì torchvision từ chối các box này.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from art.estimators.object_detection import PyTorchObjectDetector
from safetensors.torch import load, load_file
from torchvision.models import detection

from advertest_contracts.models import InferenceParams, ModelCard

StateDict = dict[str, torch.Tensor]


@dataclass(frozen=True)
class Architecture:
    build: Callable[..., torch.nn.Module]
    attack_losses: tuple[str, ...]
    # Khóa tham số hậu xử lý của hàm dựng: (ngưỡng score, ngưỡng NMS, số box tối đa).
    param_keys: tuple[str, str, str]
    # Trọng số của lớp phân loại cuối và số anchor mỗi vị trí: số class = shape[0] / anchor.
    cls_weight: str
    anchors: int


_ONE_STAGE = ("score_thresh", "nms_thresh", "detections_per_img")

ARCHITECTURES: dict[str, Architecture] = {
    "fasterrcnn_resnet50_fpn_v2": Architecture(
        detection.fasterrcnn_resnet50_fpn_v2,
        ("loss_classifier", "loss_box_reg", "loss_objectness", "loss_rpn_box_reg"),
        ("box_score_thresh", "box_nms_thresh", "box_detections_per_img"),
        "roi_heads.box_predictor.cls_score.weight",
        1,
    ),
    "retinanet_resnet50_fpn_v2": Architecture(
        detection.retinanet_resnet50_fpn_v2,
        ("classification", "bbox_regression"),
        _ONE_STAGE,
        "head.classification_head.cls_logits.weight",
        9,
    ),
    "fcos_resnet50_fpn": Architecture(
        detection.fcos_resnet50_fpn,
        ("classification", "bbox_regression", "bbox_ctrness"),
        _ONE_STAGE,
        "head.classification_head.cls_logits.weight",
        1,
    ),
}


def architecture(name: str) -> Architecture:
    try:
        return ARCHITECTURES[name]
    except KeyError:
        allowed = ", ".join(sorted(ARCHITECTURES))
        raise ValueError(f"Kiến trúc torchvision {name!r} không được hỗ trợ ({allowed})") from None


def read_state(weights: Path | bytes) -> StateDict:
    """State dict từ file hoặc bytes safetensors; nội dung không phải safetensors → lỗi."""
    return load(weights) if isinstance(weights, bytes) else load_file(weights)


def state_num_classes(card: ModelCard, state: StateDict) -> int:
    arch = architecture(card.architecture)
    weight = state.get(arch.cls_weight)
    if weight is None:
        raise ValueError(f"Weights thiếu {arch.cls_weight} của {card.architecture}")
    return int(weight.shape[0]) // arch.anchors


def build_model(card: ModelCard, state: StateDict, params: InferenceParams) -> torch.nn.Module:
    """Model eval, tham số đóng băng; số class của weights phải bằng `len(card.class_names)`."""
    arch = architecture(card.architecture)
    num_classes = state_num_classes(card, state)
    if num_classes != len(card.class_names):
        raise ValueError(
            f"Weights có {num_classes} class, model card khai báo {len(card.class_names)}"
        )
    score_key, nms_key, max_det_key = arch.param_keys
    kwargs: dict[str, Any] = {
        score_key: params.conf,
        nms_key: params.iou,
        max_det_key: params.max_det,
    }
    model = arch.build(
        weights=None,
        weights_backbone=None,
        num_classes=num_classes,
        min_size=card.input_size,
        max_size=card.input_size,
        **kwargs,
    )
    # Weights huấn luyện sẵn có thể dùng FrozenBatchNorm2d (không có `num_batches_tracked`), còn
    # kiến trúc dựng không weights dùng BatchNorm2d; ở eval hai loại tính như nhau.
    missing, unexpected = model.load_state_dict(state, strict=False)
    missing = [k for k in missing if not k.endswith("num_batches_tracked")]
    unexpected = [k for k in unexpected if not k.endswith("num_batches_tracked")]
    if missing or unexpected:
        raise ValueError(
            f"Weights không khớp {card.architecture}: thiếu {missing[:5]}, thừa {unexpected[:5]}"
        )
    model.eval()
    for p in model.parameters():
        p.requires_grad_(False)
    return model


class TorchvisionDetector(torch.nn.Module):
    """Bọc model torchvision cho ART: chế độ loss bỏ box suy biến khỏi target; predict như cũ."""

    def __init__(self, model: torch.nn.Module) -> None:
        super().__init__()
        self.model = model

    def forward(
        self, images: torch.Tensor, targets: list[dict[str, torch.Tensor]] | None = None
    ) -> Any:
        if self.training and targets is not None:
            targets = [_valid_boxes(t) for t in targets]
        return self.model(images, targets)


def _valid_boxes(target: dict[str, torch.Tensor]) -> dict[str, torch.Tensor]:
    boxes = target["boxes"]
    keep = (boxes[:, 2] > boxes[:, 0]) & (boxes[:, 3] > boxes[:, 1])
    return {k: v[keep] if k in ("boxes", "labels") else v for k, v in target.items()}


def build_estimator(
    card: ModelCard, model: torch.nn.Module, device: str = "cpu"
) -> PyTorchObjectDetector:
    """`PyTorchObjectDetector` với input (3, S, S) float32 [0, 1], channels_first."""
    size = card.input_size
    return PyTorchObjectDetector(
        model=TorchvisionDetector(model).to(torch.device(device)),
        input_shape=(3, size, size),
        clip_values=(0.0, 1.0),
        channels_first=True,
        attack_losses=architecture(card.architecture).attack_losses,
        device_type="cpu" if torch.device(device).type == "cpu" else "gpu",
    )
