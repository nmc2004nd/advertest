"""Vòng lặp tự tìm ngưỡng trong worker (requirements.md Phase 7, mục Worker; plan task 14-17).

Với mỗi attack ở chế độ tìm ngưỡng:

1. Dựng lại trạng thái từ `SearchResult` mới nhất trong bundle (Group 0: chạy lại thuật toán trên
   `trajectory`, không có checkpoint riêng).
2. Lặp: hỏi `ThresholdSearch.progress` điểm kế tiếp → dùng run đã có với đúng `search_order` (run
   tạo ở phiên trước nhưng chưa báo kết quả) hoặc tạo run mới qua API → chạy run → đại lượng so
   với ngưỡng (`threshold_quantity`) → gửi `SearchResult` tạm thời.
3. Run bị hủy hoặc chạm giới hạn → `stopped_limit` với khoảng hiện có, dừng experiment. Run lỗi,
   bị bỏ qua (không dùng được với model) hoặc đại lượng không tính được → `failed` kèm thông điệp.
4. Kết thúc: bootstrap trên prediction của các điểm toàn slice (`ml_core/metrics/bootstrap.py`),
   gửi kết quả cuối.

`SearchHooks` là phần phụ thuộc vào API và model; `JobRunner` cài đặt, test dùng bản giả.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from advertest_contracts.enums import EvalScope, RunStatus, SearchStatus
from advertest_contracts.models import (
    AttackConfig,
    AttackSpec,
    RunMetrics,
    SearchConfig,
    SearchResult,
)
from ml_core.metrics.bootstrap import (
    BootstrapPoint,
    BootstrapResult,
    EvalEvidence,
    attack_evidence,
    bootstrap_search,
    evaluation_evidence,
)
from ml_core.metrics.filters import Prediction
from ml_core.metrics.threshold import threshold_quantity
from ml_core.runner.executor import RunContext
from ml_core.search.algorithm import (
    Observation,
    SearchProgress,
    ThresholdSearch,
    observations_from_trajectory,
    to_search_result,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PointOutcome:
    """Kết quả của run cho một điểm. `stop`: run kết thúc vì bị hủy hoặc chạm giới hạn, experiment
    phải dừng."""

    status: RunStatus
    metrics: RunMetrics | None
    message: str | None = None
    stop: bool = False


@dataclass(frozen=True)
class KnownRun:
    """Run tìm ngưỡng đã có trong bundle (tạo ở phiên trước)."""

    run_id: UUID
    level: float
    scope: EvalScope
    status: RunStatus
    metrics: RunMetrics | None


class SearchHooks(Protocol):
    def should_stop(self) -> bool:
        """Có chỉ thị hủy hoặc chạm giới hạn: không tạo điểm mới."""

    def create_run(
        self, attack_spec_id: UUID, level: float, scope: EvalScope, order: int
    ) -> UUID: ...

    def execute(self, run_id: UUID) -> PointOutcome:
        """Chạy (hoặc chạy tiếp) run `queued`/`running`."""

    def report(self, result: SearchResult) -> None: ...

    def predictions(self, run_id: UUID) -> Mapping[str, Prediction] | None:
        """Prediction theo ảnh (đã lọc class đích) của run; `None` khi không có."""


_USABLE = frozenset({RunStatus.COMPLETED, RunStatus.SKIPPED})
_PENDING = frozenset({RunStatus.QUEUED, RunStatus.RUNNING})


class SearchDriver:
    """Một lần tìm ngưỡng của một attack trong experiment."""

    def __init__(
        self,
        *,
        experiment_id: UUID,
        attack: AttackConfig,
        spec: AttackSpec,
        context: RunContext,
        hooks: SearchHooks,
        known_runs: Mapping[int, KnownRun],
        previous: SearchResult | None,
        clean_evidence: EvalEvidence | None = None,
    ) -> None:
        if attack.search is None:
            raise ValueError("attack không ở chế độ tìm ngưỡng")
        self.experiment_id = experiment_id
        self.attack = attack
        self.config: SearchConfig = attack.search
        self.spec = spec
        self.context = context
        self.hooks = hooks
        self.known_runs = dict(known_runs)
        self.previous = previous
        self.search = ThresholdSearch(self.config, spec.primary_param, len(context.image_ids))
        self._clean_evidence = clean_evidence
        self.run_ids: dict[int, UUID] = {}

    # ------------------------------------------------------------------ chạy

    def run(self) -> bool:
        """Chạy tới khi kết thúc; trả `True` nếu experiment phải dừng (hủy, chạm giới hạn)."""
        observations = self._restore()
        progress = self.search.progress(observations)
        stop_experiment = False
        while not progress.done:
            if self.hooks.should_stop():
                progress = self.search.progress(observations, stop=True)
                stop_experiment = True
                break
            request = progress.next_point
            assert request is not None
            run_id, outcome = self._point(request.order, request.level, request.scope)
            self.run_ids[request.order] = run_id
            if outcome.stop:
                progress = self.search.progress(observations, stop=True)
                stop_experiment = True
                break
            drop, failure = self._drop(outcome, request.level)
            observations.append(Observation(request.level, request.scope, drop))
            progress = self.search.progress(observations, failure=failure)
            if not progress.done:
                self.hooks.report(self._result(progress))
        if self.previous is not None and self.previous.status is not None and not stop_experiment:
            return False  # đã gửi kết quả cuối ở phiên trước
        self.hooks.report(self._final(progress))
        return stop_experiment

    def _restore(self) -> list[Observation]:
        if self.previous is None:
            return []
        for point in self.previous.trajectory:
            if point.run_id is not None:
                self.run_ids[point.order] = point.run_id
        return observations_from_trajectory(self.previous.trajectory)

    def _point(self, order: int, level: float, scope: EvalScope) -> tuple[UUID, PointOutcome]:
        known = self.known_runs.get(order)
        if known is not None:
            if known.level != level or known.scope != scope:
                raise ValueError(
                    f"Run {known.run_id} (search_order {order}) có level/scope khác điểm thuật toán"
                    f" yêu cầu ({level}, {scope})"
                )
            if known.status in _USABLE:
                return known.run_id, PointOutcome(known.status, known.metrics)
            if known.status not in _PENDING:
                message = f"Run {known.run_id} ở level {level:g} đã kết thúc với {known.status}"
                return known.run_id, PointOutcome(known.status, known.metrics, message)
            return known.run_id, self.hooks.execute(known.run_id)
        run_id = self.hooks.create_run(self.spec.id, level, scope, order)
        return run_id, self.hooks.execute(run_id)

    def _drop(self, outcome: PointOutcome, level: float) -> tuple[float | None, str | None]:
        """Đại lượng so với ngưỡng của điểm; `None` kèm thông điệp khi không dùng được."""
        if outcome.status not in _USABLE or outcome.metrics is None:
            detail = f": {outcome.message}" if outcome.message else ""
            return None, (
                f"Run ở {self.spec.primary_param.name} = {level:g} kết thúc với"
                f" {outcome.status}{detail}"
            )
        return threshold_quantity(
            outcome.metrics, self.config.threshold_kind, self.config.class_filter
        ), None

    # ------------------------------------------------------------------ kết quả

    def _result(
        self, progress: SearchProgress, boot: BootstrapResult | None = None
    ) -> SearchResult:
        return to_search_result(
            progress,
            search=self.search,
            experiment_id=self.experiment_id,
            attack_spec_id=self.spec.id,
            run_ids=self.run_ids,
            drop_ci=None if boot is None else boot.drop_ci,
            confidence_interval=None if boot is None else boot.confidence_interval,
            near_threshold=False if boot is None else boot.near_threshold,
        )

    def _final(self, progress: SearchProgress) -> SearchResult:
        if progress.status == SearchStatus.FAILED or self.config.bootstrap_samples == 0:
            return self._result(progress)
        return self._result(progress, self._bootstrap(progress))

    def _bootstrap(self, progress: SearchProgress) -> BootstrapResult | None:
        ctx = self.context
        points: list[BootstrapPoint] = []
        for entry in progress.trajectory:
            if entry.scope != EvalScope.FULL or entry.drop is None:
                continue
            if entry.synthetic:
                points.append(BootstrapPoint(entry.order, entry.level, None, None))
                continue
            attacked = self.hooks.predictions(self.run_ids[entry.order])
            if attacked is None or set(attacked) != set(ctx.image_ids):
                logger.warning(
                    "Không có prediction của điểm %s = %g: bỏ khỏi bootstrap",
                    self.spec.primary_param.name,
                    entry.level,
                )
                continue
            points.append(
                BootstrapPoint(
                    entry.order,
                    entry.level,
                    evaluation_evidence(
                        attacked,
                        ctx.targets,
                        ctx.ignore_boxes,
                        ctx.image_ids,
                        ctx.target_labels,
                        ctx.params.max_det,
                    ),
                    attack_evidence(
                        ctx.clean_predictions,
                        attacked,
                        ctx.targets,
                        ctx.ignore_boxes,
                        ctx.image_ids,
                        ctx.target_labels,
                        ctx.params.operating_conf,
                    ),
                )
            )
        if not points:
            return None
        class_filter = self.config.class_filter
        assert progress.status is not None
        return bootstrap_search(
            clean=self.clean_evidence(),
            points=points,
            threshold_kind=self.config.threshold_kind,
            threshold=self.config.threshold,
            class_label=None if class_filter is None else ctx.class_names.index(class_filter),
            status=progress.status,
            bracket=progress.bracket,
            samples=self.config.bootstrap_samples,
            seed=self.attack.seed,
        )

    def clean_evidence(self) -> EvalEvidence:
        if self._clean_evidence is None:
            ctx = self.context
            self._clean_evidence = evaluation_evidence(
                ctx.clean_predictions,
                ctx.targets,
                ctx.ignore_boxes,
                ctx.image_ids,
                ctx.target_labels,
                ctx.params.max_det,
            )
        return self._clean_evidence
