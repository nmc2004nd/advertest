"""Dựng `Perturbation` cho mọi loại spec của catalog (plan.md Phase 6, task 10).

Từ Phase R1 (plan.md bước 9) đây là lớp chuyển tiếp gọi `attacks.builders.DEFAULT_REGISTRY`; tên
và chữ ký giữ nguyên tới hết R1 vì test nghiệm thu dùng nó làm mặc định của seam
`perturbation_factory` (requirements.md Phase R1, `## Decisions`).
"""

from __future__ import annotations

from art.estimators.estimator import BaseEstimator

from advertest_contracts.models import AttackSpec
from advertest_contracts.perturbation import Perturbation
from attacks.builders import DEFAULT_REGISTRY, BuildContext


def build_perturbation(spec: AttackSpec, estimator: BaseEstimator | None) -> Perturbation:
    """`Perturbation` cho spec; attack white-box không có estimator thì báo `IncompatibleAttack`
    (như Phase 2)."""
    return DEFAULT_REGISTRY.build(spec, BuildContext(estimator=estimator))
