"""Trạng thái của một experiment đang chạy trong worker (requirements.md Phase R1, `### Điều phối`).

`DirectiveBox` giữ chỉ thị mới nhất từ API, dùng chung giữa luồng heartbeat và luồng chạy.
`JobState` là mọi thứ worker biết về experiment trong phiên lease: bundle, cost profile, giới hạn
còn lại, sổ trạng thái run (dừng sớm), kết quả và prediction của run trong phiên.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from uuid import UUID

from advertest_contracts.models import (
    AttackSpec,
    BundleRun,
    CostProfile,
    Environment,
    WorkerDirective,
    WorkerJobBundle,
    WorkerLease,
)
from advertest_worker.client import LeaseLost
from advertest_worker.early_stop import RunLedger
from advertest_worker.search import PointOutcome
from ml_core.metrics.filters import Prediction
from ml_core.runner.cache_loader import ShaCacheLoader
from ml_core.runner.executor import RunContext
from ml_core.runner.fingerprint import FingerprintService
from ml_core.runner.manifest import ManifestBuilder


@dataclass
class DirectiveBox:
    """Chỉ thị mới nhất từ API (heartbeat hoặc progress), dùng chung giữa hai luồng."""

    directive: WorkerDirective | None = None
    lease_lost: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def update(self, directive: WorkerDirective) -> None:
        with self.lock:
            self.directive = directive

    def current(self) -> WorkerDirective | None:
        with self.lock:
            if self.lease_lost:
                raise LeaseLost(409, "conflict", "Lease đã mất (heartbeat)")
            return self.directive


@dataclass
class JobState:
    lease: WorkerLease
    bundle: WorkerJobBundle
    loader: ShaCacheLoader
    box: DirectiveBox
    environment: Environment
    profiles: dict[UUID, CostProfile]
    specs: dict[UUID, AttackSpec]
    remaining_seconds: float | None
    ledger: RunLedger
    context: RunContext | None = None
    # Phase 7: mọi run đã biết (bundle và run tạo động), kết quả của run trong phiên và prediction
    # theo ảnh của run đã hoàn tất trong phiên (bootstrap).
    runs: dict[UUID, BundleRun] = field(default_factory=dict)
    outcomes: dict[UUID, PointOutcome] = field(default_factory=dict)
    predictions: dict[UUID, dict[str, Prediction]] = field(default_factory=dict)
    fingerprints: FingerprintService | None = None
    manifests: ManifestBuilder | None = None

    def apply(self, directive: WorkerDirective) -> None:
        """Chỉ thị nhận được từ `progress`: lưu lại và cập nhật thời gian còn lại."""
        self.box.update(directive)
        self.remaining_seconds = directive.remaining_seconds

    def stop_requested(self) -> bool:
        """Chỉ thị mới nhất khác `continue` (dừng trước run hoặc điểm tìm ngưỡng kế tiếp)."""
        directive = self.box.current()
        return directive is not None and directive.action != "continue"
