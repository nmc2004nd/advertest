"""Ước lượng thời gian của experiment từ cost profile (requirements.md Phase 3, Calibration và
ước lượng): `thời_gian ≈ Σ_run (số ảnh * sec_per_image) * 1.2`.

Dùng profile mới nhất (theo `measured_at`) của (compute target, model, attack). Thiếu profile của
bất kỳ run nào → `None` ("chưa có ước lượng").
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db import models as m
from backend.app.services.experiments import runs_of

SAFETY_FACTOR = 1.2


def latest_profiles(
    session: Session, compute_target_id: UUID, model_version_id: UUID
) -> dict[UUID, m.CostProfile]:
    """attack_spec_id → profile mới nhất."""
    rows = session.scalars(
        select(m.CostProfile)
        .where(
            m.CostProfile.compute_target_id == compute_target_id,
            m.CostProfile.model_version_id == model_version_id,
        )
        .order_by(m.CostProfile.measured_at)
    )
    return {row.attack_spec_id: row for row in rows}


def estimate_seconds(
    runs: list[tuple[UUID, int]], profiles: dict[UUID, m.CostProfile]
) -> float | None:
    """`runs`: (attack_spec_id, số ảnh) của từng run."""
    total = 0.0
    for attack_spec_id, images in runs:
        profile = profiles.get(attack_spec_id)
        if profile is None:
            return None
        total += images * profile.sec_per_image
    return total * SAFETY_FACTOR


def estimate_experiment(session: Session, experiment: m.Experiment) -> float | None:
    profiles = latest_profiles(session, experiment.compute_target_id, experiment.model_version_id)
    runs = [(run.attack_spec_id, run.images_total) for run in runs_of(session, experiment.id)]
    return estimate_seconds(runs, profiles)
