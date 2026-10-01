"""Patch theo khóa (requirements.md Phase 6, mục Patch attack; plan task 25, 26).

Backend tính khóa patch của run bằng `compute_patch_key` của contract (cùng hàm với worker), từ
spec, weights, slice huấn luyện, `area_ratio = level` và seed. Bảng `patches` giữ `PatchArtifact`
khi đã đăng ký, hoặc checkpoint mới nhất khi đang train dở.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from advertest_contracts.models import (
    AttackSpec,
    ExperimentConfig,
    PatchArtifact,
    compute_patch_key,
)
from backend.app.db import models as m


@dataclass(frozen=True)
class RunPatch:
    key: str
    training_slice: m.Slice


def patch_key_for(
    spec: AttackSpec, weights_sha256: str, training_slice_sha256: str, level: float, seed: int
) -> str:
    return compute_patch_key(
        spec_sha256=spec.spec_sha256,
        weights_sha256=weights_sha256,
        training_slice_sha256=training_slice_sha256,
        area_ratio=level,
        seed=seed,
    )


def run_patch(
    session: Session,
    experiment: m.Experiment,
    run: m.Run,
    spec: AttackSpec,
) -> RunPatch | None:
    """Khóa patch và slice huấn luyện của run patch; `None` với run không cần train."""
    if not spec.requires_training:
        return None
    config = ExperimentConfig.model_validate(experiment.config)
    attack = next(a for a in config.attacks if a.attack_spec_id == run.attack_spec_id)
    if attack.training_slice_id is None:
        raise ValueError(f"Run {run.id}: attack {spec.name} thiếu training_slice_id")
    training = session.get(m.Slice, attack.training_slice_id)
    version = session.get(m.ModelVersion, experiment.model_version_id)
    if training is None or training.slice_sha256 is None or version is None:
        raise ValueError(f"Run {run.id}: không còn slice huấn luyện hoặc model")
    key = patch_key_for(spec, version.weights_sha256, training.slice_sha256, run.level, run.seed)
    return RunPatch(key=key, training_slice=training)


def is_registered(session: Session, key: str) -> bool:
    row = session.get(m.Patch, key)
    return row is not None and row.artifact is not None


def registered(session: Session, key: str) -> PatchArtifact | None:
    row = session.get(m.Patch, key)
    if row is None or row.artifact is None:
        return None
    return PatchArtifact.model_validate(row.artifact)
