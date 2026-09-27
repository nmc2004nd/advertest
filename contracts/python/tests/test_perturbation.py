from typing import Any

import numpy as np

from advertest_contracts.models import AttackSpec, compute_spec_sha256
from advertest_contracts.perturbation import ImageBatch, Perturbation


class _Identity:
    def __init__(self, spec: AttackSpec) -> None:
        self.spec = spec

    def apply(
        self, images: ImageBatch, targets: list[dict[str, Any]], level: float, seed: int
    ) -> ImageBatch:
        return images.copy()


def _spec() -> AttackSpec:
    body: dict[str, Any] = {
        "name": "identity",
        "version": 1,
        "kind": "occlusion",
        "access": "white_box",
        "primary_param": {
            "name": "ratio",
            "type": "continuous",
            "min": 0,
            "max": 1,
            "unit": "ratio",
        },
        "fixed_params": {},
        "cost_model": {"cpu_only": True},
        "requires_gradients": False,
    }
    return AttackSpec.model_validate(
        {
            **body,
            "id": "00000000-0000-5000-8000-000000000003",
            "spec_sha256": compute_spec_sha256(body),
        }
    )


def test_class_with_matching_signature_satisfies_protocol() -> None:
    # mypy kiểm tra phép gán này: _Identity phải khớp đúng chữ ký của Perturbation.
    perturbation: Perturbation = _Identity(_spec())
    images = np.zeros((2, 3, 640, 640), dtype=np.float32)
    out = perturbation.apply(images, [], level=0.5, seed=0)
    assert out.shape == images.shape
    assert out.dtype == np.float32
