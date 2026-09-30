"""Thứ tự quét lưới và dừng sớm (requirements.md Phase 6, mục Quét lưới; plan task 15).

Hàm thuần: backend dùng `coarse_to_fine` để gán `ordinal` khi tạo experiment; worker dùng
`early_stop` trước mỗi run (tính lại được khi chạy tiếp sau gián đoạn từ metric trong bundle).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypeVar
from uuid import UUID

from advertest_contracts.enums import RunStatus
from advertest_contracts.models import RunMetrics

COLLAPSE_FRACTION = 0.05  # model coi là đã sụp khi mAP@0.5 tấn công ≤ 5% mAP@0.5 sạch

T = TypeVar("T", int, float)


def coarse_to_fine(levels: Sequence[T]) -> list[T]:
    """Level tăng dần, lượt một lấy vị trí chẵn (0, 2, 4, ...), lượt hai lấy vị trí lẻ:
    `[2, 4, 8, 16, 32]` → `[2, 8, 32, 4, 16]`."""
    ordered = sorted(levels)
    return ordered[0::2] + ordered[1::2]


def collapsed(metrics: RunMetrics) -> bool:
    """Model đã sụp ở level này. mAP sạch bằng 0 thì không đánh giá được mức sụt nên không coi
    là sụp (người dùng chốt ở Group 3)."""
    clean = metrics.clean.map50
    return clean > 0 and metrics.attacked.map50 <= COLLAPSE_FRACTION * clean


@dataclass(frozen=True)
class GridRun:
    """Một run của một attack, như worker thấy trước khi chạy run kế tiếp."""

    run_id: UUID
    level: float
    status: RunStatus
    metrics: RunMetrics | None = None


@dataclass(frozen=True)
class EarlyStop:
    trigger_run_id: UUID
    trigger_level: float
    skip_run_ids: list[UUID]


def early_stop(runs: Sequence[GridRun], *, enabled: bool = True) -> EarlyStop | None:
    """Run cần bỏ do dừng sớm trong **một** attack: mọi run `queued` có level lớn hơn level nhỏ
    nhất đã làm model sụp. Chỉ tính run có metric đầy đủ (`completed`, hoặc `skipped` do cache
    có metric); metric một phần (`stopped_limit`) không dùng. `None` khi không có gì để bỏ."""
    if not enabled:
        return None
    triggers = [
        run
        for run in runs
        if run.metrics is not None
        and not run.metrics.partial
        and run.status in (RunStatus.COMPLETED, RunStatus.SKIPPED)
        and collapsed(run.metrics)
    ]
    if not triggers:
        return None
    trigger = min(triggers, key=lambda run: (run.level, str(run.run_id)))
    skip = [
        run.run_id for run in runs if run.status == RunStatus.QUEUED and run.level > trigger.level
    ]
    if not skip:
        return None
    return EarlyStop(trigger.run_id, trigger.level, skip)
