"""Model và perturbation của runner (requirements.md Phase R1, `### Registry`, `### Model`).

Dùng chung cho CLI và worker:
- model nạp qua `ModelSource` (mặc định `ml_core.models.adapter.ModelProvider`): predict đi qua
  adapter, attack cần gradient nhận `adapter.estimator()`, model không hỗ trợ gradient cho `None`;
- perturbation dựng qua `PerturbationRegistry` (mặc định `attacks.builders.DEFAULT_REGISTRY`), hoặc
  qua seam `PerturbationFactory`; `linf_eps` và loại ảnh thứ ba lấy từ builder của spec.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from art.estimators.estimator import BaseEstimator

from advertest_contracts.models import AttackSpec, InferenceParams, ModelCard
from advertest_contracts.perturbation import Perturbation
from attacks.builders import BuildContext, PerturbationRegistry
from ml_core.models.adapter import ModelAdapter

# (spec, estimator ART hoặc `None` khi model không hỗ trợ gradient) → perturbation.
PerturbationFactory = Callable[[AttackSpec, Any], Perturbation]


class ModelSource(Protocol):
    def get(self, card: ModelCard, params: InferenceParams, device: str) -> ModelAdapter: ...


def registry_factory(registry: PerturbationRegistry) -> PerturbationFactory:
    def build(spec: AttackSpec, estimator: Any) -> Perturbation:
        return registry.build(spec, BuildContext(estimator=estimator))

    return build


def gradient_estimator(adapter: ModelAdapter) -> BaseEstimator | None:
    """Estimator cho attack; `None` khi model không hỗ trợ gradient."""
    return adapter.estimator() if adapter.capabilities.gradients else None
