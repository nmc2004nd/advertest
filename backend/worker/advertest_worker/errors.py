"""Chính sách lỗi của worker: bảng lõi `ml_core.runner.errors.CORE_POLICY` cộng các luật riêng của
worker (requirements.md Phase R1, `### Chính sách lỗi`).

| Exception | Hành động |
|---|---|
| `LeaseLost` | ném tiếp: dừng experiment, không gửi gì thêm |
| `StopExperiment` | ném tiếp: run đã được gửi kết quả, không chạy các run sau |
| `PatchInterrupted` | `cancelled` hoặc `stopped_limit` theo directive; dừng experiment |
| (lõi) `IncompatibleAttack`, hết VRAM, exception khác | như `CORE_POLICY` |
"""

from __future__ import annotations

from advertest_contracts.enums import RunStatus
from advertest_worker.client import LeaseLost
from advertest_worker.patch import PatchInterrupted
from ml_core.runner.errors import (
    CANCELLED_REASON,
    CORE_POLICY,
    TIME_LIMIT_REASON,
    ErrorAction,
    ErrorDecision,
    propagate,
)


class StopExperiment(Exception):
    """Run kết thúc vì bị hủy hoặc chạm giới hạn: không chạy các run sau."""


def _patch_interrupted(exc: BaseException) -> ErrorDecision:
    assert isinstance(exc, PatchInterrupted)
    if exc.directive.action == "cancel":
        status, reason = RunStatus.CANCELLED, CANCELLED_REASON
    else:
        status, reason = RunStatus.STOPPED_LIMIT, TIME_LIMIT_REASON
    return ErrorDecision(ErrorAction.STOP, status, reason, device_seconds=exc.seconds)


WORKER_POLICY = CORE_POLICY.with_rules(
    (LeaseLost, propagate),
    (StopExperiment, propagate),
    (PatchInterrupted, _patch_interrupted),
)
