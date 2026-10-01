"""Đọc experiment và run cho người dùng (requirements.md Phase 5, API experiment): danh sách có
lọc và phân trang, chi tiết, run, manifest, cấu hình nhân bản.

Mọi người dùng `active` có `experiment.read` xem được experiment của người khác; luật theo chủ sở
hữu chỉ áp cho hủy (`experiments.cancel`).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from advertest_contracts.enums import ExperimentStatus, RunPhase, RunStatus
from advertest_contracts.models import (
    AttackRankingEntry,
    AttackSpec,
    CloneWarning,
    ComputeTargetRef,
    ExperimentClone,
    ExperimentConfig,
    ExperimentCreate,
    ExperimentDetail,
    ExperimentPage,
    ExperimentSummary,
    IterationProgress,
    Manifest,
    MapPair,
    ModelRef,
    Progress,
    ProtocolRef,
    RunAttackSpec,
    RunCounts,
    RunMetrics,
    RunView,
    SliceRef,
    StatusReason,
    UserRef,
)
from backend.app import storage
from backend.app.api import pagination
from backend.app.db import models as m
from backend.app.services.errors import NotFound
from backend.app.services.estimate import queue_position
from backend.app.services.experiment_config import spec_of
from backend.app.services.experiments import runs_of
from backend.app.services.runs import failure_case_ids
from ml_core.metrics.ranking import RankingAttack, RankingRun, rank_attacks

Owner = Literal["me", "all"]
ARTIFACTS_URI = f"s3://{storage.BUCKET_ARTIFACTS}/"


@dataclass(frozen=True)
class _Refs:
    owner: m.User
    model: m.Model
    slice: m.Slice
    target: m.ComputeTarget


def _with_refs(
    query: Select[m.Experiment],
) -> Select[m.Experiment, m.User, m.Model, m.Slice, m.ComputeTarget]:
    return (
        query.add_columns(m.User, m.Model, m.Slice, m.ComputeTarget)
        .join(m.User, m.User.id == m.Experiment.created_by)
        .join(m.ModelVersion, m.ModelVersion.id == m.Experiment.model_version_id)
        .join(m.Model, m.Model.id == m.ModelVersion.model_id)
        .join(m.Slice, m.Slice.id == m.Experiment.slice_id)
        .join(m.ComputeTarget, m.ComputeTarget.id == m.Experiment.compute_target_id)
    )


def _run_stats(
    session: Session, experiment_ids: list[UUID]
) -> dict[UUID, tuple[dict[str, int], int, int]]:
    """experiment_id → (số run theo trạng thái, tổng ảnh đã xử lý, tổng ảnh)."""
    counts: dict[UUID, dict[str, int]] = defaultdict(lambda: dict.fromkeys(RunStatus, 0))
    done: dict[UUID, int] = defaultdict(int)
    total: dict[UUID, int] = defaultdict(int)
    if experiment_ids:
        rows = session.execute(
            select(
                m.Run.experiment_id,
                m.Run.status,
                func.count(),
                func.sum(m.Run.images_done),
                func.sum(m.Run.images_total),
            )
            .where(m.Run.experiment_id.in_(experiment_ids))
            .group_by(m.Run.experiment_id, m.Run.status)
        )
        for experiment_id, status, count, images_done, images_total in rows:
            counts[experiment_id][status] = count
            done[experiment_id] += images_done or 0
            total[experiment_id] += images_total or 0
    return {
        eid: ({str(k): v for k, v in counts[eid].items()}, done[eid], total[eid])
        for eid in experiment_ids
    }


def _summary(
    experiment: m.Experiment, refs: _Refs, stats: tuple[dict[str, int], int, int]
) -> ExperimentSummary:
    counts, images_done, images_total = stats
    return ExperimentSummary(
        id=experiment.id,
        name=experiment.name,
        owner=UserRef(id=refs.owner.id, full_name=refs.owner.full_name),
        status=experiment.status,
        model=ModelRef(id=experiment.model_version_id, name=refs.model.name),
        slice=SliceRef(id=refs.slice.id, name=refs.slice.name, size=len(refs.slice.image_ids)),
        compute_target=ComputeTargetRef(
            id=refs.target.id, name=refs.target.name, kind=refs.target.kind
        ),
        run_counts=RunCounts.model_validate(counts),
        progress=Progress(images_done=images_done, images_total=images_total),
        created_at=experiment.created_at,
        finished_at=experiment.finished_at,
    )


def list_experiments(
    session: Session,
    *,
    viewer_id: UUID,
    owner: Owner = "all",
    status: ExperimentStatus | None = None,
    model_version_id: UUID | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> ExperimentPage:
    """Mới nhất trước, phân trang keyset theo `(created_at, id)`."""
    query = select(m.Experiment)
    if owner == "me":
        query = query.where(m.Experiment.created_by == viewer_id)
    if status is not None:
        query = query.where(m.Experiment.status == status)
    if model_version_id is not None:
        query = query.where(m.Experiment.model_version_id == model_version_id)
    query = pagination.apply(
        query, m.Experiment.created_at, m.Experiment.id, pagination.decode(cursor), limit
    )
    rows = list(session.execute(_with_refs(query)))
    page, more = rows[:limit], len(rows) > limit
    stats = _run_stats(session, [row[0].id for row in page])
    items = [
        _summary(experiment, _Refs(user, model, slice_row, target), stats[experiment.id])
        for experiment, user, model, slice_row, target in page
    ]
    last = page[-1][0] if page and more else None
    return ExperimentPage(
        items=items,
        next_cursor=pagination.encode(last.created_at, last.id) if last is not None else None,
    )


def _load(session: Session, experiment_id: UUID) -> tuple[m.Experiment, _Refs]:
    row = session.execute(
        _with_refs(select(m.Experiment).where(m.Experiment.id == experiment_id))
    ).one_or_none()
    if row is None:
        raise NotFound("Không có experiment này")
    experiment, user, model, slice_row, target = row
    return experiment, _Refs(user, model, slice_row, target)


def summary(session: Session, experiment_id: UUID) -> ExperimentSummary:
    experiment, refs = _load(session, experiment_id)
    return _summary(experiment, refs, _run_stats(session, [experiment.id])[experiment.id])


def detail(session: Session, experiment_id: UUID) -> ExperimentDetail:
    experiment, refs = _load(session, experiment_id)
    base = _summary(experiment, refs, _run_stats(session, [experiment.id])[experiment.id])
    config = ExperimentConfig.model_validate(experiment.config)
    protocol = session.get(m.Protocol, experiment.protocol_id)
    if protocol is None:
        raise NotFound("Protocol của experiment không còn")
    runs = runs_of(session, experiment.id)
    clean = next((run.metrics["clean"] for run in runs if run.metrics), None)
    return ExperimentDetail(
        **base.model_dump(),
        config=config,
        config_sha256=experiment.config_sha256,
        protocol=ProtocolRef(id=protocol.id, name=protocol.name, status=protocol.status),
        limit=config.limit,
        processing_seconds_used=float(experiment.processing_seconds_used),
        queue_position=(
            queue_position(session, experiment)
            if experiment.status == ExperimentStatus.QUEUED
            else None
        ),
        cloned_from=experiment.cloned_from,
        clean_metrics=MapPair.model_validate(clean) if clean is not None else None,
        attack_ranking=_ranking(session, config, runs),
    )


def _ranking(
    session: Session, config: ExperimentConfig, runs: list[m.Run]
) -> list[AttackRankingEntry]:
    """Phase 6 (plan task 27): cùng hàm với report ở Phase 8 (`ml_core.metrics.ranking`)."""
    specs = _specs(session, {attack.attack_spec_id for attack in config.attacks})
    attacks = []
    for attack in config.attacks:
        spec = specs[attack.attack_spec_id]
        attacks.append(
            RankingAttack(
                attack_spec_id=spec.id,
                name=spec.name,
                kind=spec.kind,
                max_level=spec.primary_param.max,
                runs=[
                    RankingRun(
                        run_id=run.id,
                        level=run.level,
                        status=run.status,
                        status_reason=(
                            StatusReason.model_validate(run.status_reason)
                            if run.status_reason
                            else None
                        ),
                        metrics=RunMetrics.model_validate(run.metrics) if run.metrics else None,
                    )
                    for run in runs
                    if run.attack_spec_id == spec.id
                ],
            )
        )
    return rank_attacks(attacks)


# ---------------------------------------------------------------- run


def _phase(run: m.Run) -> tuple[RunPhase | None, IterationProgress | None]:
    """Phase 6: giai đoạn (chỉ khi `running`) và tiến độ train patch."""
    if run.status != RunStatus.RUNNING or run.phase is None:
        return None, None
    phase = RunPhase(run.phase)
    if phase == RunPhase.TRAINING and run.iterations_done is not None and run.iterations_total:
        return phase, IterationProgress(done=run.iterations_done, total=run.iterations_total)
    if phase == RunPhase.TRAINING:
        return None, None
    return phase, None


def _run_view(session: Session, run: m.Run, spec: AttackSpec) -> RunView:
    """Như `runs.result_of`, nhưng run chưa bắt đầu có `fingerprint = null` (đề xuất 001)."""
    source = run.cached_from_run_id or run.id
    phase, training = _phase(run)
    return RunView(
        run_id=run.id,
        experiment_id=run.experiment_id,
        fingerprint=run.fingerprint,
        attack_spec_id=run.attack_spec_id,
        level=run.level,
        status=run.status,
        status_reason=(
            StatusReason.model_validate(run.status_reason) if run.status_reason else None
        ),
        progress=Progress(images_done=run.images_done, images_total=run.images_total),
        metrics=RunMetrics.model_validate(run.metrics) if run.metrics else None,
        gpu_seconds=run.gpu_seconds,
        cost=None,
        failure_case_ids=failure_case_ids(session, source),
        manifest_uri=run.manifest_uri,
        cached_from_run_id=run.cached_from_run_id,
        attack_spec=RunAttackSpec(
            name=spec.name,
            version=spec.version,
            param_name=spec.primary_param.name,
            param_unit=spec.primary_param.unit,
            param_max=spec.primary_param.max,
        ),
        phase=phase,
        training=training,
    )


def _specs(session: Session, ids: set[UUID]) -> dict[UUID, AttackSpec]:
    rows = session.scalars(select(m.AttackSpecRow).where(m.AttackSpecRow.id.in_(ids)))
    return {row.id: spec_of(row) for row in rows}


def list_runs(session: Session, experiment_id: UUID) -> list[RunView]:
    if session.get(m.Experiment, experiment_id) is None:
        raise NotFound("Không có experiment này")
    runs = runs_of(session, experiment_id)
    specs = _specs(session, {run.attack_spec_id for run in runs})
    return [_run_view(session, run, specs[run.attack_spec_id]) for run in runs]


def get_run_row(session: Session, run_id: UUID) -> m.Run:
    run = session.get(m.Run, run_id)
    if run is None:
        raise NotFound("Không có run này")
    return run


def get_run(session: Session, run_id: UUID) -> RunView:
    run = get_run_row(session, run_id)
    return _run_view(session, run, _specs(session, {run.attack_spec_id})[run.attack_spec_id])


def manifest(session: Session, read: Callable[[str], bytes], run_id: UUID) -> Manifest:
    """`manifest.json` của run trong bucket artifacts (run `cached` dùng manifest của run gốc).
    `read` đọc một khóa trong bucket artifacts; chỉ gọi khi run có manifest."""
    run = get_run_row(session, run_id)
    uri = run.manifest_uri
    if uri is None or not uri.startswith(ARTIFACTS_URI):
        raise NotFound("Run chưa có manifest")
    return Manifest.model_validate_json(read(uri.removeprefix(ARTIFACTS_URI)))


# ---------------------------------------------------------------- nhân bản


def _current_version(session: Session, name: str) -> m.AttackSpecRow | None:
    return session.scalar(
        select(m.AttackSpecRow)
        .where(m.AttackSpecRow.name == name, m.AttackSpecRow.is_active)
        .order_by(m.AttackSpecRow.version.desc())
        .limit(1)
    )


def clone(session: Session, experiment_id: UUID) -> ExperimentClone:
    """Cấu hình của experiment cũ, spec không còn hoạt động được thay bằng version hiện hành
    cùng tên (kèm cảnh báo). Spec không còn version nào hoạt động thì giữ nguyên: tạo sẽ báo
    lỗi tại đúng attack."""
    experiment = session.get(m.Experiment, experiment_id)
    if experiment is None:
        raise NotFound("Không có experiment này")
    config = ExperimentConfig.model_validate(experiment.config)
    attacks = []
    warnings: list[CloneWarning] = []
    for attack in config.attacks:
        row = session.get(m.AttackSpecRow, attack.attack_spec_id)
        current = None if row is None or row.is_active else _current_version(session, row.name)
        if row is not None and current is not None and current.version > row.version:
            attacks.append(
                attack.model_copy(
                    update={"attack_spec_id": current.id, "spec_sha256": current.spec_sha256}
                )
            )
            warnings.append(
                CloneWarning(
                    attack_spec_id=current.id,
                    from_version=row.version,
                    to_version=current.version,
                    message=(
                        f"{row.name} đã cập nhật từ version {row.version} lên {current.version};"
                        " kết quả có thể khác lần chạy trước."
                    ),
                )
            )
        else:
            attacks.append(attack)
    body = ExperimentCreate.model_validate(
        {
            **config.model_copy(update={"attacks": attacks}).model_dump(mode="json"),
            "name": None,
            "cloned_from": str(experiment.id),
        }
    )
    return ExperimentClone(config=body, warnings=warnings)
