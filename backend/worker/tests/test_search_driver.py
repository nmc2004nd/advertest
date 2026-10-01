"""Vòng lặp tìm ngưỡng của worker với hook giả (requirements.md Phase 7, mục Worker; plan task
14-17). Không cần API hay model: mức sụt của mỗi level cho trước."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

import numpy as np
import pytest

from advertest_contracts.enums import EvalScope, RunStatus, SearchStage, SearchStatus
from advertest_contracts.models import (
    AttackConfig,
    AttackSpec,
    ClassEvalMetrics,
    EvalMetrics,
    InferenceParams,
    MapPair,
    RunMetrics,
    SearchResult,
)
from advertest_worker.search import KnownRun, PointOutcome, SearchDriver
from ml_core.metrics.filters import Prediction
from ml_core.runner.executor import RunContext

ROOT = Path(__file__).resolve().parents[3]
NS = UUID("0b8f3c52-3c1e-4a63-9a0d-5f1d2e3c4b5a")
EXPERIMENT = uuid5(NS, "experiment")
CLASS_NAMES = ["person", "bicycle", "car"]
N_IMAGES = 40
Drop = Callable[[float], float]


def _spec() -> AttackSpec:
    seeds = json.loads((ROOT / "contracts/seeds/attack_specs.json").read_text())
    return AttackSpec.model_validate(next(s for s in seeds if s["name"] == "pgd_linf"))


def _attack(**search: Any) -> AttackConfig:
    spec = _spec()
    body = {
        "threshold_kind": "relative_drop",
        "threshold": 0.2,
        "lo": 0,
        "hi": 32,
        "tol": 0.5,
        "coarse_n": 4,
        "subset_size": 10,
        "bootstrap_samples": 50,
        **search,
    }
    return AttackConfig.model_validate(
        {
            "attack_spec_id": str(spec.id),
            "spec_sha256": spec.spec_sha256,
            "mode": "search",
            "search": body,
            "seed": 3,
        }
    )


def _context() -> RunContext:
    rng = np.random.default_rng(0)
    ids = [f"{i:06d}" for i in range(N_IMAGES)]
    targets: dict[str, dict[str, Any]] = {}
    clean: dict[str, Prediction] = {}
    ignore: dict[str, Any] = {}
    for image_id in ids:
        xy = rng.uniform(0, 500, size=(3, 2))
        boxes = np.concatenate([xy, xy + 40], axis=1).astype(np.float32)
        labels = np.asarray([0, 2, 2], dtype=np.int64)
        targets[image_id] = {"boxes": boxes, "labels": labels}
        clean[image_id] = {
            "boxes": boxes.copy(),
            "labels": labels.copy(),
            "scores": np.full(3, 0.9, np.float32),
        }
        ignore[image_id] = np.zeros((0, 4), np.float32)
    per_class = {
        "person": ClassEvalMetrics(ap50=1.0, ap50_95=1.0, num_gt=N_IMAGES),
        "car": ClassEvalMetrics(ap50=1.0, ap50_95=1.0, num_gt=2 * N_IMAGES),
    }
    return RunContext(
        image_ids=ids,
        class_names=CLASS_NAMES,
        target_classes=frozenset({"person", "car"}),
        target_labels=[0, 2],
        params=InferenceParams(
            conf=0.25, iou=0.7, max_det=300, operating_conf=0.25, input_size=640
        ),
        clean_predictions=clean,
        targets=targets,
        ignore_boxes=ignore,
        clean_metrics=EvalMetrics(map50=1.0, map50_95=1.0, per_class=per_class),
        failure_cases_per_run=0,
    )


def crossing(x_star: float) -> Drop:
    return lambda x: min(1.0, 0.2 * x / x_star)


def _metrics(drop: float) -> RunMetrics:
    attacked = 0.5 * (1 - drop)
    return RunMetrics(
        clean=MapPair(map50=0.5, map50_95=0.25),
        attacked=MapPair(map50=attacked, map50_95=attacked / 2),
        relative_drop=drop,
        absolute_drop=0.5 - attacked,
        attack_success_rate=drop,
    )


class FakeHooks:
    """API và model giả: run đánh giá ra mức sụt `subset(level)` hoặc `full(level)`."""

    def __init__(
        self,
        context: RunContext,
        subset: Drop,
        full: Drop | None = None,
        *,
        stop_after: int | None = None,
        outcome_override: Mapping[int, PointOutcome] | None = None,
    ) -> None:
        self.context = context
        self.subset, self.full = subset, full or subset
        self.created: list[tuple[UUID, float, EvalScope, int]] = []
        self.executed: list[UUID] = []
        self.reports: list[SearchResult] = []
        self.runs: dict[UUID, tuple[float, EvalScope, int]] = {}
        self.stop_after = stop_after
        self.outcome_override = dict(outcome_override or {})
        self.with_predictions = True

    def should_stop(self) -> bool:
        return self.stop_after is not None and len(self.executed) >= self.stop_after

    def create_run(self, attack_spec_id: UUID, level: float, scope: EvalScope, order: int) -> UUID:
        run_id = uuid5(NS, f"{attack_spec_id}/{order}")
        self.created.append((run_id, level, scope, order))
        self.runs[run_id] = (level, scope, order)
        return run_id

    def execute(self, run_id: UUID) -> PointOutcome:
        self.executed.append(run_id)
        level, scope, order = self.runs[run_id]
        if order in self.outcome_override:
            return self.outcome_override[order]
        drop = (self.subset if scope == EvalScope.SUBSET else self.full)(level)
        return PointOutcome(RunStatus.COMPLETED, _metrics(drop))

    def report(self, result: SearchResult) -> None:
        self.reports.append(SearchResult.model_validate_json(result.model_dump_json()))

    def predictions(self, run_id: UUID) -> Mapping[str, Prediction] | None:
        if not self.with_predictions:
            return None
        level, _, _ = self.runs[run_id]
        rng = np.random.default_rng(int(level * 1000))
        out: dict[str, Prediction] = {}
        for image_id, pred in self.context.clean_predictions.items():
            keep = rng.random(len(pred["labels"])) >= min(0.9, self.full(level))
            out[image_id] = {k: v[keep] for k, v in pred.items()}
        return out


def _driver(
    hooks: FakeHooks,
    attack: AttackConfig | None = None,
    previous: SearchResult | None = None,
    known: Mapping[int, KnownRun] | None = None,
) -> SearchDriver:
    return SearchDriver(
        experiment_id=EXPERIMENT,
        attack=attack or _attack(),
        spec=_spec(),
        context=hooks.context,
        hooks=hooks,
        known_runs=known or {},
        previous=previous,
    )


# ---------------------------------------------------------------- chạy liền mạch


def test_search_found_with_interim_reports_and_bootstrap() -> None:
    hooks = FakeHooks(_context(), crossing(6.3))
    assert _driver(hooks).run() is False
    final = hooks.reports[-1]
    assert final.stage == SearchStage.DONE and final.status == SearchStatus.FOUND
    a, b = final.bracket
    assert a < 6.3 <= b and b - a <= 0.5
    # Một run cho mỗi điểm không synthetic, đúng scope và search_order.
    assert final.points_used == len(hooks.created) <= final.max_points
    for run_id, level, scope, order in hooks.created:
        point = final.trajectory[order]
        assert (point.run_id, point.level, point.scope) == (run_id, level, scope)
    assert all(level != 0 for _, level, _, _ in hooks.created)
    # SearchResult tạm thời sau mỗi điểm (trừ điểm cuối, gửi kết quả cuối).
    interim = hooks.reports[:-1]
    assert len(interim) == len(hooks.created) - 1
    assert all(r.status is None for r in interim)
    assert [r.points_used for r in interim] == list(range(1, len(interim) + 1))
    # Bootstrap trên điểm toàn slice.
    full = [p for p in final.trajectory if p.scope == EvalScope.FULL and not p.synthetic]
    assert full and all(p.drop_ci is not None for p in full)
    assert final.confidence_interval is not None


def test_subset_points_use_subset_scope_and_full_points_confirm() -> None:
    hooks = FakeHooks(_context(), crossing(6.3))
    _driver(hooks).run()
    scopes = [scope for _, _, scope, _ in hooks.created]
    assert EvalScope.SUBSET in scopes and EvalScope.FULL in scopes
    assert scopes.index(EvalScope.FULL) > max(
        i for i, s in enumerate(scopes) if s == EvalScope.SUBSET
    )


def test_small_slice_has_no_subset_points() -> None:
    hooks = FakeHooks(_context(), crossing(6.3))
    _driver(hooks, _attack(subset_size=N_IMAGES)).run()
    assert {scope for _, _, scope, _ in hooks.created} == {EvalScope.FULL}


def test_bootstrap_disabled_gives_no_intervals() -> None:
    hooks = FakeHooks(_context(), crossing(6.3))
    _driver(hooks, _attack(bootstrap_samples=0)).run()
    final = hooks.reports[-1]
    assert final.confidence_interval is None
    assert all(p.drop_ci is None for p in final.trajectory)
    assert final.near_threshold is False


def test_missing_predictions_are_left_out_of_bootstrap() -> None:
    hooks = FakeHooks(_context(), crossing(6.3))
    hooks.with_predictions = False
    _driver(hooks).run()
    final = hooks.reports[-1]
    assert final.status == SearchStatus.FOUND
    assert all(p.drop_ci is None for p in final.trajectory)


# ---------------------------------------------------------------- chạy tiếp sau gián đoạn


@pytest.mark.parametrize("cut", [1, 4, 7, 9])
def test_resume_from_interim_does_not_reevaluate(cut: int) -> None:
    straight = FakeHooks(_context(), crossing(6.3), crossing(9.1))
    _driver(straight).run()
    expected = straight.reports[-1]
    previous = straight.reports[cut - 1]  # SearchResult tạm thời sau `cut` điểm
    # Worker chết sau khi tạo run cho điểm kế tiếp nhưng trước khi chạy xong.
    next_run, level, scope, order = straight.created[cut]
    known = {order: KnownRun(next_run, level, scope, RunStatus.RUNNING, None)}
    resumed = FakeHooks(_context(), crossing(6.3), crossing(9.1))
    # Prediction của run phiên trước đọc từ MinIO (đề xuất contract 001); hook giả biết các run đó.
    resumed.runs.update(straight.runs)
    _driver(resumed, previous=previous, known=known).run()
    final = resumed.reports[-1]
    assert (final.status, final.bracket, final.trajectory) == (
        expected.status,
        expected.bracket,
        expected.trajectory,
    )
    assert resumed.executed[0] == next_run  # chạy tiếp run đã tạo, không tạo lại
    already = {p.run_id for p in previous.trajectory if p.run_id is not None}
    assert not already & set(resumed.executed)
    assert len(resumed.created) == len(straight.created) - cut - 1


def test_known_completed_run_uses_its_metrics() -> None:
    straight = FakeHooks(_context(), crossing(6.3))
    _driver(straight).run()
    previous = straight.reports[2]
    run_id, level, scope, order = straight.created[3]
    known = {order: KnownRun(run_id, level, scope, RunStatus.COMPLETED, _metrics(0.9))}
    resumed = FakeHooks(_context(), crossing(6.3))
    resumed.runs[run_id] = (level, scope, order)
    _driver(resumed, previous=previous, known=known).run()
    assert run_id not in resumed.executed
    assert resumed.reports[0].trajectory[order].drop == pytest.approx(0.9)


def test_previous_final_result_is_not_sent_again() -> None:
    straight = FakeHooks(_context(), crossing(6.3))
    _driver(straight).run()
    again = FakeHooks(_context(), crossing(6.3))
    assert _driver(again, previous=straight.reports[-1]).run() is False
    assert again.reports == [] and again.created == []


# ---------------------------------------------------------------- dừng, hủy, lỗi


def test_directive_stop_gives_stopped_limit() -> None:
    hooks = FakeHooks(_context(), crossing(6.3), stop_after=5)
    assert _driver(hooks).run() is True
    final = hooks.reports[-1]
    assert final.status == SearchStatus.STOPPED_LIMIT
    assert final.points_used == 5
    assert final.bracket == hooks.reports[-2].bracket


def test_cancelled_run_gives_stopped_limit_and_stops_experiment() -> None:
    cancelled = PointOutcome(RunStatus.CANCELLED, None, "Experiment bị hủy", stop=True)
    hooks = FakeHooks(_context(), crossing(6.3), outcome_override={3: cancelled})
    assert _driver(hooks).run() is True
    final = hooks.reports[-1]
    assert final.status == SearchStatus.STOPPED_LIMIT
    assert final.trajectory[-1].order == 2  # điểm bị hủy không vào quỹ đạo


def test_failed_run_fails_search_with_message() -> None:
    failed = PointOutcome(RunStatus.FAILED, None, "RuntimeError: CUDA lỗi")
    hooks = FakeHooks(_context(), crossing(6.3), outcome_override={2: failed})
    assert _driver(hooks).run() is False
    final = hooks.reports[-1]
    assert final.status == SearchStatus.FAILED
    assert final.message is not None and "CUDA lỗi" in final.message
    assert final.trajectory[-1].drop is None


def test_skipped_incompatible_run_fails_search() -> None:
    skipped = PointOutcome(RunStatus.SKIPPED, None, "pgd_linf cần gradient")
    hooks = FakeHooks(_context(), crossing(6.3), outcome_override={1: skipped})
    _driver(hooks).run()
    final = hooks.reports[-1]
    assert final.status == SearchStatus.FAILED and "gradient" in (final.message or "")


def test_zero_clean_map_fails_search() -> None:
    zero = RunMetrics(
        clean=MapPair(map50=0.0, map50_95=0.0),
        attacked=MapPair(map50=0.0, map50_95=0.0),
        relative_drop=None,
        absolute_drop=0.0,
        attack_success_rate=None,
    )
    hooks = FakeHooks(
        _context(), crossing(6.3), outcome_override={1: PointOutcome(RunStatus.COMPLETED, zero)}
    )
    _driver(hooks).run()
    final = hooks.reports[-1]
    assert final.status == SearchStatus.FAILED and final.message


def test_known_run_with_mismatched_level_is_rejected() -> None:
    straight = FakeHooks(_context(), crossing(6.3))
    _driver(straight).run()
    run_id, level, scope, order = straight.created[1]
    known = {order: KnownRun(run_id, level + 1, scope, RunStatus.RUNNING, None)}
    resumed = FakeHooks(_context(), crossing(6.3))
    with pytest.raises(ValueError, match="level/scope"):
        _driver(resumed, previous=straight.reports[0], known=known).run()
