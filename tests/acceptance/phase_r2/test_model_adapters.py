"""validation.md Phase R2, Group 3 — Adapter model (`test_model_adapters.py`). Không cần DB.

- Fixture ONNX (`yolov8n.onnx`, xuất từ `yolov8n.pt`): box `xyxy` trong không gian letterbox,
  khớp prediction của adapter Ultralytics trên cùng ảnh; `capabilities.gradients = false`,
  `estimator()` báo `NoGradients`; attack white-box gặp model này → `IncompatibleAttack` (run
  `skipped`), corruption vẫn chạy và model vẫn predict được.
- Fixture safetensors torchvision (`fcos_resnet50_fpn_coco.safetensors`): inference và estimator ART
  chạy được FGSM một ảnh.
- `ModelProvider` LRU tối đa 2 model: model thứ 3 đẩy model ít dùng nhất ra khỏi cache.
- File pickle đổi đuôi `.safetensors` → nạp thất bại, không chạy code.

Interface (requirements.md Phase R2, Chốt ở Group 0, "Interface cho test nghiệm thu"):
`ml_core.models.adapter.open_adapter(card, weights, params, device)`,
`ModelProvider(store, *, load_model=None, max_models=2)`.
"""

from __future__ import annotations

import hashlib
import json
import pickle
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import torch
from PIL import Image
from safetensors import safe_open

from advertest_contracts.ids import content_id
from advertest_contracts.models import ModelCard
from attacks.builders import DEFAULT_REGISTRY, BuildContext, IncompatibleAttack
from attacks.registry import get_spec, load_catalog
from ml_core.models import adapter as adapter_module
from ml_core.models.adapter import ModelProvider, NoGradients
from ml_core.models.register import lib_versions
from ml_core.models.wrapper import DEFAULT_INFERENCE_PARAMS
from ml_core.preprocess.letterbox import letterbox
from ml_core.store import LocalStore

from .conftest import KITTI_IMAGE, ONNX_WEIGHTS, TORCHVISION_WEIGHTS, YOLO_WEIGHTS

NOW = datetime(2026, 10, 9, 8, 0, tzinfo=UTC)
PARAMS = DEFAULT_INFERENCE_PARAMS


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _card(
    path: Path, framework: str, architecture: str, class_names: list[str], gradients: bool
) -> ModelCard:
    sha = _sha(path)
    check: dict[str, Any] = {"passed": gradients, "checked_at": NOW.isoformat()}
    if not gradients:
        check["details"] = "Không hỗ trợ gradient"
    return ModelCard.model_validate(
        {
            "id": str(content_id(sha)),
            "name": path.stem,
            "framework": framework,
            "architecture": architecture,
            "weights_sha256": sha,
            "class_names": class_names,
            "input_size": 640,
            "supports_gradients": gradients,
            "gradient_check": check,
            "lib_versions": lib_versions().model_dump(),
        }
    )


def _coco80() -> list[str]:
    import onnxruntime as ort

    session = ort.InferenceSession(str(ONNX_WEIGHTS), providers=["CPUExecutionProvider"])
    names: list[str] = json.loads(session.get_modelmeta().custom_metadata_map["class_names"])
    return names


def _torchvision_names() -> list[str]:
    """Tên class theo index của FCOS COCO; tên trùng (`N/A`) được đánh số để không trùng."""
    with safe_open(str(TORCHVISION_WEIGHTS), "pt") as f:
        names: list[str] = json.loads(f.metadata()["class_names"])
    return [f"{n}_{i}" if names.count(n) > 1 else n for i, n in enumerate(names)]


@pytest.fixture(scope="module")
def image() -> np.ndarray:
    array, _ = letterbox(Image.open(KITTI_IMAGE))
    return array[None]


@pytest.fixture(scope="module")
def onnx_card() -> ModelCard:
    return _card(ONNX_WEIGHTS, "onnx", "yolov8n onnx (1, 84, 8400)", _coco80(), gradients=False)


def open_adapter(card: ModelCard, weights: Path, params: Any, device: str) -> Any:
    return adapter_module.open_adapter(card, weights, params, device)  # Group 3


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return float(inter / union) if union > 0 else 0.0


# ---------------------------------------------------------------- ONNX


def test_onnx_predictions_match_ultralytics(onnx_card: ModelCard, image: np.ndarray) -> None:
    onnx = open_adapter(onnx_card, ONNX_WEIGHTS, PARAMS, "cpu")
    yolo_card = _card(YOLO_WEIGHTS, "ultralytics", "yolov8n", _coco80(), gradients=True)
    yolo = open_adapter(yolo_card, YOLO_WEIGHTS, PARAMS, "cpu")

    (got,) = onnx.predict(image)
    (want,) = yolo.predict(image)
    assert got["boxes"].shape[1:] == (4,)
    boxes = got["boxes"]
    assert np.all(boxes[:, 2] >= boxes[:, 0]) and np.all(boxes[:, 3] >= boxes[:, 1])  # xyxy
    assert boxes.min() >= 0 and boxes.max() <= 640  # không gian letterbox
    strong = [i for i, s in enumerate(want["scores"]) if s >= 0.5]
    assert strong, "ảnh fixture phải có object rõ"
    for i in strong:
        matches = [
            j
            for j in range(len(boxes))
            if got["labels"][j] == want["labels"][i] and _iou(boxes[j], want["boxes"][i]) > 0.9
        ]
        assert matches, (i, want["boxes"][i], want["labels"][i])
        assert abs(float(got["scores"][matches[0]]) - float(want["scores"][i])) < 0.02


def test_onnx_has_no_gradients(onnx_card: ModelCard) -> None:
    onnx = open_adapter(onnx_card, ONNX_WEIGHTS, PARAMS, "cpu")
    assert onnx.capabilities.gradients is False
    assert onnx.class_names() == onnx_card.class_names
    with pytest.raises(NoGradients):
        onnx.estimator()


def test_onnx_white_box_incompatible_corruption_runs(
    onnx_card: ModelCard, image: np.ndarray
) -> None:
    """Như runner: model không có gradient → estimator None → attack white-box `skipped`."""
    onnx = open_adapter(onnx_card, ONNX_WEIGHTS, PARAMS, "cpu")
    estimator = onnx.estimator() if onnx.capabilities.gradients else None
    catalog = load_catalog()
    with pytest.raises(IncompatibleAttack):
        DEFAULT_REGISTRY.build(get_spec(catalog, name="fgsm"), BuildContext(estimator=estimator))
    fog = DEFAULT_REGISTRY.build(get_spec(catalog, name="fog"), BuildContext(estimator=estimator))
    attacked = fog.apply(image, [{}], 3.0, 0)
    assert not np.array_equal(attacked, image)
    (prediction,) = onnx.predict(attacked)
    assert set(prediction) >= {"boxes", "labels", "scores"}


# ---------------------------------------------------------------- torchvision safetensors


def test_torchvision_inference_and_fgsm(image: np.ndarray) -> None:
    card = _card(
        TORCHVISION_WEIGHTS, "torchvision", "fcos_resnet50_fpn", _torchvision_names(), True
    )
    adapter = open_adapter(card, TORCHVISION_WEIGHTS, PARAMS, "cpu")
    assert adapter.capabilities.gradients is True
    (prediction,) = adapter.predict(image)
    boxes = prediction["boxes"]
    assert len(boxes) > 0
    assert boxes.min() >= 0 and boxes.max() <= 640
    assert np.all(boxes[:, 2] >= boxes[:, 0]) and np.all(boxes[:, 3] >= boxes[:, 1])

    fgsm = get_spec(load_catalog(), name="fgsm")
    perturbation = DEFAULT_REGISTRY.build(fgsm, BuildContext(estimator=adapter.estimator()))
    targets = [{k: prediction[k] for k in ("boxes", "labels", "scores")}]
    attacked = perturbation.apply(image, targets, 4.0, 0)
    delta = np.abs(attacked - image)
    assert attacked.dtype == np.float32 and attacked.shape == image.shape
    assert delta.max() > 0
    assert delta.max() <= 4 / 255 + 1e-6


def test_pickle_renamed_safetensors_is_rejected_without_running_code(tmp_path: Path) -> None:
    assert hasattr(adapter_module, "open_adapter")  # lỗi phải đến từ việc nạp, không từ thiếu hàm
    marker = tmp_path / "da-chay-code"

    class Payload:
        def __reduce__(self) -> tuple[Any, tuple[Any, ...]]:
            return (Path.touch, (marker,))

    for name, write in (
        ("raw.safetensors", lambda p: p.write_bytes(pickle.dumps(Payload()))),
        ("torch.safetensors", lambda p: torch.save({"w": Payload()}, p)),
    ):
        path = tmp_path / name
        write(path)
        card = _card(path, "torchvision", "fcos_resnet50_fpn", _torchvision_names(), True)
        with pytest.raises(Exception) as excinfo:
            adapter = open_adapter(card, path, PARAMS, "cpu")
            adapter.predict(np.zeros((1, 3, 640, 640), dtype=np.float32))
        assert not isinstance(excinfo.value, AssertionError)
        assert not marker.exists(), name


# ---------------------------------------------------------------- ModelProvider


def test_model_provider_lru_two_models(tmp_path: Path, onnx_card: ModelCard) -> None:
    def never(card: ModelCard) -> Any:
        raise AssertionError("adapter nạp lười: test không predict")

    provider = ModelProvider(LocalStore(tmp_path), load_model=never)
    base = _card(YOLO_WEIGHTS, "ultralytics", "yolov8n", _coco80(), gradients=True)
    cards = {}
    for name in ("a", "b", "c"):
        sha = hashlib.sha256(name.encode()).hexdigest()
        cards[name] = base.model_copy(
            update={"weights_sha256": sha, "id": content_id(sha), "name": name}
        )
    a = provider.get(cards["a"], PARAMS, "cpu")
    b = provider.get(cards["b"], PARAMS, "cpu")
    assert provider.get(cards["a"], PARAMS, "cpu") is a  # a vừa dùng; b ít dùng nhất
    c = provider.get(cards["c"], PARAMS, "cpu")  # đẩy b ra
    assert provider.get(cards["a"], PARAMS, "cpu") is a
    assert provider.get(cards["c"], PARAMS, "cpu") is c
    b2 = provider.get(cards["b"], PARAMS, "cpu")  # nạp lại; đẩy a (ít dùng nhất) ra
    assert b2 is not b
    assert provider.get(cards["c"], PARAMS, "cpu") is c
    assert provider.get(cards["a"], PARAMS, "cpu") is not a
