"""Dựng `Perturbation` cho mọi loại spec của catalog (plan.md Phase 6, task 10).

- `kind = corruption` → `CorruptionPerturbation`; `kind = occlusion` → `OcclusionPerturbation`
  (không cần estimator).
- `kind = attack` → adapter ART (`attacks.art_adapter.build_perturbation`); `RobustDPatch` (patch)
  chưa có adapter cho tới Group 2 nên báo `UnsupportedAttack`.

`attacks.art_adapter.build_perturbation` giữ nguyên kiểu trả về `ArtPerturbation` vì
`ml_core/runner` và worker đang khai kiểu theo nó; Group 3 chuyển các chỗ gọi sang hàm này.
"""

from __future__ import annotations

from art.estimators.estimator import BaseEstimator

from advertest_contracts.enums import AttackKind
from advertest_contracts.models import AttackSpec
from attacks.art_adapter import ArtPerturbation, UnsupportedAttack
from attacks.art_adapter import build_perturbation as build_art_perturbation
from attacks.corruptions.adapter import CorruptionPerturbation
from attacks.occlusion.adapter import OcclusionPerturbation

AnyPerturbation = ArtPerturbation | CorruptionPerturbation | OcclusionPerturbation


def build_perturbation(spec: AttackSpec, estimator: BaseEstimator | None) -> AnyPerturbation:
    """`Perturbation` cho spec; attack white-box cần estimator (`IncompatibleAttack` khi thiếu
    gradient, như Phase 2)."""
    if spec.kind == AttackKind.CORRUPTION:
        return CorruptionPerturbation(spec)
    if spec.kind == AttackKind.OCCLUSION:
        return OcclusionPerturbation(spec)
    if estimator is None:
        raise UnsupportedAttack(f"{spec.name}: attack cần estimator của model")
    return build_art_perturbation(spec, estimator)
