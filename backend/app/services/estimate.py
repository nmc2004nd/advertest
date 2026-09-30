"""Ước lượng thời gian của experiment từ cost profile (requirements.md Phase 3, Calibration và
ước lượng): `thời_gian ≈ Σ_run (số ảnh * sec_per_image) * 1.2`.

Dùng profile mới nhất (theo `measured_at`) của (compute target, model, attack). Thiếu profile của
bất kỳ run nào → `None` ("chưa có ước lượng").
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from advertest_contracts.enums import ExperimentStatus, RunStatus
from advertest_contracts.models import (
    AttackConfig,
    AttackSpec,
    EstimateResponse,
    EstimateRun,
    QueueEstimate,
)
from backend.app.db import models as m
from backend.app.services.experiment_config import CheckedConfig
from backend.app.services.experiments import runs_of
from backend.app.services.patches import is_registered, patch_key_for

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


# ---------------------------------------------------------------- Phase 5: ước lượng cho wizard


def _incompatible(spec_requires_gradients: bool, model: m.ModelVersion) -> bool:
    """Attack cần gradient trên model không hỗ trợ gradient: run sẽ `skipped` (`incompatible`)."""
    return spec_requires_gradients and not model.supports_gradients


def remaining_seconds(session: Session, experiment: m.Experiment) -> float:
    """Ước lượng còn lại của các run `queued` của experiment; bỏ run không ước lượng được (thiếu
    profile) và run sẽ bị bỏ qua (requirements.md Phase 5, `queue.ahead_seconds`)."""
    model = session.get(m.ModelVersion, experiment.model_version_id)
    if model is None:
        return 0.0
    profiles = latest_profiles(session, experiment.compute_target_id, model.id)
    runs = runs_of(session, experiment.id)
    spec_ids = {run.attack_spec_id for run in runs}
    requires: dict[UUID, bool] = {
        row.id: bool(row.spec.get("requires_gradients"))
        for row in session.scalars(select(m.AttackSpecRow).where(m.AttackSpecRow.id.in_(spec_ids)))
    }
    total = 0.0
    for run in runs:
        if run.status != RunStatus.QUEUED or _incompatible(
            bool(requires.get(run.attack_spec_id)), model
        ):
            continue
        profile = profiles.get(run.attack_spec_id)
        if profile is not None:
            total += run.images_total * profile.sec_per_image * SAFETY_FACTOR
    return total


def queued_ahead(
    session: Session, target_id: UUID, experiment: m.Experiment | None = None
) -> list[m.Experiment]:
    """Experiment `queued` của target đứng trước `experiment` theo thứ tự lease (`submitted_at`,
    `id`); `experiment = None` (experiment sắp tạo) thì mọi experiment đang chờ đều đứng trước."""
    query = select(m.Experiment).where(
        m.Experiment.compute_target_id == target_id,
        m.Experiment.status == ExperimentStatus.QUEUED,
    )
    if experiment is not None:
        query = query.where(
            tuple_(m.Experiment.submitted_at, m.Experiment.id)
            < tuple_(experiment.submitted_at, experiment.id)
        )
    return list(session.scalars(query.order_by(m.Experiment.submitted_at, m.Experiment.id)))


def queue_position(session: Session, experiment: m.Experiment) -> int:
    return len(queued_ahead(session, experiment.compute_target_id, experiment)) + 1


def _training_seconds(
    session: Session,
    checked: CheckedConfig,
    attack: AttackConfig,
    spec: AttackSpec,
    level: float,
    profile: m.CostProfile | None,
) -> float | None:
    """Phase 6 (plan task 25): `max_iter * số ảnh slice huấn luyện * sec_per_image_iteration` khi
    patch chưa đăng ký; `None` khi không cần train, patch đã có, hoặc profile thiếu số đo train."""
    if spec.training is None or attack.training_slice_id is None:
        return None
    training = checked.training_slices[attack.training_slice_id]
    assert training.slice_sha256 is not None  # đã kiểm tra ở experiment_config
    key = patch_key_for(
        spec, checked.model.weights_sha256, training.slice_sha256, level, attack.seed
    )
    if is_registered(session, key):
        return None
    if profile is None or profile.sec_per_image_iteration is None:
        return None
    iterations = spec.training.max_iter * len(training.image_ids)
    return iterations * profile.sec_per_image_iteration


def estimate_config(session: Session, checked: CheckedConfig) -> EstimateResponse:
    """`EstimateResponse` cho cấu hình đã kiểm tra (requirements.md Phase 5, Ước lượng)."""
    profiles = latest_profiles(session, checked.target.id, checked.model.id)
    runs: list[EstimateRun] = []
    for attack, spec in zip(checked.body.attacks, checked.specs, strict=True):
        assert attack.grid is not None
        skip = _incompatible(spec.requires_gradients, checked.model)
        profile = profiles.get(spec.id)
        spp = profile.sec_per_image if profile is not None else None
        for level in attack.grid.levels:
            est: float | None
            if skip:
                est = 0.0
            elif spp is None:
                est = None
            else:
                est = checked.images * spp * SAFETY_FACTOR
            runs.append(
                EstimateRun(
                    attack_spec_id=spec.id,
                    level=level,
                    images=checked.images,
                    sec_per_image=spp,
                    est_seconds=est,
                    skip_reason="incompatible" if skip else None,
                    training_seconds=(
                        None
                        if skip or est is None
                        else _training_seconds(session, checked, attack, spec, level, profile)
                    ),
                )
            )
    unknown = [r for r in runs if r.skip_reason is None and r.est_seconds is None]
    # Phase 6: thời gian train patch cộng vào tổng và vào cận dưới của `exceeds_limit`.
    known = sum(r.est_seconds for r in runs if r.est_seconds is not None) + sum(
        r.training_seconds for r in runs if r.training_seconds is not None
    )
    ahead = queued_ahead(session, checked.target.id)
    return EstimateResponse(
        runs=runs,
        total_seconds=None if unknown else known,
        missing_profiles=list(dict.fromkeys(r.attack_spec_id for r in unknown)),
        # Cận dưới khi thiếu profile: phần đã biết vượt giới hạn thì vẫn cảnh báo.
        exceeds_limit=known > float(checked.limit_seconds),
        queue=QueueEstimate(
            position=len(ahead) + 1,
            ahead_seconds=sum(remaining_seconds(session, e) for e in ahead),
        ),
    )
