"""Thuật toán tự tìm ngưỡng (requirements.md Phase 7, mục Thuật toán; plan task 7, 8).

Máy trạng thái thuần, không gọi model: `ThresholdSearch.progress(observations)` chạy lại thuật toán
từ đầu trên các điểm đã đánh giá (theo thứ tự) và trả điểm cần đánh giá kế tiếp, hoặc kết quả
cuối. Trạng thái cần lưu chỉ là danh sách quan sát, nên worker dựng lại đúng giai đoạn sau gián
đoạn từ `SearchResult.trajectory` (quyết định Group 0) và kết quả giống hệt lần chạy liền mạch.

Các bước:
1. Quét thô mọi level thô trên tập con (tăng dần). Mức sụt thô giảm quá 0.02 so với điểm trước →
   cờ không đơn điệu.
2. `d(lo) ≥ ngưỡng` → xác nhận `lo` trên toàn slice (vẫn gãy → `below_min`); `d(hi) < ngưỡng` →
   xác nhận `hi` (vẫn không gãy → `not_reached`); ngược lại khoảng `[a, b]` là hai level thô liền
   kề đầu tiên với `d(a) < ngưỡng ≤ d(b)`, chia đôi trên tập con tới khi `b - a ≤ tol` (rời rạc:
   tới khi `a`, `b` liền kề).
3. Xác nhận `a`, `b` trên toàn slice. `d(a) ≥ ngưỡng` → dịch xuống (nếu đồng thời `d(b) < ngưỡng`
   thì gắn cờ không đơn điệu); `d(b) < ngưỡng` → dịch lên. Dịch là đánh giá lần lượt các level thô
   kế tiếp trên toàn slice tới khi đổi phía ngưỡng (chạm `lo`/`hi` → `below_min`/`not_reached`),
   rồi chia đôi trên toàn slice (quyết định Group 1: dịch tiếp từng ô thô; dịch xuống khi mâu
   thuẫn). Xác nhận `lo`/`hi` cho kết quả ngược tập con cũng dịch theo cách này.
4. `breaking_point = b`, `bracket = [a, b]`; `non_monotonic` thay `found` khi có cờ.

Level 0 là "không biến đổi" (Phase 6): mức sụt bằng 0 theo định nghĩa, không chạy, ghi vào quỹ
đạo với `synthetic = true`. Một cặp (level, tập ảnh) chỉ đánh giá một lần.
"""

from __future__ import annotations

import math
from collections.abc import Generator, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from typing import cast
from uuid import UUID

from advertest_contracts.enums import EvalScope, SearchStage, SearchStatus
from advertest_contracts.models import (
    PrimaryParam,
    SearchConfig,
    SearchMetricKind,
    SearchResult,
    TrajectoryPoint,
    search_metric_kind,
)
from ml_core.search.bounds import (
    WIDTH_SLACK,
    SearchBounds,
    SearchGrid,
    search_bounds,
    search_grid,
    uses_subset,
)

NON_MONOTONIC_TOLERANCE = 0.02  # mức sụt thô thấp hơn điểm trước quá mức này → không đơn điệu
NEUTRAL_LEVEL = 0.0  # level "không biến đổi" của mọi spec (Phase 6)

_FULL_STAGES = frozenset({SearchStage.CONFIRM, SearchStage.BISECT_FULL})


@dataclass(frozen=True)
class Observation:
    """Kết quả của một điểm đã đánh giá (không gồm điểm synthetic). `drop` là đại lượng so với
    ngưỡng (`ml_core/metrics/threshold.py`); null khi không tính được."""

    level: float
    scope: EvalScope
    drop: float | None


@dataclass(frozen=True)
class TrajectoryEntry:
    order: int
    level: float
    scope: EvalScope
    drop: float | None
    synthetic: bool


@dataclass(frozen=True)
class PointRequest:
    """Điểm cần đánh giá kế tiếp; `order` là `search_order` của run sẽ tạo."""

    order: int
    level: float
    scope: EvalScope
    stage: SearchStage


@dataclass(frozen=True)
class SearchProgress:
    """Trạng thái hiện tại. `status` null và `next_point` khác null khi còn điểm cần đánh giá."""

    stage: SearchStage
    status: SearchStatus | None
    bracket: tuple[float, float]
    breaking_point: float | None
    trajectory: tuple[TrajectoryEntry, ...]
    next_point: PointRequest | None
    non_monotonic: bool
    message: str | None = None

    @property
    def done(self) -> bool:
        return self.status is not None

    @property
    def points_used(self) -> int:
        return sum(1 for entry in self.trajectory if not entry.synthetic)


@dataclass(frozen=True)
class _Ask:
    level: float
    scope: EvalScope
    stage: SearchStage


@dataclass(frozen=True)
class _Final:
    status: SearchStatus
    bracket: tuple[float, float]


@dataclass
class _Context:
    """Trạng thái của một lần chạy lại (không giữ giữa các lần gọi `progress`)."""

    trajectory: list[TrajectoryEntry] = field(default_factory=list)
    cache: dict[tuple[float, EvalScope], float] = field(default_factory=dict)
    stage: SearchStage = SearchStage.COARSE
    non_monotonic: bool = False

    def add(self, level: float, scope: EvalScope, drop: float | None, synthetic: bool) -> None:
        order = len(self.trajectory)
        self.trajectory.append(TrajectoryEntry(order, level, scope, drop, synthetic))


_Steps = Generator[_Ask, float, _Final]


class ThresholdSearch:
    """Một lần tìm ngưỡng của một attack trên một slice."""

    def __init__(self, config: SearchConfig, param: PrimaryParam, slice_size: int) -> None:
        self.config = config
        self.grid: SearchGrid = search_grid(config, param)
        self.bounds: SearchBounds = search_bounds(config, param, slice_size)
        self.uses_subset = uses_subset(config, slice_size)
        self._param_name = param.name

    # ------------------------------------------------------------ chạy lại

    def progress(
        self,
        observations: Sequence[Observation],
        *,
        stop: bool = False,
        failure: str | None = None,
    ) -> SearchProgress:
        """Chạy lại thuật toán trên `observations` (đúng thứ tự đã đánh giá).

        `stop`: dừng do giới hạn thời gian hoặc bị hủy → `stopped_limit` với khoảng hiện có.
        `failure`: lỗi không phục hồi → `failed` với thông điệp này. Cả hai không có tác dụng khi
        thuật toán đã kết thúc trên các quan sát hiện có. Quan sát thừa hoặc không khớp điểm mà
        thuật toán yêu cầu → `ValueError`.
        """
        ctx = _Context()
        steps = self._search(ctx)
        pending = list(observations)
        used = 0
        try:
            ask = next(steps)
            while True:
                ctx.stage = ask.stage
                key = (ask.level, ask.scope)
                if key in ctx.cache:
                    ask = steps.send(ctx.cache[key])
                    continue
                if ask.level == NEUTRAL_LEVEL:
                    ctx.add(ask.level, ask.scope, 0.0, synthetic=True)
                    ctx.cache[key] = 0.0
                    ask = steps.send(0.0)
                    continue
                if used == len(pending):
                    return self._unfinished(ctx, ask, stop=stop, failure=failure)
                obs = pending[used]
                used += 1
                if obs.scope != ask.scope or not math.isclose(
                    obs.level, ask.level, rel_tol=1e-12, abs_tol=1e-12
                ):
                    raise ValueError(
                        f"quan sát thứ {used} ({obs.level}, {obs.scope}) không khớp điểm thuật"
                        f" toán yêu cầu ({ask.level}, {ask.scope})"
                    )
                ctx.add(ask.level, ask.scope, obs.drop, synthetic=False)
                if obs.drop is None or math.isnan(obs.drop):
                    if used != len(pending):
                        raise ValueError("có quan sát sau một điểm không tính được mức sụt")
                    return self._finish_early(
                        ctx, SearchStatus.FAILED, failure or self._no_drop_message(ask)
                    )
                ctx.cache[key] = obs.drop
                ask = steps.send(obs.drop)
        except StopIteration as stop_iteration:
            final: _Final = stop_iteration.value
        if used != len(pending):
            raise ValueError(f"thừa {len(pending) - used} quan sát sau khi thuật toán kết thúc")
        status = final.status
        if status == SearchStatus.FOUND and ctx.non_monotonic:
            status = SearchStatus.NON_MONOTONIC
        found = status in (SearchStatus.FOUND, SearchStatus.NON_MONOTONIC)
        return SearchProgress(
            stage=SearchStage.DONE,
            status=status,
            bracket=final.bracket,
            breaking_point=final.bracket[1] if found else None,
            trajectory=tuple(ctx.trajectory),
            next_point=None,
            non_monotonic=ctx.non_monotonic,
        )

    def _unfinished(
        self, ctx: _Context, ask: _Ask, *, stop: bool, failure: str | None
    ) -> SearchProgress:
        if failure is not None:
            return self._finish_early(ctx, SearchStatus.FAILED, failure)
        if stop:
            return self._finish_early(ctx, SearchStatus.STOPPED_LIMIT, None)
        used = sum(1 for entry in ctx.trajectory if not entry.synthetic)
        if used >= self.bounds.max_points:
            raise RuntimeError(f"thuật toán cần điểm thứ {used + 1}, vượt max_points")
        request = PointRequest(len(ctx.trajectory), ask.level, ask.scope, ask.stage)
        return SearchProgress(
            stage=ask.stage,
            status=None,
            bracket=self._known_bracket(ctx),
            breaking_point=None,
            trajectory=tuple(ctx.trajectory),
            next_point=request,
            non_monotonic=ctx.non_monotonic,
        )

    def _finish_early(
        self, ctx: _Context, status: SearchStatus, message: str | None
    ) -> SearchProgress:
        return SearchProgress(
            stage=SearchStage.DONE,
            status=status,
            bracket=self._known_bracket(ctx),
            breaking_point=None,
            trajectory=tuple(ctx.trajectory),
            next_point=None,
            non_monotonic=ctx.non_monotonic,
            message=message,
        )

    def _known_bracket(self, ctx: _Context) -> tuple[float, float]:
        """Khoảng hẹp nhất suy ra từ các điểm đã có của giai đoạn hiện tại (review Group 0): cận
        trên là level nhỏ nhất đã gãy (chưa có thì `hi`), cận dưới là level lớn nhất chưa gãy nằm
        dưới cận trên (chưa có thì `lo`)."""
        if ctx.stage in _FULL_STAGES or not self.uses_subset:
            scope = EvalScope.FULL
        else:
            scope = EvalScope.SUBSET
        t = self.config.threshold
        points = [e for e in ctx.trajectory if e.scope == scope and e.drop is not None]
        broken = [e.level for e in points if e.drop is not None and e.drop >= t]
        upper = min(broken, default=self.grid.hi)
        intact = [e.level for e in points if e.drop is not None and e.drop < t and e.level < upper]
        return (max(intact, default=self.grid.lo), upper)

    def _no_drop_message(self, ask: _Ask) -> str:
        where = "tập con" if ask.scope == EvalScope.SUBSET else "toàn slice"
        return (
            f"Không tính được {self._quantity()} ở {self._param_name} = {ask.level:g} trên {where}"
            " (mAP@0.5 sạch bằng 0 với ngưỡng tương đối, hoặc không còn object nào để tính ASR)"
        )

    def _quantity(self) -> str:
        kind = search_metric_kind(self.config.threshold_kind, self.config.class_filter)
        return {
            "map50": "mức sụt mAP@0.5",
            "class_ap50": f"mức sụt AP@0.5 của class {self.config.class_filter}",
            "asr": "tỷ lệ tấn công thành công",
            "class_asr": f"tỷ lệ tấn công thành công của class {self.config.class_filter}",
        }[kind]

    # ------------------------------------------------------------ thuật toán

    def _search(self, ctx: _Context) -> _Steps:
        grid, t = self.grid, self.config.threshold
        sub = EvalScope.SUBSET if self.uses_subset else EvalScope.FULL
        full = EvalScope.FULL
        lo, hi = grid.coarse[0], grid.coarse[-1]

        drops: list[float] = []
        for level in grid.coarse:
            drops.append((yield _Ask(level, sub, SearchStage.COARSE)))
        if any(cur < prev - NON_MONOTONIC_TOLERANCE for prev, cur in pairwise(drops)):
            ctx.non_monotonic = True

        if drops[0] >= t:
            if not self.uses_subset:
                return _Final(SearchStatus.BELOW_MIN, (lo, lo))
            if (yield _Ask(lo, full, SearchStage.CONFIRM)) >= t:
                return _Final(SearchStatus.BELOW_MIN, (lo, lo))
            return (yield from self._shift_up(lo))
        if drops[-1] < t:
            if not self.uses_subset:
                return _Final(SearchStatus.NOT_REACHED, (hi, hi))
            if (yield _Ask(hi, full, SearchStage.CONFIRM)) < t:
                return _Final(SearchStatus.NOT_REACHED, (hi, hi))
            return (yield from self._shift_down(hi))

        k = next(i for i in range(len(drops) - 1) if drops[i] < t <= drops[i + 1])
        stage = SearchStage.BISECT_SUBSET if self.uses_subset else SearchStage.BISECT_FULL
        a, b = yield from self._bisect(grid.coarse[k], grid.coarse[k + 1], sub, stage)
        if not self.uses_subset:
            return _Final(SearchStatus.FOUND, (a, b))

        d_a = yield _Ask(a, full, SearchStage.CONFIRM)
        d_b = yield _Ask(b, full, SearchStage.CONFIRM)
        if d_a >= t:
            if d_b < t:
                ctx.non_monotonic = True  # mâu thuẫn: dịch xuống (thận trọng), quyết định Group 1
            return (yield from self._shift_down(a))
        if d_b < t:
            return (yield from self._shift_up(b))
        return _Final(SearchStatus.FOUND, (a, b))

    def _shift_up(self, lower: float) -> _Steps:
        """`lower` chưa gãy trên toàn slice: đánh giá các level thô phía trên tới khi gãy."""
        for level in [c for c in self.grid.coarse if c > lower]:
            if (
                yield _Ask(level, EvalScope.FULL, SearchStage.BISECT_FULL)
            ) >= self.config.threshold:
                a, b = yield from self._bisect(
                    lower, level, EvalScope.FULL, SearchStage.BISECT_FULL
                )
                return _Final(SearchStatus.FOUND, (a, b))
            lower = level
        return _Final(SearchStatus.NOT_REACHED, (self.grid.hi, self.grid.hi))

    def _shift_down(self, upper: float) -> _Steps:
        """`upper` đã gãy trên toàn slice: đánh giá các level thô phía dưới tới khi không gãy."""
        for level in reversed([c for c in self.grid.coarse if c < upper]):
            if (yield _Ask(level, EvalScope.FULL, SearchStage.BISECT_FULL)) < self.config.threshold:
                a, b = yield from self._bisect(
                    level, upper, EvalScope.FULL, SearchStage.BISECT_FULL
                )
                return _Final(SearchStatus.FOUND, (a, b))
            upper = level
        return _Final(SearchStatus.BELOW_MIN, (self.grid.lo, self.grid.lo))

    def _bisect(
        self, a: float, b: float, scope: EvalScope, stage: SearchStage
    ) -> Generator[_Ask, float, tuple[float, float]]:
        """Chia đôi khi `d(a) < ngưỡng ≤ d(b)`; trả khoảng cuối."""
        t = self.config.threshold
        values = self.grid.values
        if values is not None:
            ia, ib = values.index(a), values.index(b)
            while ib - ia > 1:
                im = (ia + ib) // 2
                if (yield _Ask(values[im], scope, stage)) >= t:
                    ib = im
                else:
                    ia = im
            return values[ia], values[ib]
        while b - a > self.grid.tol * (1 + WIDTH_SLACK):
            m = (a + b) / 2
            if (yield _Ask(m, scope, stage)) >= t:
                b = m
            else:
                a = m
        return a, b


# ---------------------------------------------------------------- chuyển đổi với contract


def observations_from_trajectory(trajectory: Sequence[TrajectoryPoint]) -> list[Observation]:
    """Quan sát để chạy lại thuật toán từ `SearchResult.trajectory` (bỏ điểm synthetic)."""
    ordered = sorted(trajectory, key=lambda point: point.order)
    return [Observation(p.level, p.scope, p.drop) for p in ordered if not p.synthetic]


def to_search_result(
    progress: SearchProgress,
    *,
    search: ThresholdSearch,
    experiment_id: UUID,
    attack_spec_id: UUID,
    run_ids: Mapping[int, UUID],
    drop_ci: Mapping[int, tuple[float, float]] | None = None,
    confidence_interval: tuple[float, float] | None = None,
    near_threshold: bool = False,
) -> SearchResult:
    """`SearchResult` (tạm thời hoặc cuối) từ trạng thái hiện tại. `run_ids`: `order` → run của
    mọi điểm không synthetic; `drop_ci`, `confidence_interval`, `near_threshold` do bootstrap
    (`ml_core/metrics/bootstrap.py`) tính khi kết thúc."""
    config = search.config
    ci = drop_ci or {}
    trajectory = [
        TrajectoryPoint(
            order=entry.order,
            level=entry.level,
            scope=entry.scope,
            drop=entry.drop,
            drop_ci=ci.get(entry.order),
            synthetic=entry.synthetic,
            run_id=None if entry.synthetic else run_ids[entry.order],
        )
        for entry in progress.trajectory
    ]
    return SearchResult(
        experiment_id=experiment_id,
        attack_spec_id=attack_spec_id,
        stage=progress.stage,
        status=progress.status,
        threshold_kind=config.threshold_kind,
        threshold=config.threshold,
        class_filter=config.class_filter,
        metric_kind=cast(
            SearchMetricKind, search_metric_kind(config.threshold_kind, config.class_filter)
        ),
        breaking_point=progress.breaking_point,
        bracket=progress.bracket,
        confidence_interval=confidence_interval,
        near_threshold=near_threshold,
        max_points=search.bounds.max_points,
        points_used=progress.points_used,
        message=progress.message,
        trajectory=trajectory,
    )
