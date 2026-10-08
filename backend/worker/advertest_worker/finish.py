"""Hoàn tất một run trong worker: dựng `RunResult` + `RunCompletion` và gửi `complete`
(requirements.md Phase 3, Luồng xử lý của worker; Phase R1, `### Điều phối`).

Mọi trạng thái kết thúc (`completed`, `stopped_limit`, `cancelled`, `skipped`, `failed`) đi qua
`RunFinisher`; trạng thái do chính sách lỗi quyết định đi qua `ended`. Sau khi gửi, sổ trạng thái
(dừng sớm) và kết quả trong phiên (tìm ngưỡng) được cập nhật.
"""

from __future__ import annotations

import logging
from typing import Protocol
from uuid import UUID

from advertest_contracts.enums import RunStatus, SkipReason
from advertest_contracts.models import (
    AttackSpec,
    BundleRun,
    FailureCaseRecord,
    FingerprintInputs,
    Progress,
    RunCompletion,
    RunMetrics,
    RunResult,
    StatusReason,
)
from advertest_worker.search import PointOutcome
from advertest_worker.state import JobState
from ml_core.metrics.bootstrap import dump_run_predictions, run_predictions_key
from ml_core.runner.env import describe_device
from ml_core.runner.errors import CANCELLED_REASON, TIME_LIMIT_REASON, ErrorDecision
from ml_core.runner.executor import RunExecutor
from ml_core.runner.paths import artifact_uri
from ml_core.store import PresignedStore

logger = logging.getLogger(__name__)


class CompletionClient(Protocol):
    def complete(self, run_id: UUID, body: RunCompletion) -> None: ...


class RunFinisher:
    """Dựng `RunResult` + `RunCompletion` và gửi `complete` cho một run."""

    def __init__(
        self,
        client: CompletionClient,
        device: str,
        job: JobState,
        run: BundleRun,
        spec: AttackSpec,
        fp: str,
        inputs: FingerprintInputs,
        store: PresignedStore,
        prefix: str,
        *,
        images_total: int,
    ) -> None:
        self.client = client
        self.device = device
        self.job = job
        self.run = run
        self.run_id = run.run_id
        self.spec = spec
        self.level = run.level
        self.images_total = images_total
        self.fp = fp
        self.inputs = inputs
        self.store = store
        self.prefix = prefix
        # Thời gian train patch của run (Phase 6): API ghi đè `gpu_seconds` của run bằng giá trị
        # gửi khi hoàn tất, nên phải cộng vào đây (review Group 3 #1).
        self.extra_seconds = 0.0

    def _manifest(self) -> str:
        assert self.job.manifests is not None
        return artifact_uri(
            self.job.manifests.write(self.store, self.prefix, self.run_id, self.inputs)
        )

    def _send(
        self,
        status: RunStatus,
        reason: StatusReason | None,
        executor: RunExecutor | None,
        metrics: RunMetrics | None = None,
        cases: list[FailureCaseRecord] | None = None,
        predictions_key: str | None = None,
    ) -> None:
        cases = cases or []
        result = RunResult(
            run_id=self.run_id,
            experiment_id=self.job.bundle.experiment_id,
            fingerprint=self.fp,
            attack_spec_id=self.spec.id,
            level=self.level,
            status=status,
            status_reason=reason,
            progress=Progress(
                images_done=executor.images_done if executor else 0,
                images_total=self.images_total,
            ),
            metrics=metrics,
            gpu_seconds=(executor.processing_seconds if executor else 0.0) + self.extra_seconds,
            cost=None,
            failure_case_ids=[case.id for case in cases],
            manifest_uri=self._manifest(),
            scope=self.run.scope,
            search_order=self.run.search_order,
            predictions_key=predictions_key,
        )
        self.client.complete(
            self.run_id,
            RunCompletion(lease_id=self.job.lease.lease_id, run_result=result, failure_cases=cases),
        )
        self.job.ledger.record(self.run_id, status, metrics)
        message = reason.message if reason is not None else None
        self.job.outcomes[self.run_id] = PointOutcome(status, metrics, message)
        logger.info("[%s %g] %s", self.spec.name, self.level, status)

    def _discard_candidates(self, executor: RunExecutor | None) -> None:
        """Run không hoàn tất: ứng viên đã upload không phải kết quả, xóa đi."""
        if executor is None:
            return
        for image_id in executor.offered:
            try:
                executor.candidates.discard(image_id)
            except Exception:
                logger.warning("Không xóa được ứng viên %s", image_id, exc_info=True)

    def _predictions(self, executor: RunExecutor) -> str:
        """Prediction theo ảnh của run (Phase 7, plan task 13a): upload để bootstrap dùng lại."""
        key = run_predictions_key(self.run_id)
        device = describe_device(self.device)
        self.store.put(key, dump_run_predictions(self.run_id, executor.predictions, device))
        return key

    def completed(self, executor: RunExecutor) -> None:
        finalized = executor.finalize(self.run_id)
        key = self._predictions(executor)
        self._send(
            RunStatus.COMPLETED,
            None,
            executor,
            finalized.metrics,
            finalized.failure_cases,
            predictions_key=key,
        )
        self.job.predictions[self.run_id] = dict(executor.predictions)

    def ended(self, decision: ErrorDecision, exc: Exception, executor: RunExecutor | None) -> None:
        """Gửi kết quả theo quyết định của chính sách lỗi (không gồm `PROPAGATE`)."""
        self.extra_seconds += decision.device_seconds
        if decision.status == RunStatus.CANCELLED:
            self.cancelled(executor)
        elif decision.status == RunStatus.STOPPED_LIMIT:
            self.stopped(executor)
        elif decision.status == RunStatus.SKIPPED and decision.reason is not None:
            self.skipped(decision.reason.message)
        else:
            self.failed(exc, executor)

    def stopped(self, executor: RunExecutor | None) -> None:
        reason = TIME_LIMIT_REASON
        if executor is None or executor.images_done == 0:
            self._send(RunStatus.STOPPED_LIMIT, reason, executor)
            return
        finalized = executor.finalize(self.run_id, partial=True)
        self._send(
            RunStatus.STOPPED_LIMIT,
            reason,
            executor,
            finalized.metrics,
            finalized.failure_cases,
            predictions_key=self._predictions(executor),
        )

    def cancelled(self, executor: RunExecutor | None) -> None:
        self._discard_candidates(executor)
        self._send(RunStatus.CANCELLED, CANCELLED_REASON, executor)

    def skipped(self, message: str) -> None:
        self._send(
            RunStatus.SKIPPED, StatusReason(code=SkipReason.INCOMPATIBLE, message=message), None
        )

    def failed(self, exc: Exception, executor: RunExecutor | None) -> None:
        message = f"{type(exc).__name__}: {exc}"
        logger.error("[%s %g] failed: %s", self.spec.name, self.level, message, exc_info=exc)
        self._discard_candidates(executor)
        self._send(RunStatus.FAILED, StatusReason(code="error", message=message), executor)
