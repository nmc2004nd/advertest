"""Model Ultralytics đăng ký qua web bằng safetensors (state_dict), có gradient.

- Mạng dựng lại từ config `<architecture>.yaml` có sẵn trong gói Ultralytics
  (`ULTRALYTICS_ARCHITECTURES`, số class theo `card.class_names`), rồi nạp state dict bằng
  `safetensors` với `strict=True`. Không bao giờ dùng `torch.load` trên file của web: pickle đổi
  đuôi bị từ chối khi đọc header, không chạy code (mission.md nguyên tắc 10).
- Checkpoint lưu bằng bản Ultralytics cũ có thể có bias ở vài `Conv2d` mà config hiện tại bỏ (ví
  dụ `attn.pe.conv.bias` của `yolo12n.pt` phát hành): thêm đúng tham số bias đó vào mạng trước khi
  nạp, nên kết quả bằng checkpoint gốc. Khóa thừa hoặc thiếu khác vẫn là lỗi.
- `export_safetensors` chạy trên máy người dùng, với file `.pt` của chính họ: nạp checkpoint bằng
  Ultralytics (pickle), ghi state dict float32 kèm metadata `framework`, `architecture`, `names`,
  `imgsz` để form đăng ký trên web tự điền.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import torch
from safetensors.torch import save_file
from torch import nn
from ultralytics.nn.tasks import DetectionModel

from advertest_contracts.models import (
    ULTRALYTICS_ARCHITECTURES,
    ULTRALYTICS_INPUT_SIZE,
    ModelCard,
)
from ml_core.models.torchvision_detection import StateDict, read_state
from ml_core.models.wrapper import class_names, load_detection_model

_detection_model = cast(Callable[..., DetectionModel], DetectionModel)


def looks_like_safetensors(head: bytes) -> bool:
    """8 byte đầu là độ dài header (u64 LE), byte thứ 9 mở JSON; pickle bắt đầu bằng 0x80, zip
    bằng `PK`."""
    if len(head) < 9:
        return False
    length = int.from_bytes(head[:8], "little")
    return 0 < length < 100 * 1024 * 1024 and head[8:9] == b"{"


def _add_missing_conv_bias(model: nn.Module, state: StateDict) -> None:
    modules = dict(model.named_modules())
    for key in sorted(set(state) - set(model.state_dict())):
        parent, _, leaf = key.rpartition(".")
        conv = modules.get(parent)
        if leaf != "bias" or not isinstance(conv, nn.Conv2d) or conv.bias is not None:
            continue  # để load_state_dict(strict=True) báo khóa thừa
        conv.bias = nn.Parameter(torch.zeros(conv.out_channels, dtype=state[key].dtype))


def build_model(card: ModelCard, weights: Path | bytes) -> DetectionModel:
    """`DetectionModel` float32 từ safetensors của kiến trúc `card.architecture`."""
    if card.architecture not in ULTRALYTICS_ARCHITECTURES:
        allowed = ", ".join(ULTRALYTICS_ARCHITECTURES)
        raise ValueError(
            f"Kiến trúc Ultralytics {card.architecture!r} không được hỗ trợ ({allowed})"
        )
    state = read_state(weights)
    model = _detection_model(f"{card.architecture}.yaml", nc=len(card.class_names), verbose=False)
    _add_missing_conv_bias(model, state)
    try:
        model.load_state_dict(state, strict=True)
    except RuntimeError as exc:
        raise ValueError(
            f"Weights không khớp {card.architecture} với {len(card.class_names)} class: {exc}"
        ) from exc
    cast(Any, model).names = dict(enumerate(card.class_names))
    return model.float().eval()


def load_ultralytics(card: ModelCard, weights: Path | bytes) -> DetectionModel:
    """Safetensors (đăng ký qua web) → `build_model`; còn lại là `.pt` đăng ký qua CLI."""
    if isinstance(weights, bytes):
        head = weights[:9]
    else:
        with weights.open("rb") as f:
            head = f.read(9)
    if looks_like_safetensors(head):
        return build_model(card, weights)
    if isinstance(weights, bytes):
        raise ValueError("Weights Ultralytics dạng bytes phải là safetensors")
    return load_detection_model(weights)


_CANONICAL = re.compile(r"^yolov?(8|9|11|12)([a-z])$")


def architecture_of(model: nn.Module, checkpoint: Path) -> str:
    """Tên trong `ULTRALYTICS_ARCHITECTURES` từ `yaml_file` của model hoặc tên file, ví dụ
    `yolov12n.yaml` → `yolo12n`, `yolov8n.pt` → `yolov8n`."""
    for source in (getattr(model, "yaml", {}).get("yaml_file"), checkpoint.name):
        match = _CANONICAL.match(Path(str(source or "")).stem.lower())
        if match:
            version, scale = match.groups()
            name = f"yolo{'v' if version in ('8', '9') else ''}{version}{scale}"
            if name in ULTRALYTICS_ARCHITECTURES:
                return name
    raise ValueError(
        f"Không nhận ra kiến trúc của {checkpoint.name}; truyền --architecture "
        f"(một trong {', '.join(ULTRALYTICS_ARCHITECTURES)})"
    )


def export_safetensors(
    checkpoint: Path, output: Path, architecture: str | None = None
) -> tuple[str, list[str]]:
    """Ghi state dict của checkpoint `.pt` ra `output`; trả (kiến trúc, tên class)."""
    model = load_detection_model(checkpoint)
    arch = architecture or architecture_of(model, checkpoint)
    if arch not in ULTRALYTICS_ARCHITECTURES:
        raise ValueError(f"Kiến trúc {arch!r} không thuộc {', '.join(ULTRALYTICS_ARCHITECTURES)}")
    names = class_names(model)
    state = {
        k: (v.float() if v.is_floating_point() else v).detach().contiguous()
        for k, v in model.state_dict().items()
    }
    metadata = {
        "framework": "ultralytics",
        "architecture": arch,
        "names": json.dumps(names, ensure_ascii=False),
        "imgsz": str(ULTRALYTICS_INPUT_SIZE),
    }
    save_file(state, str(output), metadata=metadata)
    return arch, names
