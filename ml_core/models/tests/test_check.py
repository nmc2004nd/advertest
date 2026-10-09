import pickle
import uuid
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from advertest_contracts.models import ModelCard
from ml_core.models import check, onnx_model
from ml_core.models.check import check_model
from ml_core.models.tests.conftest import FCOS_CLASSES, LOW_PARAMS, make_card
from ml_core.models.tests.test_onnx_model import Arg, FakeSession, _yolo_raw, _yolo_session

TARGET = uuid.UUID(int=7)
ARCH = "fcos_resnet50_fpn"


def test_torchvision_passes_with_gradient_check(
    fcos_weights: Path, images: NDArray[np.float32]
) -> None:
    card = make_card(fcos_weights, "torchvision", ARCH, FCOS_CLASSES)
    result = check_model(
        card, fcos_weights, worker_target_id=TARGET, params=LOW_PARAMS, images=images[:1]
    )
    assert result.passed and result.details is None
    assert result.gradient_check is not None
    assert result.worker_target_id == TARGET


def test_gradient_error_keeps_model_usable(
    fcos_weights: Path, images: NDArray[np.float32], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object) -> None:
        raise RuntimeError("hỏng")

    monkeypatch.setattr(check, "run_gradient_check", broken)
    card = make_card(fcos_weights, "torchvision", ARCH, FCOS_CLASSES)
    result = check_model(
        card, fcos_weights, worker_target_id=TARGET, params=LOW_PARAMS, images=images[:1]
    )
    assert result.passed
    assert result.gradient_check is not None and not result.gradient_check.passed
    assert "hỏng" in (result.gradient_check.details or "")


def test_sha_mismatch(fcos_weights: Path, tmp_path: Path, images: NDArray[np.float32]) -> None:
    card = make_card(fcos_weights, "torchvision", ARCH, FCOS_CLASSES)
    other = tmp_path / "other.safetensors"
    other.write_bytes(fcos_weights.read_bytes() + b" ")
    result = check_model(card, other, worker_target_id=TARGET, images=images[:1])
    assert not result.passed and "sha256" in (result.details or "")
    assert result.gradient_check is None


def test_class_count_mismatch(fcos_weights: Path, images: NDArray[np.float32]) -> None:
    card = make_card(fcos_weights, "torchvision", ARCH, ["a", "b"])
    result = check_model(card, fcos_weights, worker_target_id=TARGET, images=images[:1])
    assert not result.passed and "3 class" in (result.details or "")


def test_pickle_fails_to_load(tmp_path: Path, images: NDArray[np.float32]) -> None:
    path = tmp_path / "evil.safetensors"
    path.write_bytes(pickle.dumps({"w": 1}))
    card = make_card(path, "torchvision", ARCH, FCOS_CLASSES)
    result = check_model(card, path, worker_target_id=TARGET, images=images[:1])
    assert not result.passed and (result.details or "").startswith("Nạp model thất bại")


def test_ultralytics_not_checked(random_weights: Path) -> None:
    card = make_card(random_weights, "ultralytics", "yolov8n", ["a"])
    with pytest.raises(ValueError, match="torchvision hoặc onnx"):
        check_model(card, random_weights, worker_target_id=TARGET)


def _onnx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, session: FakeSession, classes: list[str]
) -> tuple[Path, ModelCard]:
    weights = tmp_path / "m.onnx"
    weights.write_bytes(b"onnx")
    monkeypatch.setattr(onnx_model, "open_session", lambda source, device: session)
    return weights, make_card(weights, "onnx", "fake", classes)


def test_onnx_passes_without_gradient_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, images: NDArray[np.float32]
) -> None:
    session = _yolo_session(_yolo_raw(classes=2))
    weights, card = _onnx(tmp_path, monkeypatch, session, ["a", "b"])
    result = check_model(card, weights, worker_target_id=TARGET, params=LOW_PARAMS, images=images)
    assert result.passed and result.gradient_check is None
    assert session.batches == [1, 1]


def test_onnx_class_count_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, images: NDArray[np.float32]
) -> None:
    weights, card = _onnx(tmp_path, monkeypatch, _yolo_session(_yolo_raw(classes=2)), ["a"])
    result = check_model(card, weights, worker_target_id=TARGET, images=images)
    assert not result.passed and "2 class" in (result.details or "")


def test_onnx_label_out_of_range(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, images: NDArray[np.float32]
) -> None:
    session = FakeSession(
        [Arg("images", [1, 3, 640, 640])],
        [Arg("boxes", [1, "k", 4]), Arg("scores", [1, "k"]), Arg("labels", [1, "k"])],
        {
            "boxes": np.array([[[1, 2, 30, 40]]], np.float32),
            "scores": np.array([[0.9]], np.float32),
            "labels": np.array([[5]], np.int64),
        },
    )
    weights, card = _onnx(tmp_path, monkeypatch, session, ["a", "b"])
    result = check_model(card, weights, worker_target_id=TARGET, images=images)
    assert not result.passed and "label 5" in (result.details or "")


def test_onnx_unsupported_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, images: NDArray[np.float32]
) -> None:
    session = FakeSession([Arg("images", [1, 3, 640, 640])], [Arg("logits", [1, 10])], {})
    weights, card = _onnx(tmp_path, monkeypatch, session, ["a"])
    result = check_model(card, weights, worker_target_id=TARGET, images=images)
    assert not result.passed and "layout" in (result.details or "")
