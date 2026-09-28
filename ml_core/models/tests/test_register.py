import hashlib
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from typer.testing import CliRunner

from advertest_contracts.ids import content_id
from advertest_contracts.models import ModelCard
from ml_core.cli import app
from ml_core.models import register as register_module
from ml_core.models.register import card_key, register_model, weights_key
from ml_core.models.wrapper import class_names, load_detection_model
from ml_core.store import LocalStore, resolve_id


@pytest.fixture
def store(tmp_path: Path) -> LocalStore:
    return LocalStore(tmp_path / "store")


def test_register_writes_card_weights_and_index(
    store: LocalStore, random_weights: Path, images: NDArray[np.float32]
) -> None:
    card = register_model(store, random_weights, "yolov8n-random", images)
    sha = hashlib.sha256(random_weights.read_bytes()).hexdigest()

    assert card.weights_sha256 == sha
    assert card.id == content_id(sha)
    assert card.name == "yolov8n-random"
    assert card.framework == "ultralytics"
    assert card.architecture == "yolov8n"
    assert card.input_size == 640
    assert card.class_names == class_names(load_detection_model(random_weights))
    assert len(card.class_names) == 80
    assert card.supports_gradients == card.gradient_check.passed
    assert store.get(weights_key(sha)) == random_weights.read_bytes()
    assert ModelCard.model_validate_json(store.get(card_key(sha))) == card
    assert resolve_id(store, "model", card.id) == sha


def test_register_again_returns_same_card(
    store: LocalStore, random_weights: Path, images: NDArray[np.float32]
) -> None:
    first = register_model(store, random_weights, "yolov8n-random", images)
    second = register_model(store, random_weights, "tên-khác", images)
    assert second == first  # cùng id, không chạy lại bài kiểm tra


def test_gradient_check_error_recorded_in_card(
    store: LocalStore,
    random_weights: Path,
    images: NDArray[np.float32],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("hỏng")

    monkeypatch.setattr(register_module, "run_gradient_check", broken)
    card = register_model(store, random_weights, "yolov8n-random", images)
    assert not card.supports_gradients
    assert card.gradient_check.details is not None
    assert "RuntimeError: hỏng" in card.gradient_check.details


def test_cli_register(
    tmp_path: Path,
    random_weights: Path,
    images: NDArray[np.float32],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(register_module, "load_check_images", lambda: images)
    monkeypatch.setattr("ml_core.models.cli.load_check_images", lambda: images)
    store_dir = tmp_path / "store"
    args = ["--store-dir", str(store_dir), "model", "register"]
    args += ["--weights", str(random_weights), "--name", "yolov8n-random"]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    card = ModelCard.model_validate_json(result.stdout)
    assert resolve_id(LocalStore(store_dir), "model", card.id) == card.weights_sha256


def test_load_check_images_missing_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="make fixtures"):
        register_module.load_check_images(tmp_path)
