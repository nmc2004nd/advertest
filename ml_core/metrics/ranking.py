"""Xếp hạng attack trong một experiment (requirements.md Phase 6, mục Xếp hạng attack; task 20).

Backend dùng lại hàm này cho `ExperimentDetail.attack_ranking` và report ở Phase 8.

- Điểm của đường cong: (`level / primary_param.max`, `relative_drop`) của mỗi level có metric,
  thêm (0, 0) ở đầu. Level bị `early_stop` lấy `relative_drop` của run kích hoạt
  (`status_reason.trigger_run_id`).
- `auc_drop`: quy tắc hình thang, tính đến `coverage` (x lớn nhất có điểm), không ngoại suy ra 1.
  Ít hơn 2 điểm (level có metric cộng level `early_stop`) → `null`, xếp cuối.
- `max_relative_drop`: lớn nhất trong các level có metric (không tính level `early_stop`).
- `partial`: có run `stopped_limit` hoặc metric `partial`.
- Level có metric nhưng `relative_drop = null` (mAP sạch bằng 0) vẫn đếm vào `levels_evaluated`
  nhưng không thành điểm của đường cong.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from uuid import UUID

from advertest_contracts.enums import AttackKind, RunStatus, SkipReason
from advertest_contracts.models import AttackRankingEntry, RunMetrics, StatusReason


@dataclass(frozen=True)
class RankingRun:
    run_id: UUID
    level: float
    status: RunStatus
    status_reason: StatusReason | None = None
    metrics: RunMetrics | None = None


@dataclass(frozen=True)
class RankingAttack:
    attack_spec_id: UUID
    name: str
    kind: AttackKind
    max_level: float  # primary_param.max của spec
    runs: Sequence[RankingRun]


def _trapezoid(points: list[tuple[float, float]]) -> float:
    return sum((x2 - x1) * (y1 + y2) / 2 for (x1, y1), (x2, y2) in pairwise(points))


def rank_attack(attack: RankingAttack) -> AttackRankingEntry:
    if attack.max_level <= 0:
        raise ValueError(f"{attack.name}: primary_param.max phải dương")
    measured = [run for run in attack.runs if run.metrics is not None]
    drops = {run.run_id: run.metrics.relative_drop for run in measured if run.metrics is not None}
    xs: list[float] = []
    points: list[tuple[float, float]] = []
    for run in measured:
        x = run.level / attack.max_level
        xs.append(x)
        drop = drops[run.run_id]
        if drop is not None:
            points.append((x, drop))
    early = 0
    for run in attack.runs:
        reason = run.status_reason
        if (
            run.status != RunStatus.SKIPPED
            or reason is None
            or reason.code != SkipReason.EARLY_STOP
        ):
            continue
        early += 1
        x = run.level / attack.max_level
        xs.append(x)
        drop = drops.get(reason.trigger_run_id) if reason.trigger_run_id else None
        if drop is not None:
            points.append((x, drop))
    points.sort()
    auc = _trapezoid([(0.0, 0.0), *points]) if len(points) >= 2 else None
    measured_drops = [d for d in drops.values() if d is not None]
    return AttackRankingEntry(
        attack_spec_id=attack.attack_spec_id,
        name=attack.name,
        kind=attack.kind,
        auc_drop=auc,
        max_relative_drop=max(measured_drops) if measured_drops else None,
        levels_evaluated=len(measured),
        levels_early_stopped=early,
        coverage=min(1.0, max(xs)) if xs else None,
        partial=any(
            run.status == RunStatus.STOPPED_LIMIT
            or (run.metrics is not None and run.metrics.partial)
            for run in attack.runs
        ),
    )


def rank_attacks(attacks: Sequence[RankingAttack]) -> list[AttackRankingEntry]:
    """Mỗi attack một dòng, giảm dần theo `auc_drop`, `null` xếp cuối; bằng nhau giữ thứ tự vào."""
    entries = [rank_attack(attack) for attack in attacks]
    return sorted(entries, key=lambda e: (e.auc_drop is None, -(e.auc_drop or 0.0)))
