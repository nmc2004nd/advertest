"""Model adapter: giao diện chung cho runner CLI và worker (requirements.md Phase R1, mục Model).

- `ModelAdapter` khai báo năng lực (`Capabilities`), cho predict và estimator ART.
- `UltralyticsAdapter` bọc `UltralyticsDetector` qua `build_estimator`. Mọi adapter nạp model lười:
  chỉ nạp khi gọi `predict` hoặc `estimator` lần đầu (runner không nạp model khi mọi run đã có
  cache).
- Phase R2 thêm `TorchvisionAdapter` (safetensors, estimator ART) và `OnnxAdapter` (chỉ inference);
  `open_adapter` chọn adapter theo `ModelCard.framework` (requirements.md Phase R2, mục Model qua
  web).
- `ModelProvider` cache adapter theo `(weights_sha256, InferenceParams, device)`, LRU tối đa
  `max_models` khóa (mặc định 2), nên mỗi khóa còn trong cache chỉ nạp model một lần.
"""

from __future__ import annotations

import tempfile
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from art.estimators import BaseEstimator
from art.estimators.object_detection import PyTorchObjectDetector, PyTorchYolo
from numpy.typing import NDArray
from ultralytics.nn.tasks import DetectionModel

from advertest_contracts.models import InferenceParams, ModelCard
from advertest_contracts.perturbation import ImageBatch
from ml_core.models import onnx_model, torchvision_detection
from ml_core.models.estimator import build_estimator
from ml_core.models.register import weights_key
from ml_core.models.wrapper import load_detection_model
from ml_core.store import ArtifactStore

Prediction = dict[str, NDArray[Any]]  # {"boxes": (K, 4), "labels": (K,), "scores": (K,)}

ModelLoader = Callable[[ModelCard], DetectionModel]
# Nội dung weights (đường dẫn file hoặc bytes) của adapter torchvision và onnx, đọc lười.
WeightsSource = Callable[[], Path | bytes]


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


class TorchvisionAdapter:
    """Model torchvision (safetensors) qua estimator `PyTorchObjectDetector`."""

    def __init__(
        self, card: ModelCard, params: InferenceParams, device: str, weights: WeightsSource
    ) -> None:
        torchvision_detection.architecture(card.architecture)  # kiến trúc ngoài danh sách → lỗi
        self.card = card
        self.params = params
        self.device = device
        self.capabilities = Capabilities(gradients=card.supports_gradients)
        self._weights = weights
        self._estimator: PyTorchObjectDetector | None = None

    def detector(self) -> PyTorchObjectDetector:
        """Estimator đã nạp model, không xét `supports_gradients` (bài kiểm tra gradient dùng)."""
        if self._estimator is None:
            state = torchvision_detection.read_state(self._weights())
            model = torchvision_detection.build_model(self.card, state, self.params)
            self._estimator = torchvision_detection.build_estimator(self.card, model, self.device)
        return self._estimator

    def class_names(self) -> list[str]:
        return list(self.card.class_names)

    def predict(self, images: ImageBatch, batch_size: int | None = None) -> list[Prediction]:
        if batch_size is None:
            batch_size = len(images)
        return list(self.detector().predict(images, batch_size=max(batch_size, 1)))

    def estimator(self) -> BaseEstimator:
        if not self.capabilities.gradients:
            raise NoGradients(f"Model {self.card.name} không hỗ trợ gradient")
        return self.detector()


class OnnxAdapter:
    """Model ONNX qua `onnxruntime`; chỉ predict, không có estimator."""

    def __init__(
        self, card: ModelCard, params: InferenceParams, device: str, weights: WeightsSource
    ) -> None:
        self.card = card
        self.params = params
        self.device = device
        self.capabilities = Capabilities(gradients=False)
        self._weights = weights
        self._model: onnx_model.OnnxModel | None = None

    def model(self) -> onnx_model.OnnxModel:
        if self._model is None:
            session = onnx_model.open_session(self._weights(), self.device)
            self._model = onnx_model.inspect(session, self.card.input_size)
        return self._model

    def class_names(self) -> list[str]:
        return list(self.card.class_names)

    def predict(self, images: ImageBatch, batch_size: int | None = None) -> list[Prediction]:
        if batch_size is None:
            batch_size = len(images)
        return self.model().predict(images, self.params, batch_size)

    def estimator(self) -> BaseEstimator:
        raise NoGradients(f"Model ONNX {self.card.name} không hỗ trợ gradient")


def _make_adapter(
    card: ModelCard,
    params: InferenceParams,
    device: str,
    load_model: ModelLoader,
    weights: WeightsSource,
) -> ModelAdapter:
    if card.framework == "ultralytics":
        return UltralyticsAdapter(card, params, device, load_model)
    if card.framework == "torchvision":
        return TorchvisionAdapter(card, params, device, weights)
    if card.framework == "onnx":
        return OnnxAdapter(card, params, device, weights)
    raise ValueError(f"Chưa hỗ trợ model framework {card.framework}")


def open_adapter(
    card: ModelCard, weights: Path, params: InferenceParams, device: str
) -> ModelAdapter:
    """Adapter cho file weights `weights` theo `card.framework`; model nạp lười."""
    return _make_adapter(
        card, params, device, lambda _card: load_detection_model(weights), lambda: weights
    )


def store_loader(store: ArtifactStore) -> ModelLoader:
    """Nạp weights đã đăng ký (`models/<sha>/weights.pt`) từ store."""

    def load(card: ModelCard) -> DetectionModel:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "weights.pt"
            path.write_bytes(store.get(weights_key(card.weights_sha256)))
            return load_detection_model(path)

    return load


class ModelProvider:
    """Adapter theo model card, cache LRU theo `(weights_sha256, InferenceParams, device)`.

    `load_model` chỉ dùng cho model Ultralytics; torchvision và onnx đọc weights từ
    `weights_key(sha)` của `store` (worker cache lưu mọi định dạng ở key này).
    """

    def __init__(
        self,
        store: ArtifactStore,
        *,
        load_model: ModelLoader | None = None,
        max_models: int = 2,
    ) -> None:
        if max_models < 1:
            raise ValueError("max_models phải ≥ 1")
        self._store = store
        self._load = load_model or store_loader(store)
        self._max_models = max_models
        self._adapters: OrderedDict[tuple[str, InferenceParams, str], ModelAdapter] = OrderedDict()

    def get(self, card: ModelCard, params: InferenceParams, device: str) -> ModelAdapter:
        key = (card.weights_sha256, params, device)
        adapter = self._adapters.get(key)
        if adapter is not None:
            self._adapters.move_to_end(key)
            return adapter
        sha = card.weights_sha256
        adapter = _make_adapter(
            card, params, device, self._load, lambda: self._store.get(weights_key(sha))
        )
        self._adapters[key] = adapter
        while len(self._adapters) > self._max_models:
            self._adapters.popitem(last=False)  # ít dùng nhất
        return adapter
