import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import torch
from numpy.typing import NDArray
from safetensors.torch import load_file, save_file

from ml_core.models.adapter import ModelProvider, NoGradients, TorchvisionAdapter, open_adapter
from ml_core.models.register import weights_key
from ml_core.models.tests.conftest import FCOS_CLASSES, LOW_PARAMS, make_card
from ml_core.models.torchvision_detection import ARCHITECTURES, architecture, state_num_classes
from ml_core.store import LocalStore

ARCH = "fcos_resnet50_fpn"


@pytest.fixture(scope="module")
def adapter(fcos_weights: Path) -> TorchvisionAdapter:
    card = make_card(fcos_weights, "torchvision", ARCH, FCOS_CLASSES, gradients=True)
    result = open_adapter(card, fcos_weights, LOW_PARAMS, "cpu")
    assert isinstance(result, TorchvisionAdapter)
    return result


def test_allowed_architectures() -> None:
    assert set(ARCHITECTURES) == {
        "fasterrcnn_resnet50_fpn_v2",
        "retinanet_resnet50_fpn_v2",
        "fcos_resnet50_fpn",
    }
    with pytest.raises(ValueError, match="không được hỗ trợ"):
        architecture("maskrcnn_resnet50_fpn")


@pytest.mark.parametrize("name", sorted(ARCHITECTURES))
def test_num_classes_from_state(name: str, fcos_weights: Path) -> None:
    model = ARCHITECTURES[name].build(weights=None, weights_backbone=None, num_classes=5)
    card = make_card(fcos_weights, "torchvision", name, [f"c{i}" for i in range(5)])
    assert state_num_classes(card, model.state_dict()) == 5


def test_predict_in_letterbox_space(
    adapter: TorchvisionAdapter, images: NDArray[np.float32]
) -> None:
    preds = adapter.predict(images, batch_size=1)
    assert len(preds) == len(images)
    assert any(len(p["boxes"]) for p in preds)
    for pred in preds:
        assert set(pred) >= {"boxes", "labels", "scores"}
        boxes = pred["boxes"]
        assert boxes.shape[1:] == (4,)
        assert np.all(boxes[:, 2] >= boxes[:, 0]) and np.all(boxes[:, 3] >= boxes[:, 1])
        assert boxes.min() >= 0 and boxes.max() <= 640
        assert np.all(pred["scores"] >= LOW_PARAMS.conf)
        assert np.all((pred["labels"] >= 0) & (pred["labels"] < len(FCOS_CLASSES)))
        assert len(boxes) <= LOW_PARAMS.max_det


def test_params_and_input_size_reach_model(adapter: TorchvisionAdapter) -> None:
    model: Any = adapter.detector().model.model
    assert model.transform.min_size == (640,) and model.transform.max_size == 640
    assert model.score_thresh == LOW_PARAMS.conf
    assert model.nms_thresh == LOW_PARAMS.iou
    assert model.detections_per_img == LOW_PARAMS.max_det
    assert not model.training
    assert not any(p.requires_grad for p in model.parameters())


def test_estimator_gradient(adapter: TorchvisionAdapter, images: NDArray[np.float32]) -> None:
    estimator = adapter.estimator()
    x = images[:1]
    (pred,) = estimator.predict(x)
    targets = [{"boxes": pred["boxes"][:5], "labels": pred["labels"][:5]}]
    grad = np.asarray(estimator.loss_gradient(x, targets))
    assert grad.shape == x.shape
    assert np.all(np.isfinite(grad)) and np.any(grad != 0)
    # ART bật train() khi tính loss nhưng giữ BatchNorm ở eval.
    for layer in estimator.model.modules():
        if isinstance(layer, torch.nn.modules.batchnorm._BatchNorm):
            assert not layer.training


def test_degenerate_target_boxes_dropped(
    adapter: TorchvisionAdapter, images: NDArray[np.float32]
) -> None:
    targets = [
        {
            "boxes": np.array([[10, 10, 80, 90], [624, 568, 624, 569.3]], np.float32),
            "labels": np.array([1, 2]),
        }
    ]
    grad = np.asarray(adapter.estimator().loss_gradient(images[:1], targets))
    assert np.all(np.isfinite(grad)) and np.any(grad != 0)


def test_no_gradients_card(fcos_weights: Path, images: NDArray[np.float32]) -> None:
    card = make_card(fcos_weights, "torchvision", ARCH, FCOS_CLASSES, gradients=False)
    adapter = open_adapter(card, fcos_weights, LOW_PARAMS, "cpu")
    assert adapter.capabilities.gradients is False
    with pytest.raises(NoGradients):
        adapter.estimator()
    assert len(adapter.predict(images[:1])) == 1


def test_frozen_batchnorm_state_loads(
    fcos_weights: Path, tmp_path: Path, images: NDArray[np.float32], adapter: TorchvisionAdapter
) -> None:
    """Weights huấn luyện sẵn dùng FrozenBatchNorm2d: không có `num_batches_tracked`."""
    state = {k: v for k, v in load_file(fcos_weights).items() if "num_batches_tracked" not in k}
    path = tmp_path / "frozen.safetensors"
    save_file(state, str(path))
    card = make_card(path, "torchvision", ARCH, FCOS_CLASSES)
    got = open_adapter(card, path, LOW_PARAMS, "cpu").predict(images[:1])
    want = adapter.predict(images[:1])
    np.testing.assert_array_equal(got[0]["boxes"], want[0]["boxes"])


def test_mismatched_weights_rejected(fcos_weights: Path, tmp_path: Path) -> None:
    card = make_card(fcos_weights, "torchvision", ARCH, ["a", "b"])
    with pytest.raises(ValueError, match="3 class"):
        open_adapter(card, fcos_weights, LOW_PARAMS, "cpu").predict(
            np.zeros((1, 3, 640, 640), np.float32)
        )

    state = load_file(fcos_weights)
    state.pop("head.regression_head.bbox_ctrness.weight")
    path = tmp_path / "missing.safetensors"
    save_file(state, str(path))
    card = make_card(path, "torchvision", ARCH, FCOS_CLASSES)
    with pytest.raises(ValueError, match="không khớp"):
        open_adapter(card, path, LOW_PARAMS, "cpu").predict(np.zeros((1, 3, 640, 640), np.float32))


def test_unknown_architecture_rejected_on_open(fcos_weights: Path) -> None:
    card = make_card(fcos_weights, "torchvision", "yolov8n", FCOS_CLASSES)
    with pytest.raises(ValueError, match="không được hỗ trợ"):
        open_adapter(card, fcos_weights, LOW_PARAMS, "cpu")


class _Payload:
    def __init__(self, marker: Path) -> None:
        self.marker = marker

    def __reduce__(self) -> tuple[Any, tuple[Any, ...]]:
        return (Path.touch, (self.marker,))


def test_pickle_is_rejected_without_running_code(tmp_path: Path) -> None:
    marker = tmp_path / "ran"
    path = tmp_path / "evil.safetensors"
    path.write_bytes(pickle.dumps({"w": _Payload(marker)}))
    card = make_card(path, "torchvision", ARCH, FCOS_CLASSES)
    with pytest.raises(Exception) as excinfo:
        open_adapter(card, path, LOW_PARAMS, "cpu").predict(np.zeros((1, 3, 640, 640), np.float32))
    assert not isinstance(excinfo.value, AssertionError)
    assert not marker.exists()


def test_provider_reads_weights_from_store(
    fcos_weights: Path, tmp_path: Path, images: NDArray[np.float32], adapter: TorchvisionAdapter
) -> None:
    store = LocalStore(tmp_path)
    card = make_card(fcos_weights, "torchvision", ARCH, FCOS_CLASSES)
    store.put(weights_key(card.weights_sha256), fcos_weights.read_bytes())
    got = ModelProvider(store).get(card, LOW_PARAMS, "cpu").predict(images[:1])
    np.testing.assert_array_equal(got[0]["scores"], adapter.predict(images[:1])[0]["scores"])
