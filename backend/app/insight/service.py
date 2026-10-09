"""`GET /experiments/{id}/insight` (requirements.md Phase R2, Behaviour Insight; plan task 5).

Insight tính từ run đã có metric (`completed`, hoặc `stopped_limit` có metric một phần) và kết quả
tìm ngưỡng cuối cùng `found`. `partial` khi có run `stopped_limit` hoặc experiment chưa kết thúc.
"""

from __future__ import annotations

from collections import defaultdict
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
    Weakness,
)
from backend.app.db import models as m
from backend.app.insight import rules
from backend.app.insight.phrases import conclude
from backend.app.services.errors import NotFound
from backend.app.services.experiment_config import spec_of
from backend.app.services.experiment_views import mode_of

MEASURED = (RunStatus.COMPLETED, RunStatus.STOPPED_LIMIT)
UNFINISHED = (ExperimentStatus.DRAFT, ExperimentStatus.QUEUED, ExperimentStatus.RUNNING)


def _metadata(row: m.AttackSpecRow) -> AttackSpecMetadata | None:
    """Metadata hiển thị của spec. Cột `attack_specs.metadata` có từ Group 4 (migration catalog);
    trước đó mọi spec seed chưa có metadata (Chốt ở Group 0)."""
    return None


def _attack(row: m.AttackSpecRow) -> rules.InsightAttack:
    spec = spec_of(row)
    return rules.InsightAttack(
        attack_spec_id=row.id,
        name=row.name,
        max_level=spec.primary_param.max,
        metadata=_metadata(row),
    )


def insight(session: Session, experiment_id: UUID) -> ExperimentInsight:
    experiment = session.get(m.Experiment, experiment_id)
    if experiment is None:
        raise NotFound("Không có experiment này")
    protocol = session.get(m.Protocol, experiment.protocol_id)
    assert protocol is not None  # khóa ngoại không null
    config = ExperimentConfig.model_validate(experiment.config)
    runs = list(session.scalars(select(m.Run).where(m.Run.experiment_id == experiment.id)))
    has_data = any(run.status in MEASURED and run.metrics for run in runs)
    partial = experiment.status in UNFINISHED or any(
        run.status == RunStatus.STOPPED_LIMIT for run in runs
    )

    grid_runs: dict[UUID, list[rules.GridRun]] = defaultdict(list)
    for run in runs:
        if run.scope == "full" and run.status in MEASURED and run.metrics:
            grid_runs[run.attack_spec_id].append(
                rules.GridRun(level=run.level, metrics=RunMetrics.model_validate(run.metrics))
            )
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
        conclusion=conclude(ranked, has_data=has_data),
        partial=partial,
    )
