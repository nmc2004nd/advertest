"""Chính sách lỗi của run (requirements.md Phase R1, `### Chính sách lỗi`).

Một bảng ánh xạ exception sang kết quả, dùng chung cho `_run_one` của CLI và worker. Luật xét theo
thứ tự, luật đầu tiên khớp kiểu exception được dùng. Bảng lõi (`CORE_POLICY`) có các luật chung;
worker thêm luật cho exception riêng của nó (`PatchInterrupted`, `LeaseLost`) bằng `with_rules`.

| Exception | Hành động |
|---|---|
| `IncompatibleAttack` | run `skipped` (`incompatible`) |
| Hết VRAM | `RETRY_SMALLER`: nơi chạy batch giảm batch một bậc rồi chạy lại; nơi không giảm được
  (batch 1, hoặc ngoài vòng batch) xử lý như exception khác |
| Exception khác | run `failed` (`error`), các run khác chạy tiếp |
| (worker) `PatchInterrupted` | `cancelled` hoặc `stopped_limit` theo directive; dừng experiment |
| (worker) `LeaseLost` | `PROPAGATE`: dừng experiment, không gửi gì thêm |
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

import torch

from advertest_contracts.enums import RunStatus, SkipReason, StopReason
from advertest_contracts.models import StatusReason
from attacks.builders import IncompatibleAttack

CANCELLED_REASON = StatusReason(code="cancelled", message="Experiment bị hủy")
TIME_LIMIT_REASON = StatusReason(
    code=StopReason.TIME, message="Chạm giới hạn thời gian của experiment"
)


class ErrorAction(StrEnum):
    SKIP = "skip"  # gửi/ghi kết quả `status`, chạy run kế tiếp
    FAIL = "fail"
    RETRY_SMALLER = "retry_smaller"
    STOP = "stop"  # gửi kết quả `status` rồi dừng experiment
    PROPAGATE = "propagate"  # ném tiếp, không gửi gì


@dataclass(frozen=True)
class ErrorDecision:
    action: ErrorAction
    status: RunStatus | None = None
    reason: StatusReason | None = None
    device_seconds: float = 0.0  # thời gian thiết bị đã dùng trước lỗi (train patch dở)

    @property
    def stops_experiment(self) -> bool:
        return self.action in (ErrorAction.STOP, ErrorAction.PROPAGATE)


Rule = tuple[type[BaseException], Callable[[BaseException], ErrorDecision]]


def failed(exc: BaseException) -> ErrorDecision:
    return ErrorDecision(
        ErrorAction.FAIL,
        RunStatus.FAILED,
        StatusReason(code="error", message=f"{type(exc).__name__}: {exc}"),
    )


def incompatible(message: str) -> ErrorDecision:
    return ErrorDecision(
        ErrorAction.SKIP,
        RunStatus.SKIPPED,
        StatusReason(code=SkipReason.INCOMPATIBLE, message=message),
    )


def propagate(_exc: BaseException) -> ErrorDecision:
    return ErrorDecision(ErrorAction.PROPAGATE)


def _retry_smaller(exc: BaseException) -> ErrorDecision:
    # status, reason dùng khi không giảm được batch nữa: như exception khác.
    return ErrorDecision(ErrorAction.RETRY_SMALLER, failed(exc).status, failed(exc).reason)


class ErrorPolicy:
    def __init__(self, rules: Sequence[Rule]) -> None:
        self.rules = tuple(rules)

    def with_rules(self, *rules: Rule) -> ErrorPolicy:
        """Bảng mới: `rules` xét trước các luật hiện có."""
        return ErrorPolicy((*rules, *self.rules))

    def decide(self, exc: BaseException) -> ErrorDecision:
        for kind, decide in self.rules:
            if isinstance(exc, kind):
                return decide(exc)
        return failed(exc)


CORE_POLICY = ErrorPolicy(
    [
        (IncompatibleAttack, lambda exc: incompatible(str(exc))),
        (torch.cuda.OutOfMemoryError, _retry_smaller),
        (Exception, failed),
    ]
)
