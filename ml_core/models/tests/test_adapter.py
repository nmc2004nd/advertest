from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from ultralytics.nn.tasks import DetectionModel

from advertest_contracts.models import ModelCard
from ml_core.models.adapter import ModelProvider, NoGradients
from ml_core.models.estimator import build_estimator
from ml_core.models.register import register_model
from ml_core.models.tests.conftest import LOW_PARAMS
from ml_core.models.wrapper import DEFAULT_INFERENCE_PARAMS, load_detection_model
from ml_core.store import LocalStore


@pytest.fixture(scope="module")
def store(tmp_path_factory: pytest.TempPathFactory) -> LocalStore:
    return LocalStore(tmp_path_factory.mktemp("store"))


@pytest.fixture(scope="module")
def registered(store: LocalStore, random_weights: Path, images: NDArray[np.float32]) -> ModelCard:
    return register_model(store, random_weights, "yolov8n-random", images)


def _with_gradients(card: ModelCard, gradients: bool) -> ModelCard:
    check = card.gradient_check.model_copy(update={"passed": gradients})
    return card.model_copy(update={"supports_gradients": gradients, "gradient_check": check})


class _CountingLoader:
    def __init__(self, weights: Path) -> None:
        self.weights = weights
        self.calls = 0

    def __call__(self, card: ModelCard) -> DetectionModel:
        self.calls += 1
        return load_detection_model(self.weights)


def test_cache_returns_same_instance_per_key(store: LocalStore, registered: ModelCard) -> None:
    provider = ModelProvider(store)
    adapter = provider.get(registered, LOW_PARAMS, "cpu")

    assert provider.get(registered, LOW_PARAMS.model_copy(), "cpu") is adapter
    assert provider.get(registered, DEFAULT_INFERENCE_PARAMS, "cpu") is not adapter
    assert provider.get(registered, LOW_PARAMS, "cuda") is not adapter
    other = registered.model_copy(update={"weights_sha256": "0" * 64})
    assert provider.get(other, LOW_PARAMS, "cpu") is not adapter


def test_loads_lazily_and_once_per_key(
    store: LocalStore, registered: ModelCard, random_weights: Path, images: NDArray[np.float32]
) -> None:
    loader = _CountingLoader(random_weights)
    provider = ModelProvider(store, load_model=loader)
    card = _with_gradients(registered, True)

    adapter = provider.get(card, LOW_PARAMS, "cpu")
    assert adapter.class_names() == registered.class_names
    assert adapter.capabilities.gradients
    assert loader.calls == 0  # chưa predict hay estimator thì chưa nạp model

    adapter.predict(images)
    estimator = adapter.estimator()
    assert provider.get(card, LOW_PARAMS, "cpu").estimator() is estimator
    assert loader.calls == 1


def test_predict_matches_estimator(
    store: LocalStore, registered: ModelCard, random_weights: Path, images: NDArray[np.float32]
) -> None:
    adapter = ModelProvider(store).get(registered, LOW_PARAMS, "cpu")
    expected = build_estimator(load_detection_model(random_weights), LOW_PARAMS).predict(
        images, batch_size=1
    )

    preds = adapter.predict(images, batch_size=1)
    assert len(preds) == len(expected)
    assert any(len(p["boxes"]) for p in preds)
    for got, want in zip(preds, expected, strict=True):
        assert set(got) == {"boxes", "labels", "scores"}
        for key in want:
            np.testing.assert_array_equal(got[key], want[key])


def test_no_gradients_raises_but_predicts(
    store: LocalStore, registered: ModelCard, images: NDArray[np.float32]
) -> None:
    card = _with_gradients(registered, False)
    adapter = ModelProvider(store).get(card, LOW_PARAMS, "cpu")

    assert not adapter.capabilities.gradients
    with pytest.raises(NoGradients):
        adapter.estimator()
    assert len(adapter.predict(images)) == len(images)


def test_torchvision_card_needs_allowed_architecture(
    store: LocalStore, registered: ModelCard
) -> None:
    card = registered.model_copy(update={"framework": "torchvision"})  # architecture yolov8n
    with pytest.raises(ValueError, match="không được hỗ trợ"):
        ModelProvider(store).get(card, LOW_PARAMS, "cpu")


def _card_with_sha(card: ModelCard, name: str) -> ModelCard:
    return card.model_copy(update={"weights_sha256": name * 64, "name": name})


def test_lru_evicts_least_recently_used(store: LocalStore, registered: ModelCard) -> None:
    provider = ModelProvider(store, max_models=2)
    a, b, c = (_card_with_sha(registered, n) for n in "abc")

    adapter_a = provider.get(a, LOW_PARAMS, "cpu")
    adapter_b = provider.get(b, LOW_PARAMS, "cpu")
    assert provider.get(a, LOW_PARAMS, "cpu") is adapter_a  # b ít dùng nhất
    provider.get(c, LOW_PARAMS, "cpu")
    assert provider.get(a, LOW_PARAMS, "cpu") is adapter_a
    assert provider.get(b, LOW_PARAMS, "cpu") is not adapter_b


def test_lru_size_is_configurable(store: LocalStore, registered: ModelCard) -> None:
    provider = ModelProvider(store, max_models=1)
    a, b = (_card_with_sha(registered, n) for n in "ab")
    adapter_a = provider.get(a, LOW_PARAMS, "cpu")
    provider.get(b, LOW_PARAMS, "cpu")
    assert provider.get(a, LOW_PARAMS, "cpu") is not adapter_a
    with pytest.raises(ValueError, match="max_models"):
        ModelProvider(store, max_models=0)
