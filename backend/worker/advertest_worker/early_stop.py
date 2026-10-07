"""Dừng sớm trong worker (requirements.md Phase 6, mục Quét lưới; plan task 16).

Worker giữ trạng thái và metric của mọi run trong experiment (`RunLedger`): khởi tạo từ bundle
(`runs[].metrics`, nên chạy tiếp sau gián đoạn tính lại được) và cập nhật khi run trong phiên
kết thúc hoặc trúng cache. Trước mỗi run `queued`, `decision` gọi hàm thuần
`ml_core.runner.grid.early_stop` cho attack của run đó; `skip_early_stop` báo bỏ run lên API.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from advertest_contracts.enums import RunStatus
from advertest_contracts.models import BundleRun, RunMetrics, RunSkipRequest, WorkerJobBundle
from ml_core.runner.grid import EarlyStop, GridRun, early_stop

logger = logging.getLogger(__name__)


class SkipClient(Protocol):
    def skip(self, run_id: UUID, body: RunSkipRequest) -> None: ...


@dataclass
class _Entry:
    attack_spec_id: UUID
    level: float
    status: RunStatus
    metrics: RunMetrics | None


class RunLedger:
    def __init__(self, bundle: WorkerJobBundle) -> None:
        self._runs = {
            run.run_id: _Entry(run.attack_spec_id, run.level, run.status, run.metrics)
            for run in bundle.runs
        }
        self._enabled = {
            attack.attack_spec_id: bool(attack.grid is not None and attack.grid.early_stop)
            for attack in bundle.config.attacks
        }

    def add(self, run: BundleRun) -> None:
        """Run tạo động trong phiên (tìm ngưỡng, Phase 7); không tham gia dừng sớm."""
        self._runs[run.run_id] = _Entry(run.attack_spec_id, run.level, run.status, run.metrics)

    def record(self, run_id: UUID, status: RunStatus, metrics: RunMetrics | None = None) -> None:
        entry = self._runs[run_id]
        entry.status = status
        entry.metrics = metrics

    def status(self, run_id: UUID) -> RunStatus:
        return self._runs[run_id].status

    def decision(self, run_id: UUID) -> EarlyStop | None:
        """Dừng sớm nếu run `run_id` phải bị bỏ; `None` nếu vẫn chạy."""
        entry = self._runs[run_id]
        runs = [
            GridRun(rid, other.level, other.status, other.metrics)
            for rid, other in self._runs.items()
            if other.attack_spec_id == entry.attack_spec_id
        ]
        stop = early_stop(runs, enabled=self._enabled.get(entry.attack_spec_id, False))
        return stop if stop is not None and run_id in stop.skip_run_ids else None


def skip_early_stop(
    client: SkipClient, ledger: RunLedger, lease_id: UUID, run_id: UUID, name: str, level: float
) -> bool:
    """Phase 6 (plan task 16): bỏ run `queued` khi level nhỏ hơn của cùng attack đã làm model
    sụp; báo `skip` lên API và ghi vào sổ. `True` nếu run bị bỏ."""
    if ledger.status(run_id) != RunStatus.QUEUED:
        return False
    stop = ledger.decision(run_id)
    if stop is None:
        return False
    client.skip(
        run_id,
        RunSkipRequest(
            lease_id=lease_id,
            code="early_stop",
            trigger_run_id=stop.trigger_run_id,
            message=f"Bỏ qua: model đã sụp ở level {stop.trigger_level:g}",
        ),
    )
    ledger.record(run_id, RunStatus.SKIPPED)
    logger.info("[%s %g] bỏ qua: dừng sớm (sụp ở %g)", name, level, stop.trigger_level)
    return True
