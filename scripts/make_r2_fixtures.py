"""Sinh fixture model của Phase R2 (requirements.md Phase R2, Chốt ở Group 0, mục Fixture).

Chạy một lần trên máy người duyệt, rồi upload hai file lên release `fixtures-v2` và ghi sha256 vào
`tests/fixtures/checksums.json`:

    uv run --extra cpu --with onnx python scripts/make_r2_fixtures.py

- `yolov8n.onnx`: xuất từ `tests/fixtures/yolov8n.pt` (cần `make fixtures` trước), đầu vào
  `images` (1, 3, 640, 640), đầu ra kiểu YOLO `output0` (1, 4 + C, N) chưa NMS; `metadata_props`
  có `class_names` (JSON).
- `fcos_resnet50_fpn_coco.safetensors`: weights COCO_V1 của torchvision cho `fcos_resnet50_fpn`;
  metadata có `architecture` và `class_names` (JSON, theo index của model).

Gói `onnx` chỉ cần cho script này, không vào lock (tech-stack.md mục 11).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
INPUT_SIZE = 640


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _YoloRaw(torch.nn.Module):
    """Chỉ lấy tensor đã giải mã (1, 4 + C, N) của Detect ở chế độ eval."""

    def __init__(self, model: torch.nn.Module) -> None:
        super().__init__()
        self.model = model

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        out = self.model(images)
        return out[0] if isinstance(out, (list, tuple)) else out


def make_onnx(out: Path) -> None:
    import onnx
    from ultralytics import YOLO

    weights = FIXTURES / "yolov8n.pt"
    if not weights.exists():
        raise SystemExit(f"Thiếu {weights}; chạy `make fixtures` trước")
    yolo = YOLO(str(weights))
    model = yolo.model.eval()
    for p in model.parameters():
        p.requires_grad_(False)
    dummy = torch.zeros(1, 3, INPUT_SIZE, INPUT_SIZE)
    torch.onnx.export(
        _YoloRaw(model),
        (dummy,),
        str(out),
        input_names=["images"],
        output_names=["output0"],
        opset_version=17,
        dynamo=False,
    )
    proto = onnx.load(str(out))
    names = [yolo.names[i] for i in sorted(yolo.names)]
    entry = proto.metadata_props.add()
    entry.key, entry.value = "class_names", json.dumps(names)
    onnx.checker.check_model(proto)
    onnx.save(proto, str(out))


def make_safetensors(out: Path) -> None:
    from safetensors.torch import save_file
    from torchvision.models.detection import FCOS_ResNet50_FPN_Weights, fcos_resnet50_fpn

    weights = FCOS_ResNet50_FPN_Weights.COCO_V1
    model = fcos_resnet50_fpn(weights=weights).eval()
    state = {k: v.detach().contiguous() for k, v in model.state_dict().items()}
    metadata = {
        "architecture": "fcos_resnet50_fpn",
        "class_names": json.dumps(list(weights.meta["categories"])),
    }
    save_file(state, str(out), metadata=metadata)


def main() -> int:
    torch.manual_seed(0)
    targets = {
        "yolov8n.onnx": make_onnx,
        "fcos_resnet50_fpn_coco.safetensors": make_safetensors,
    }
    for name, make in targets.items():
        out = FIXTURES / name
        make(out)
        print(f"{name}\t{out.stat().st_size} byte\tsha256 {_sha256(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
