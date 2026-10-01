"""Phase 7 Group 4: kiểm tra cấu hình và ước lượng của tự tìm ngưỡng (plan task 19, 20, 23)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from advertest_contracts.enums import RunStatus
from advertest_contracts.models import PrimaryParam, SearchConfig
from attacks.registry import get_spec, load_catalog
from backend.app.db import models as m
from ml_core.search.bounds import search_bounds

from .test_experiment_api import (
    Api,
    Fx,
    _body,
    _create,
    _error,
    _estimate,
    _new_target,
    _post,
    _profiles,
    api,
    env,
    fx,
    world,
)
from .test_worker_services import _attack

pytestmark = pytest.mark.db
__all__ = ["api", "env", "fx", "world"]


def _search(name: str, **search: Any) -> dict[str, Any]:
    spec = get_spec(load_catalog(), name=name)
    param = spec.primary_param
    body: dict[str, Any] = {
        "threshold_kind": "relative_drop",
        "threshold": 0.2,
        "lo": param.min,
        "hi": param.max,
        "tol": (param.max - param.min) / 256,
        "coarse_n": 4,
        "subset_size": 2,
        **search,
    }
    return {
        "attack_spec_id": str(spec.id),
        "spec_sha256": spec.spec_sha256,
        "mode": "search",
        "search": body,
        "seed": 3,
    }


def _images(fx: Fx) -> int:
    return len(fx.world.local.slice.image_ids)


def _bounds(name: str, attack: dict[str, Any], images: int) -> int:
    param: PrimaryParam = get_spec(load_catalog(), name=name).primary_param
    return search_bounds(SearchConfig.model_validate(attack["search"]), param, images).max_points


# ---------------------------------------------------------------- kiểm tra cấu hình (task 19)


def test_patch_search_is_not_supported(api: Api, fx: Fx) -> None:
    _, client = api.client()
    body = _body(fx, attacks=[_search("adv_patch")])
    assert _error(_post(client, "/experiments", body)) == (
        422, "not_supported_yet", ["attacks.0.mode"],
    )  # fmt: skip


@pytest.mark.parametrize(
    ("attack", "path"),
    [
        (_search("pgd_linf", lo=-1), "attacks.0.search.lo"),
        (_search("pgd_linf", hi=40), "attacks.0.search.hi"),
        (_search("fog", lo=1.5, tol=0.5), "attacks.0.search.lo"),
        (_search("pgd_linf", subset_size=10_000), "attacks.0.search.subset_size"),
        (_search("pgd_linf", class_filter="bicycle"), "attacks.0.search.class_filter"),
        (
            {**_search("pgd_linf"), "training_slice_id": str(uuid.uuid4())},
            "attacks.0.training_slice_id",
        ),
    ],
)
def test_search_rules_with_field_paths(api: Api, fx: Fx, attack: dict[str, Any], path: str) -> None:
    _, client = api.client()
    status, code, paths = _error(_post(client, "/experiments", _body(fx, attacks=[attack])))
    assert (status, code) == (422, "invalid_request")
    assert path in paths


@pytest.mark.parametrize(
    "search",
    [
        {"tol": 40},
        {"tol": 0},
        {"coarse_n": 2},
        {"coarse_n": 9},
        {"subset_size": 1},
        {"threshold": 0},
        {"threshold": 1.5},
        {"class_filter": ["car"]},
        {"lo": 10, "hi": 5},
    ],
)
def test_contract_rules_are_422(api: Api, fx: Fx, search: dict[str, Any]) -> None:
    _, client = api.client()
    response = _post(client, "/experiments", _body(fx, attacks=[_search("pgd_linf", **search)]))
    assert response.status_code == 422


def test_max_runs_counts_max_points(api: Api, fx: Fx) -> None:
    """Kickoff: số run quét lưới cộng tổng `max_points` không vượt 50."""
    images = _images(fx)
    searches = [_search("pgd_linf"), _search("pgd_l2"), _search("fgsm")]
    used = sum(
        _bounds(name, attack, images)
        for name, attack in zip(("pgd_linf", "pgd_l2", "fgsm"), searches, strict=True)
    )
    room = 50 - used
    assert room >= 1

    def grid(n: int) -> list[dict[str, Any]]:
        """`n` run quét lưới chia cho occlusion (tối đa 12 level) và các corruption (5 level)."""
        attacks, left = [], n
        take = min(left, 12)
        attacks.append(_attack("bbox_occlusion", [round(0.05 * (k + 1), 2) for k in range(take)]))
        left -= take
        for name in ("fog", "snow", "frost", "motion_blur", "contrast"):
            if left == 0:
                break
            take = min(left, 5)
            attacks.append(_attack(name, [float(k + 1) for k in range(take)]))
            left -= take
        assert left == 0
        return attacks

    _, client = api.client()
    fits = _body(fx, attacks=[*searches, *grid(room)])
    over = _body(fx, attacks=[*searches, *grid(room + 1)])
    assert _post(client, "/experiments/estimate", fits).status_code == 200
    status, _, paths = _error(_post(client, "/experiments", over))
    assert status == 422 and "attacks" in paths


def test_search_experiment_has_no_runs_until_worker_creates_them(api: Api, fx: Fx) -> None:
    _, client = api.client()
    detail = _create(client, _body(fx, attacks=[_attack("fgsm", [4]), _search("pgd_linf")]))
    runs = client.get(f"/experiments/{detail.id}/runs").json()
    assert [r["level"] for r in runs] == [4]
    assert detail.search_results == []
    assert detail.config.attacks[1].search is not None


def test_absolute_threshold_bounded_by_known_clean_map(
    api: Api, fx: Fx, owner_engine: Engine
) -> None:
    """Quyết định Group 4: kiểm cận `absolute_drop` khi đã biết mAP sạch từ run trước."""
    _, client = api.client()
    first = _create(client, _body(fx, attacks=[_attack("fgsm", [4])]))
    with Session(owner_engine) as s, s.begin():
        run = s.scalar(select(m.Run).where(m.Run.experiment_id == first.id))
        assert run is not None
        run.status = RunStatus.COMPLETED
        run.fingerprint = uuid.uuid4().hex * 2
        run.metrics = {
            "clean": {"map50": 0.4, "map50_95": 0.2},
            "attacked": {"map50": 0.1, "map50_95": 0.05},
            "relative_drop": 0.75,
            "absolute_drop": 0.3,
            "attack_success_rate": 0.5,
        }
    high = _search("pgd_linf", threshold_kind="absolute_drop", threshold=0.5)
    status, _, paths = _error(_post(client, "/experiments", _body(fx, attacks=[high])))
    assert status == 422 and paths == ["attacks.0.search.threshold"]
    ok = _search("pgd_linf", threshold_kind="absolute_drop", threshold=0.3)
    assert _post(client, "/experiments/estimate", _body(fx, attacks=[ok])).status_code == 200


# ---------------------------------------------------------------- ước lượng (task 20, 23)


def test_estimate_searches(api: Api, fx: Fx, owner_engine: Engine) -> None:
    target = _new_target(owner_engine)
    _profiles(owner_engine, fx, target, {"fgsm": 0.5, "pgd_linf": 2.0})
    images = _images(fx)
    search = _search("pgd_linf")
    _, client = api.client()
    result = _estimate(
        client,
        _body(fx, [_attack("fgsm", [2]), search], compute_target_id=str(target)),
    )
    (row,) = result.searches
    bounds = search_bounds(
        SearchConfig.model_validate(search["search"]),
        get_spec(load_catalog(), name="pgd_linf").primary_param,
        images,
    )
    assert (row.max_points, row.max_subset_points, row.max_full_points) == (
        bounds.max_points,
        bounds.max_subset_points,
        bounds.max_full_points,
    )
    expected = (bounds.max_subset_points * 2 + bounds.max_full_points * images) * 2.0 * 1.2
    assert row.max_seconds == pytest.approx(expected)
    assert result.total_seconds == pytest.approx(images * 0.5 * 1.2)
    assert result.max_total_seconds == pytest.approx(images * 0.5 * 1.2 + expected)
    assert len(result.runs) == 1 and result.runs[0].attack_spec_id != row.attack_spec_id
    assert result.max_exceeds_limit is False


def test_estimate_search_only_and_missing_profile(api: Api, fx: Fx, owner_engine: Engine) -> None:
    target = _new_target(owner_engine)
    _, client = api.client()
    result = _estimate(client, _body(fx, [_search("pgd_linf")], compute_target_id=str(target)))
    assert result.runs == [] and result.total_seconds == 0
    assert result.searches[0].max_seconds is None
    assert result.missing_profiles == [result.searches[0].attack_spec_id]
    assert result.max_total_seconds is None


def test_max_exceeds_limit_only_warns(api: Api, fx: Fx, owner_engine: Engine) -> None:
    target = _new_target(owner_engine)
    _profiles(owner_engine, fx, target, {"pgd_linf": 50.0})
    _, client = api.client()
    body = _body(fx, [_search("pgd_linf")], compute_target_id=str(target))
    body["limit"] = {"kind": "time", "value": "10"}
    result = _estimate(client, body)
    assert result.max_exceeds_limit is True and result.exceeds_limit is False
    assert _post(client, "/experiments", body).status_code == 201


def test_queue_ahead_counts_search_max_seconds(api: Api, fx: Fx, owner_engine: Engine) -> None:
    target = _new_target(owner_engine)
    _profiles(owner_engine, fx, target, {"pgd_linf": 1.0})
    _, client = api.client()
    body = _body(fx, [_search("pgd_linf")], compute_target_id=str(target))
    first = _estimate(client, body)
    max_seconds = first.searches[0].max_seconds
    assert max_seconds is not None
    _create(client, body)
    second = _estimate(client, body)
    assert second.queue.position == 2
    assert second.queue.ahead_seconds == pytest.approx(max_seconds)
