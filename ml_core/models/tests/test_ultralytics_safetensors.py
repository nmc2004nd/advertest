import json
import pickle
from pathlib import Path

import pytest
import torch
from safetensors import safe_open
from safetensors.torch import load_file, save_file
from torch import nn

from ml_core.models.tests.conftest import make_card
from ml_core.models.ultralytics_safetensors import (
    architecture_of,
    build_model,
    load_ultralytics,
    looks_like_safetensors,
)
from ml_core.models.wrapper import class_names, load_detection_model

COCO = [f"c{i}" for i in range(80)]


def _outputs(model: nn.Module, seed: int = 0) -> torch.Tensor:
    torch.manual_seed(seed)
    with torch.no_grad():
        result: torch.Tensor = model.eval()(torch.rand(1, 3, 640, 640))[0]
    return result


def test_export_then_build_matches_checkpoint(random_weights: Path, yolo_safetensors: Path) -> None:
    original = load_detection_model(random_weights)
    rebuilt = build_model(
        make_card(yolo_safetensors, "ultralytics", "yolov8n", COCO), yolo_safetensors
    )
    assert torch.equal(_outputs(original), _outputs(rebuilt))
    assert class_names(rebuilt) == COCO


def test_export_writes_metadata_for_the_web_form(yolo_safetensors: Path) -> None:
    with safe_open(str(yolo_safetensors), "pt") as f:
        meta = f.metadata()
    assert meta["framework"] == "ultralytics" and meta["architecture"] == "yolov8n"
    assert meta["imgsz"] == "640" and len(json.loads(meta["names"])) == 80


def test_load_ultralytics_dispatches_on_content(
    random_weights: Path, yolo_safetensors: Path
) -> None:
    card = make_card(yolo_safetensors, "ultralytics", "yolov8n", COCO)
    assert class_names(load_ultralytics(card, yolo_safetensors.read_bytes())) == COCO
    assert len(class_names(load_ultralytics(card, random_weights))) == 80  # `.pt` của CLI
    with pytest.raises(ValueError, match="safetensors"):
        load_ultralytics(card, pickle.dumps({"w": 1}))


def test_old_checkpoint_conv_bias_is_kept(yolo_safetensors: Path, tmp_path: Path) -> None:
    # Checkpoint của bản Ultralytics cũ có bias ở Conv2d mà config hiện tại bỏ.
    state = load_file(str(yolo_safetensors))
    key = next(k for k in state if k.endswith(".conv.weight"))
    bias = key.removesuffix("weight") + "bias"
    assert bias not in state
    state[bias] = torch.full((state[key].shape[0],), 0.5)
    path = tmp_path / "old.safetensors"
    save_file(state, str(path))
    model = build_model(make_card(path, "ultralytics", "yolov8n", COCO), path)
    assert torch.equal(model.state_dict()[bias], state[bias])


def test_wrong_weights_or_architecture(yolo_safetensors: Path) -> None:
    with pytest.raises(ValueError, match="không khớp yolo11n"):
        build_model(make_card(yolo_safetensors, "ultralytics", "yolo11n", COCO), yolo_safetensors)
    with pytest.raises(ValueError, match="không được hỗ trợ"):
        build_model(make_card(yolo_safetensors, "ultralytics", "yolov5s", COCO), yolo_safetensors)


def test_looks_like_safetensors(yolo_safetensors: Path) -> None:
    assert looks_like_safetensors(yolo_safetensors.read_bytes()[:9])
    assert not looks_like_safetensors(pickle.dumps({"w": 1}))
    assert not looks_like_safetensors(b"PK\x03\x04" + b"\0" * 5)


@pytest.mark.parametrize(
    ("filename", "expected"),
    [("yolov8n.pt", "yolov8n"), ("yolov9t.pt", "yolov9t"), ("yolo11s.pt", "yolo11s"),
     ("yolov12n.pt", "yolo12n"), ("YOLO12x.pt", "yolo12x")],
)  # fmt: skip
def test_architecture_from_file_name(filename: str, expected: str) -> None:
    assert architecture_of(nn.Module(), Path(filename)) == expected


def test_unknown_architecture_needs_option() -> None:
    with pytest.raises(ValueError, match="--architecture"):
        architecture_of(nn.Module(), Path("best.pt"))
