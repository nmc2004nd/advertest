"""Nghiệm thu Phase 2, mục Chung (validation.md)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from advertest_contracts.models import AttackSpec, FailureCaseRecord, compute_spec_sha256

REPO = Path(__file__).resolve().parents[3]

# Bảng catalog trong requirements.md Phase 2.
CATALOG: dict[str, dict[str, Any]] = {
    "fgsm": {
        "art_class": "FastGradientMethod",
        "unit": "1/255",
        "range": (0, 32),
        "fixed": {"norm": "inf"},
    },
    "pgd_linf": {
        "art_class": "ProjectedGradientDescent",
        "unit": "1/255",
        "range": (0, 32),
        "fixed": {"norm": "inf", "max_iter": 10, "eps_step_ratio": 0.25, "num_random_init": 0},
    },
    "pgd_l2": {
        "art_class": "ProjectedGradientDescent",
        "unit": "L2",
        "range": (0, 16),
        "fixed": {"norm": 2, "max_iter": 10, "eps_step_ratio": 0.25, "num_random_init": 0},
    },
}


def test_failure_case_record_mocks_validate() -> None:
    mocks = sorted((REPO / "contracts/mocks/failure_case_record").glob("*.json"))
    assert mocks
    for path in mocks:
        FailureCaseRecord.model_validate_json(path.read_text())


@pytest.mark.parametrize("name", sorted(CATALOG))
def test_seed_spec_hash_and_fixed_params(name: str) -> None:
    specs = [
        AttackSpec.model_validate(item)
        for item in json.loads((REPO / "contracts/seeds/attack_specs.json").read_text())
    ]
    spec = next(s for s in specs if s.name == name)
    expected = CATALOG[name]
    assert spec.spec_sha256 == compute_spec_sha256(spec)
    assert spec.kind == "attack" and spec.access == "white_box" and spec.requires_gradients
    assert spec.art_class == expected["art_class"]
    assert spec.primary_param.name == "eps" and spec.primary_param.unit == expected["unit"]
    assert (spec.primary_param.min, spec.primary_param.max) == expected["range"]
    assert spec.fixed_params == expected["fixed"]
