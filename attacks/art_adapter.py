"""Adapter attack ART → `Perturbation` (requirements.md Phase 2, mục Chạy attack).

`attacks/` không phụ thuộc `ml_core/`: estimator ART được truyền vào qua `build_perturbation`.

Mask được áp hai lần:
- truyền vào `generate` để ART che gradient (PGD dùng mask này, gồm cả chuẩn hóa L2);
- áp lại sau `generate`: vùng mask = 0 lấy nguyên ảnh gốc. ART 1.20.1 bỏ qua `mask` trong
  `FastGradientMethod.generate` khi estimator là object detector (gọi `_compute(..., None, ...)`).
  Với FGSM L∞ mỗi điểm ảnh độc lập (`sign` của gradient), nên che sau cho kết quả như che gradient.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
from art.attacks.evasion import FastGradientMethod, ProjectedGradientDescent
from art.estimators.estimator import BaseEstimator, LossGradientsMixin

from advertest_contracts.enums import AttackKind
from advertest_contracts.models import AttackSpec
from advertest_contracts.perturbation import ImageBatch, MaskBatch

_ART_CLASSES: dict[str, Any] = {
    "FastGradientMethod": FastGradientMethod,
    "ProjectedGradientDescent": ProjectedGradientDescent,
}
# Hệ số đổi `level` → `eps` theo `primary_param.unit`.
_UNIT_SCALE = {"1/255": 1.0 / 255.0, "L2": 1.0}
# Bước nhảy PGD mặc định eps/4 (tech-stack.md mục 3.2).
DEFAULT_EPS_STEP_RATIO = 0.25
# Tham số của adapter, không truyền cho ART.
_ADAPTER_PARAMS = frozenset({"eps_step_ratio"})


def level_to_eps(spec: AttackSpec, level: float) -> float:
    """`level` theo đơn vị của spec → `eps` trên ảnh [0, 1]."""
    return level * _UNIT_SCALE[spec.primary_param.unit]


class UnsupportedAttack(ValueError):
    """Spec không dựng được bằng adapter ART (sai `kind`, `art_class` hay đơn vị)."""


class IncompatibleAttack(ValueError):
    """Spec cần gradient nhưng estimator không cung cấp."""


class ArtPerturbation:
    """Attack white-box của ART theo interface `Perturbation`."""

    def __init__(self, spec: AttackSpec, estimator: BaseEstimator) -> None:
        if spec.kind != AttackKind.ATTACK or spec.art_class is None:
            raise UnsupportedAttack(f"{spec.name}: adapter ART chỉ nhận kind = attack")
        if spec.art_class not in _ART_CLASSES:
            raise UnsupportedAttack(
                f"{spec.name}: art_class {spec.art_class!r} chưa được hỗ trợ "
                f"(có: {', '.join(sorted(_ART_CLASSES))})"
            )
        if spec.primary_param.name != "eps" or spec.primary_param.unit not in _UNIT_SCALE:
            raise UnsupportedAttack(
                f"{spec.name}: tham số chính phải là eps với đơn vị trong {sorted(_UNIT_SCALE)}"
            )
        self.spec = spec
        self.estimator = estimator

    def eps(self, level: float) -> float:
        """`level` theo đơn vị của spec → `eps` trên ảnh [0, 1]."""
        return level_to_eps(self.spec, level)

    def apply(
        self,
        images: ImageBatch,
        targets: list[dict[str, Any]],
        level: float,
        seed: int,
        mask: MaskBatch | None = None,
    ) -> ImageBatch:
        """Ảnh sau tấn công; `targets` là nhãn ground truth (untargeted)."""
        self._check_inputs(images, targets, level, mask)
        if level == 0:
            return images.copy()

        attack = self._build_attack(self.eps(level), batch_size=len(images))
        np.random.seed(seed)
        torch.manual_seed(seed)
        adversarial = np.asarray(attack.generate(images, y=targets, mask=mask), dtype=np.float32)

        clip_values = self.estimator.clip_values
        if clip_values is not None:
            adversarial = np.clip(adversarial, clip_values[0], clip_values[1]).astype(np.float32)
        if mask is not None:
            adversarial = np.where(mask == 0, images, adversarial).astype(np.float32)
        return adversarial

    def _check_inputs(
        self,
        images: ImageBatch,
        targets: list[dict[str, Any]],
        level: float,
        mask: MaskBatch | None,
    ) -> None:
        if images.ndim != 4 or images.dtype != np.float32:
            raise ValueError(
                f"images phải là float32 (N, C, H, W), nhận {images.dtype} {images.shape}"
            )
        if len(targets) != len(images):
            raise ValueError(f"Cần {len(images)} targets, nhận {len(targets)}")
        n, _, height, width = images.shape
        if mask is not None and mask.shape != (n, 1, height, width):
            raise ValueError(f"mask phải có shape {(n, 1, height, width)}, nhận {mask.shape}")
        param = self.spec.primary_param
        if not param.min <= level <= param.max:
            raise ValueError(
                f"{self.spec.name}: level {level} ngoài dải "
                f"[{param.min}, {param.max}] ({param.unit})"
            )

    def _build_attack(self, eps: float, batch_size: int) -> Any:
        params: dict[str, Any] = {
            key: value
            for key, value in self.spec.fixed_params.items()
            if key not in _ADAPTER_PARAMS
        }
        if params.get("norm") == "inf":
            params["norm"] = np.inf
        art_class = _ART_CLASSES[self.spec.art_class or ""]
        if art_class is ProjectedGradientDescent:
            ratio = self.spec.fixed_params.get("eps_step_ratio", DEFAULT_EPS_STEP_RATIO)
            if not isinstance(ratio, int | float):
                raise UnsupportedAttack(f"{self.spec.name}: eps_step_ratio phải là số")
            params["eps_step"] = eps * ratio
            params["verbose"] = False
        else:
            params["eps_step"] = eps
        return art_class(
            estimator=self.estimator, eps=eps, targeted=False, batch_size=batch_size, **params
        )


def build_perturbation(spec: AttackSpec, estimator: BaseEstimator) -> ArtPerturbation:
    """Dựng `Perturbation` cho spec; ném `IncompatibleAttack` nếu estimator thiếu gradient."""
    if spec.requires_gradients and not isinstance(estimator, LossGradientsMixin):
        raise IncompatibleAttack(
            f"{spec.name} cần gradient của loss nhưng estimator {type(estimator).__name__} "
            "không cung cấp loss_gradient"
        )
    return ArtPerturbation(spec, estimator)
