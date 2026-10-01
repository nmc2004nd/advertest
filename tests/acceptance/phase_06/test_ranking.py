"""validation.md Phase 6, Xếp hạng (`test_ranking.py`)."""

from __future__ import annotations

from itertools import pairwise
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from advertest_contracts.enums import AttackKind, RunStatus, SkipReason
from advertest_contracts.models import RunMetrics, StatusReason
from attacks.registry import get_spec, load_catalog
from backend.app.db import models as m
from ml_core.metrics.ranking import RankingAttack, RankingRun, rank_attack, rank_attacks

from .conftest import grid_attack, ok, post, runs_of


def metrics(drop: float, *, partial: bool = False) -> RunMetrics:
    clean = 0.5
    attacked = clean * (1 - drop)
    return RunMetrics.model_validate(
        {
            "clean": {"map50": clean, "map50_95": 0.3},
            "attacked": {"map50": attacked, "map50_95": attacked / 2},
            "relative_drop": drop,
            "absolute_drop": clean - attacked,
            "attack_success_rate": None,
            "partial": partial,
        }
    )


def done(level: float, drop: float, **kw: Any) -> RankingRun:
    return RankingRun(uuid4(), level, RunStatus.COMPLETED, metrics=metrics(drop, **kw))


def early(level: float, trigger: RankingRun) -> RankingRun:
    reason = StatusReason(
        code=SkipReason.EARLY_STOP, message="Bỏ qua", trigger_run_id=trigger.run_id
    )
    return RankingRun(uuid4(), level, RunStatus.SKIPPED, status_reason=reason)


def ranking(name: str, max_level: float, runs: list[RankingRun]) -> RankingAttack:
    return RankingAttack(uuid4(), name, AttackKind.CORRUPTION, max_level, runs)


def test_trapezoid_normalized_from_origin_to_coverage() -> None:
    """Severity 1 của dải 1-5 → x = 0.2; có (0, 0) ở đầu; dừng ở coverage, không ngoại suy."""
    entry = rank_attack(ranking("fog", 5, [done(1, 0.2), done(3, 0.5)]))
    # (0,0)-(0.2,0.2): 0.02; (0.2,0.2)-(0.6,0.5): 0.4 * 0.35 = 0.14.
    assert entry.auc_drop == pytest.approx(0.16)
    assert entry.coverage == pytest.approx(0.6)
    assert entry.max_relative_drop == pytest.approx(0.5)
    assert entry.levels_evaluated == 2 and not entry.partial


def test_early_stop_level_uses_trigger_drop() -> None:
    trigger = done(8, 0.97)
    entry = rank_attack(
        ranking("fgsm", 32, [done(2, 0.1), trigger, early(16, trigger), early(32, trigger)])
    )
    points = [(0, 0), (2 / 32, 0.1), (8 / 32, 0.97), (16 / 32, 0.97), (1.0, 0.97)]
    expected = sum((x2 - x1) * (y1 + y2) / 2 for (x1, y1), (x2, y2) in pairwise(points))
    assert entry.auc_drop == pytest.approx(expected)
    assert entry.levels_early_stopped == 2 and entry.coverage == pytest.approx(1.0)


def test_fewer_than_two_points_is_null_and_last() -> None:
    one = ranking("pgd_l2", 16, [done(1, 0.3)])
    trigger = done(1, 0.99)
    collapsed_first = ranking("frost", 5, [trigger, early(3, trigger), early(5, trigger)])
    weak = ranking("snow", 5, [done(1, 0.05), done(5, 0.1)])
    entries = rank_attacks([one, weak, collapsed_first])
    assert [e.name for e in entries] == ["frost", "snow", "pgd_l2"]
    assert entries[-1].auc_drop is None
    assert entries[0].auc_drop is not None  # sụp ngay level đầu vẫn có diện tích


def test_partial_flag() -> None:
    stopped = RankingRun(uuid4(), 3, RunStatus.STOPPED_LIMIT, metrics=metrics(0.4, partial=True))
    assert rank_attack(ranking("contrast", 5, [done(1, 0.1), stopped])).partial
    assert rank_attack(ranking("contrast", 5, [done(1, 0.1), done(3, 0.4, partial=True)])).partial
    assert not rank_attack(ranking("contrast", 5, [done(1, 0.1), done(3, 0.4)])).partial


# ---------------------------------------------------------------- qua API


@pytest.mark.db
def test_api_ranking_matches_ml_core(api: Any, owner_engine: Engine) -> None:
    target = api.target()
    _, _, client = api.user("engineer")
    body = api.body(target, [grid_attack("fgsm", [2, 8, 16]), grid_attack("fog", [1, 3, 5])])
    experiment = ok(post(client, "/experiments", body)).json()
    runs = {(r["attack_spec"]["name"], r["level"]): r for r in runs_of(client, experiment["id"])}
    trigger = runs[("fgsm", 8.0)]
    values = {
        ("fgsm", 2.0): (RunStatus.COMPLETED, metrics(0.2), None),
        ("fgsm", 8.0): (RunStatus.COMPLETED, metrics(0.98), None),
        ("fgsm", 16.0): (RunStatus.SKIPPED, None, StatusReason(
            code=SkipReason.EARLY_STOP, message="Bỏ qua", trigger_run_id=UUID(trigger["run_id"]))),
        ("fog", 1.0): (RunStatus.COMPLETED, metrics(0.1), None),
        ("fog", 3.0): (RunStatus.COMPLETED, metrics(0.3), None),
        ("fog", 5.0): (RunStatus.STOPPED_LIMIT, metrics(0.4, partial=True),
                       StatusReason(code="time", message="Hết thời gian")),
    }  # fmt: skip
    with Session(owner_engine) as session, session.begin():
        for key, (status, run_metrics, reason) in values.items():
            row = session.get(m.Run, UUID(runs[key]["run_id"]))
            assert row is not None
            row.status = status
            row.metrics = run_metrics.model_dump(mode="json") if run_metrics else None
            row.status_reason = reason.model_dump(mode="json") if reason else None
            if status != RunStatus.SKIPPED:
                row.fingerprint = uuid4().hex * 2
    detail = client.get(f"/experiments/{experiment['id']}").json()
    catalog = load_catalog()
    expected = rank_attacks(
        [
            RankingAttack(
                get_spec(catalog, name=name).id, name,
                get_spec(catalog, name=name).kind,
                get_spec(catalog, name=name).primary_param.max,
                [
                    RankingRun(UUID(runs[(name, level)]["run_id"]), level, status,
                               status_reason=reason, metrics=run_metrics)
                    for (n, level), (status, run_metrics, reason) in values.items() if n == name
                ],
            )
            for name in ("fgsm", "fog")
        ]
    )  # fmt: skip
    assert detail["attack_ranking"] == [e.model_dump(mode="json") for e in expected]
    assert detail["attack_ranking"][0]["name"] == "fgsm"
    assert detail["attack_ranking"][1]["partial"] is True
