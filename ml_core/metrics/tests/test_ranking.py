"""Xếp hạng attack (validation.md Phase 6, mục Xếp hạng)."""

import json
from pathlib import Path
from uuid import UUID, uuid5

import pytest

from advertest_contracts.enums import AttackKind, RunStatus
from advertest_contracts.models import (
    ExperimentDetail,
    MapPair,
    RunMetrics,
    RunView,
    StatusReason,
)
from ml_core.metrics.ranking import RankingAttack, RankingRun, rank_attack, rank_attacks

NS = UUID("12345678-1234-5678-1234-567812345678")
MOCKS = Path(__file__).resolve().parents[3] / "contracts" / "mocks"
SEEDS = Path(__file__).resolve().parents[3] / "contracts" / "seeds" / "attack_specs.json"


def _metrics(drop: float, partial: bool = False) -> RunMetrics:
    clean = 0.5
    attacked = clean * (1 - drop)
    return RunMetrics(
        clean=MapPair(map50=clean, map50_95=0.3),
        attacked=MapPair(map50=attacked, map50_95=0.1),
        relative_drop=drop,
        absolute_drop=clean - attacked,
        attack_success_rate=None,
        partial=partial,
    )


def _done(level: float, drop: float, partial: bool = False) -> RankingRun:
    status = RunStatus.STOPPED_LIMIT if partial else RunStatus.COMPLETED
    return RankingRun(uuid5(NS, f"run-{level}"), level, status, None, _metrics(drop, partial))


def _early(level: float, trigger: float) -> RankingRun:
    reason = StatusReason(
        code="early_stop", message="Bỏ qua", trigger_run_id=uuid5(NS, f"run-{trigger}")
    )
    return RankingRun(uuid5(NS, f"run-{level}"), level, RunStatus.SKIPPED, reason, None)


def _attack(name: str, runs: list[RankingRun], max_level: float = 10) -> RankingAttack:
    return RankingAttack(uuid5(NS, name), name, AttackKind.ATTACK, max_level, runs)


def test_trapezoid_with_origin() -> None:
    entry = rank_attack(_attack("a", [_done(2, 0.2), _done(6, 0.6), _done(10, 0.8)]))
    # (0,0)-(0.2,0.2)-(0.6,0.6)-(1,0.8): 0.02 + 0.16 + 0.28
    assert entry.auc_drop == pytest.approx(0.46)
    assert entry.coverage == pytest.approx(1.0)
    assert entry.max_relative_drop == pytest.approx(0.8)
    assert (entry.levels_evaluated, entry.levels_early_stopped) == (3, 0)


def test_no_extrapolation_beyond_coverage() -> None:
    entry = rank_attack(_attack("a", [_done(2, 0.4), _done(4, 0.4)]))
    assert entry.auc_drop == pytest.approx(0.04 + 0.08)
    assert entry.coverage == pytest.approx(0.4)


def test_early_stop_uses_trigger_drop_and_counts_as_point() -> None:
    entry = rank_attack(_attack("a", [_done(2, 0.97), _early(4, 2), _early(8, 2)]))
    assert (entry.levels_evaluated, entry.levels_early_stopped) == (1, 2)
    # (0,0)-(0.2,0.97)-(0.4,0.97)-(0.8,0.97)
    assert entry.auc_drop == pytest.approx(0.097 + 0.194 + 0.388)
    assert entry.max_relative_drop == pytest.approx(0.97)
    assert entry.coverage == pytest.approx(0.8)


def test_fewer_than_two_points_is_null_and_last() -> None:
    single = _attack("single", [_done(4, 0.9)])
    strong = _attack("strong", [_done(2, 0.5), _done(4, 0.6)])
    weak = _attack("weak", [_done(2, 0.1), _done(4, 0.2)])
    empty = _attack("empty", [RankingRun(uuid5(NS, "q"), 2, RunStatus.QUEUED)])
    ranked = rank_attacks([single, weak, empty, strong])
    assert [e.name for e in ranked] == ["strong", "weak", "single", "empty"]
    assert ranked[2].auc_drop is None and ranked[3].auc_drop is None
    assert ranked[3].coverage is None and ranked[3].max_relative_drop is None


def test_partial_flag() -> None:
    assert rank_attack(_attack("a", [_done(2, 0.2), _done(4, 0.5, partial=True)])).partial
    assert not rank_attack(_attack("a", [_done(2, 0.2), _done(4, 0.5)])).partial


def test_matches_full_catalog_mock() -> None:
    """Hàm cho cùng bảng xếp hạng với mock của Group 0 (tính độc lập bằng script sinh mock)."""
    detail = ExperimentDetail.model_validate_json(
        (MOCKS / "experiment_detail" / "full_catalog.json").read_text()
    )
    specs = {s["id"]: s for s in json.loads(SEEDS.read_text())}
    views = [
        RunView.model_validate_json(p.read_text())
        for p in (MOCKS / "run_view").glob("catalog_*.json")
    ]
    attacks = []
    for config in detail.config.attacks:
        spec = specs[str(config.attack_spec_id)]
        runs = [
            RankingRun(v.run_id, v.level, v.status, v.status_reason, v.metrics)
            for v in views
            if v.attack_spec_id == config.attack_spec_id
        ]
        attacks.append(
            RankingAttack(
                config.attack_spec_id,
                spec["name"],
                AttackKind(spec["kind"]),
                spec["primary_param"]["max"],
                runs,
            )
        )
    ranked = rank_attacks(attacks)
    assert [e.name for e in ranked] == [e.name for e in detail.attack_ranking]
    for got, want in zip(ranked, detail.attack_ranking, strict=True):
        assert (
            got.auc_drop == pytest.approx(want.auc_drop, abs=1e-3)
            if want.auc_drop
            else (got.auc_drop is None)
        )
        assert (got.levels_evaluated, got.levels_early_stopped, got.partial) == (
            want.levels_evaluated,
            want.levels_early_stopped,
            want.partial,
        )
        assert got.coverage == pytest.approx(want.coverage, abs=1e-3)
