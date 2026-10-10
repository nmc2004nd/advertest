"""`GET /experiments/{id}/insight` (requirements.md Phase R2, Behaviour Insight; plan task 5).

Insight tính từ run có metric (chọn run ở `rules.grid_runs`: `completed`, `stopped_limit`, trúng
cache, level dừng sớm theo run kích hoạt) và kết quả tìm ngưỡng cuối cùng `found`. `partial` khi có
run `stopped_limit` hoặc experiment chưa kết thúc.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from advertest_contracts.enums import ExperimentStatus, RunStatus, SearchStatus
from advertest_contracts.models import (
    ROBUSTNESS_BANDS,
    AttackSpecMetadata,
    ExperimentConfig,
    ExperimentInsight,
    RobustnessRow,
    RunMetrics,
    SearchResult,
    StatusReason,
    Weakness,
)
from backend.app.db import models as m
from backend.app.insight import rules
from backend.app.insight.phrases import conclude
from backend.app.services.errors import NotFound
from backend.app.services.experiment_config import spec_of
from backend.app.services.experiment_views import mode_of

UNFINISHED = (ExperimentStatus.DRAFT, ExperimentStatus.QUEUED, ExperimentStatus.RUNNING)


def _metadata(row: m.AttackSpecRow) -> AttackSpecMetadata | None:
    """Metadata hiển thị của spec (cột `attack_specs.metadata`, Group 4); spec seed chưa có."""
    return AttackSpecMetadata.model_validate(row.spec_metadata) if row.spec_metadata else None


def _attack(row: m.AttackSpecRow) -> rules.InsightAttack:
    spec = spec_of(row)
    return rules.InsightAttack(
        attack_spec_id=row.id,
        name=row.name,
        max_level=spec.primary_param.max,
        metadata=_metadata(row),
    )


def _insight_run(run: m.Run) -> rules.InsightRun:
    return rules.InsightRun(
        run_id=run.id,
        attack_spec_id=run.attack_spec_id,
        scope=run.scope,
        level=run.level,
        status=RunStatus(run.status),
        status_reason=(
            StatusReason.model_validate(run.status_reason) if run.status_reason else None
        ),
        metrics=RunMetrics.model_validate(run.metrics) if run.metrics else None,
    )


def insight(session: Session, experiment_id: UUID) -> ExperimentInsight:
    experiment = session.get(m.Experiment, experiment_id)
    if experiment is None:
        raise NotFound("Không có experiment này")
    protocol = session.get(m.Protocol, experiment.protocol_id)
    assert protocol is not None  # khóa ngoại không null
    config = ExperimentConfig.model_validate(experiment.config)
    runs = [
        _insight_run(run)
        for run in session.scalars(select(m.Run).where(m.Run.experiment_id == experiment.id))
    ]
    partial = experiment.status in UNFINISHED or any(
        run.status == RunStatus.STOPPED_LIMIT for run in runs
    )
    grid_runs = rules.grid_runs(runs)
    found = {
        result.attack_spec_id: result.breaking_point
        for result in (
            SearchResult.model_validate(row.result)
            for row in session.scalars(
                select(m.SearchResultRow).where(m.SearchResultRow.experiment_id == experiment.id)
            )
        )
        if result.status == SearchStatus.FOUND and result.breaking_point is not None
    }

    weaknesses: list[Weakness] = []
    matrix: list[RobustnessRow] = []
    for attack in config.attacks:  # theo thứ tự cấu hình
        row = session.get(m.AttackSpecRow, attack.attack_spec_id)
        assert row is not None  # experiment chỉ tạo được với spec trong catalog
        target = _attack(row)
        if attack.grid is not None:
            items = grid_runs.get(row.id, [])
            weakness = rules.grid_weakness(target, items)
            if weakness is not None:
                weaknesses.append(weakness)
            matrix_row = rules.matrix_row(target, items)
            if matrix_row is not None:
                matrix.append(matrix_row)
        elif row.id in found:
            weaknesses.append(rules.search_weakness(target, found[row.id]))

    ranked = rules.rank(weaknesses)
    return ExperimentInsight(
        experiment_id=experiment.id,
        mode=mode_of(protocol.status),
        weaknesses=ranked,
        matrix=matrix,
        bands=list(ROBUSTNESS_BANDS),
        conclusion=conclude(ranked, has_data=rules.has_data(runs)),
        partial=partial,
    )
