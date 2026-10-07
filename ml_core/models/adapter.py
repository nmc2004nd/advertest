"""Model adapter: giao diện chung cho runner CLI và worker (requirements.md Phase R1, mục Model).

- `ModelAdapter` khai báo năng lực (`Capabilities`), cho predict và estimator ART.
- `UltralyticsAdapter` bọc `UltralyticsDetector` qua `build_estimator`, nạp model lười: chỉ nạp
  khi gọi `predict` hoặc `estimator` lần đầu (runner không nạp model khi mọi run đã có cache).
- `ModelProvider` cache adapter theo `(weights_sha256, InferenceParams, device)`, nên mỗi khóa
  nạp model một lần.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from art.estimators import BaseEstimator
from art.estimators.object_detection import PyTorchYolo
from numpy.typing import NDArray
from ultralytics.nn.tasks import DetectionModel

from advertest_contracts.models import InferenceParams, ModelCard
from advertest_contracts.perturbation import ImageBatch
from ml_core.models.estimator import build_estimator
from ml_core.models.register import weights_key
from ml_core.models.wrapper import load_detection_model
from ml_core.store import ArtifactStore

Prediction = dict[str, NDArray[Any]]  # {"boxes": (K, 4), "labels": (K,), "scores": (K,)}

ModelLoader = Callable[[ModelCard], DetectionModel]


class NoGradients(RuntimeError):
    """Model không hỗ trợ gradient (`ModelCard.supports_gradients = false`)."""


@dataclass(frozen=True)
class Capabilities:
    gradients: bool


class ModelAdapter(Protocol):
    card: ModelCard
    capabilities: Capabilities

    def class_names(self) -> list[str]: ...

    def predict(self, images: ImageBatch, batch_size: int | None = None) -> list[Prediction]: ...

    def estimator(self) -> BaseEstimator: ...


class UltralyticsAdapter:
    """Model Ultralytics qua estimator `PyTorchYolo` (wrapper `UltralyticsDetector`)."""

    def __init__(
        self, card: ModelCard, params: InferenceParams, device: str, load: ModelLoader
    ) -> None:
        self.card = card
        self.params = params
        self.device = device
        self.capabilities = Capabilities(gradients=card.supports_gradients)
        self._load = load
        self._estimator: PyTorchYolo | None = None

    def _yolo(self) -> PyTorchYolo:
        if self._estimator is None:
            self._estimator = build_estimator(self._load(self.card), self.params, self.device)
        return self._estimator

    def class_names(self) -> list[str]:
        # Bằng tên class của model (kiểm tra khi đăng ký); không cần nạp model.
        return list(self.card.class_names)

    def predict(self, images: ImageBatch, batch_size: int | None = None) -> list[Prediction]:
        """Prediction sau NMS, như `estimator.predict` của `predict_slice`."""
        if batch_size is None:
            batch_size = len(images)
        return list(self._yolo().predict(images, batch_size=batch_size))

    def estimator(self) -> BaseEstimator:
        if not self.capabilities.gradients:
            raise NoGradients(f"Model {self.card.name} không hỗ trợ gradient")
        return self._yolo()


def store_loader(store: ArtifactStore) -> ModelLoader:
    """Nạp weights đã đăng ký (`models/<sha>/weights.pt`) từ store."""

    def load(card: ModelCard) -> DetectionModel:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "weights.pt"
            path.write_bytes(store.get(weights_key(card.weights_sha256)))
            return load_detection_model(path)

    return load


class ModelProvider:
    """Adapter theo model card, cache theo `(weights_sha256, InferenceParams, device)`."""

    def __init__(self, store: ArtifactStore, *, load_model: ModelLoader | None = None) -> None:
        self._load = load_model or store_loader(store)
        self._adapters: dict[tuple[str, InferenceParams, str], ModelAdapter] = {}

    def get(self, card: ModelCard, params: InferenceParams, device: str) -> ModelAdapter:
        key = (card.weights_sha256, params, device)
        adapter = self._adapters.get(key)
        if adapter is None:
            if card.framework != "ultralytics":
                raise ValueError(f"Chưa hỗ trợ model framework {card.framework}")
            adapter = UltralyticsAdapter(card, params, device, self._load)
            self._adapters[key] = adapter
        return adapter
