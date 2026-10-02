"""validation.md Phase 7, API (`test_search_api.py`). API thật trên DB tạm; endpoint nội bộ gọi bằng
`WorkerClient` với token của máy chạy, như worker."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text

from advertest_contracts.enums import EvalScope, SearchStatus
from advertest_contracts.models import RunSkipRequest, SearchResult, SearchRunCreate
from advertest_worker.client import ApiError, LeaseLost, WorkerClient
from attacks.registry import get_spec, load_catalog

from .conftest import (
    SUBSET,
    Crash,
    Recorder,
    attack,
    detail_of,
    error,
    ok,
    post,
    result_of,
    runs_of,
    search_attack,
    setup,
)

pytestmark = pytest.mark.db

SLICE_IMAGES = 5
FGSM_SEARCH: dict[str, Any] = {"threshold": 0.5, "lo": 0, "hi": 16, "tol": 2, "coarse_n": 3}


def _create_error(api: Any, attacks: list[dict[str, Any]]) -> tuple[int, str, list[str]]:
    target = api.target()
    _, _, client = api.user("engineer")
    status, code, paths = error(post(client, "/experiments", api.body(target, attacks)))
    return int(status), str(code), list(paths)


# ---------------------------------------------------------------- kiểm tra cấu hình


def test_patch_search_not_supported_yet(api: Any) -> None:
    status, code, paths = _create_error(api, [search_attack("adv_patch", lo=0.02, hi=0.25)])
    assert (status, code) == (422, "not_supported_yet")
    assert paths == ["attacks.0.mode"]


@pytest.mark.parametrize(
    ("change", "path"),
    [
        ({"lo": 10, "hi": 5}, "attacks.0.search"),
        ({"tol": 0}, "attacks.0.search.tol"),
        ({"tol": -1}, "attacks.0.search.tol"),
        ({"lo": 0, "hi": 16, "tol": 16}, "attacks.0.search"),
        ({"coarse_n": 2}, "attacks.0.search.coarse_n"),
        ({"coarse_n": 9}, "attacks.0.search.coarse_n"),
        ({"subset_size": 1}, "attacks.0.search.subset_size"),
        ({"subset_size": SLICE_IMAGES + 1}, "attacks.0.search.subset_size"),
        ({"threshold": 0}, "attacks.0.search.threshold"),
        ({"threshold": 1.5}, "attacks.0.search.threshold"),
        ({"lo": -1}, "attacks.0.search.lo"),
        ({"hi": 40}, "attacks.0.search.hi"),
        ({"class_filter": "bicycle"}, "attacks.0.search.class_filter"),
        ({"class_filter": ["car"]}, "attacks.0.search.class_filter"),
    ],
    ids=[
        "lo>=hi", "tol=0", "tol<0", "tol>=hi-lo", "coarse_n=2", "coarse_n=9", "subset=1",
        "subset>slice", "threshold=0", "threshold>1", "lo<min", "hi>max", "class-not-target",
        "class-list",
    ],
)  # fmt: skip
def test_search_rules_return_field_paths(api: Any, change: dict[str, Any], path: str) -> None:
    status, _, paths = _create_error(api, [search_attack("pgd_linf", **change)])
    assert status == 422
    # Lỗi một trường: đúng trường; lỗi giữa các trường (lo/hi/tol): ở `search` hoặc trường con.
    if path.count(".") == 3:
        assert path in paths, paths
    else:
        assert paths and all(p.startswith(path) for p in paths), paths


def test_discrete_bounds_must_be_spec_values(api: Any) -> None:
    status, _, paths = _create_error(api, [search_attack("fog", lo=1.5, hi=5, tol=0.5)])
    assert status == 422 and "attacks.0.search.lo" in paths


# ---------------------------------------------------------------- ước lượng và trần run


def _estimate(client: Any, api: Any, target: Any, attacks: list[dict[str, Any]], **kw: Any) -> Any:
    return ok(post(client, "/experiments/estimate", api.body(target, attacks, **kw))).json()


def test_estimate_search_costs(api: Any) -> None:
    sec = 0.05
    grid = [attack("fgsm", [2, 4])]
    search = search_attack("pgd_linf", lo=0, hi=16, tol=2)
    target, client, _ = setup(api, [*grid, search], sec=sec)
    only_grid = _estimate(client, api, target, grid)
    both = _estimate(client, api, target, [*grid, search])
    # total_seconds và exceeds_limit giữ nghĩa Phase 5-6: không đổi khi thêm attack tìm ngưỡng.
    assert both["total_seconds"] == only_grid["total_seconds"]
    assert both["exceeds_limit"] == only_grid["exceeds_limit"]
    assert [r["attack_spec_id"] for r in both["runs"]] == [
        r["attack_spec_id"] for r in only_grid["runs"]
    ]
    (row,) = both["searches"]
    assert row["attack_spec_id"] == search["attack_spec_id"]
    assert row["max_points"] == row["max_subset_points"] + row["max_full_points"]
    expected = (
        (row["max_subset_points"] * SUBSET + row["max_full_points"] * SLICE_IMAGES) * sec * 1.2
    )
    assert row["max_seconds"] == pytest.approx(expected)
    assert both["max_total_seconds"] == pytest.approx(both["total_seconds"] + expected)
    assert both["max_exceeds_limit"] is False
    assert only_grid.get("max_total_seconds") is None
    assert not only_grid.get("max_exceeds_limit")

    search_only = _estimate(client, api, target, [search])
    assert search_only["runs"] == [] and len(search_only["searches"]) == 1

    # Giới hạn nhỏ hơn chi phí tối đa: chỉ cảnh báo, vẫn tạo được experiment.
    small = {"kind": "time", "value": str(int(both["max_total_seconds"]) - 1 or 1)}
    warned = _estimate(client, api, target, [*grid, search], limit=small)
    assert warned["max_exceeds_limit"] is True
    ok(post(client, "/experiments", api.body(target, [*grid, search], limit=small)))


def _grid_filler(n: int) -> list[dict[str, Any]]:
    """`n` run quét lưới trên các attack không dùng cho tìm ngưỡng (occlusion tối đa 12 level,
    corruption 5 level)."""
    out, left = [], n
    take = min(left, 12)
    out.append(attack("bbox_occlusion", [round(0.05 * (k + 1), 2) for k in range(take)]))
    left -= take
    for name in ("fog", "snow", "frost", "motion_blur", "contrast"):
        if left == 0:
            break
        take = min(left, 5)
        out.append(attack(name, [float(k + 1) for k in range(take)]))
        left -= take
    assert left == 0
    return out


def test_grid_runs_plus_max_points_capped_at_50(api: Any) -> None:
    searches = [search_attack("pgd_linf"), search_attack("fgsm")]
    target, client, _ = setup(api, [searches[0]])
    used = sum(r["max_points"] for r in _estimate(client, api, target, searches)["searches"])
    room = 50 - used
    assert room >= 1
    _estimate(client, api, target, [*searches, *_grid_filler(room)])
    status, _, paths = error(
        post(client, "/experiments", api.body(target, [*searches, *_grid_filler(room + 1)]))
    )
    assert status == 422 and paths == ["attacks"]


# ---------------------------------------------------------------- tiến độ và hàng đợi


def test_images_total_grows_with_dynamic_runs(api: Any, recorder: Recorder) -> None:
    target, client, experiment_id = setup(api, [search_attack("fgsm", **FGSM_SEARCH)])
    assert detail_of(client, experiment_id)["progress"]["images_total"] == 0
    seen: list[int] = []
    api.work(
        target,
        experiment_id,
        on_batch=lambda *_: seen.append(
            detail_of(client, experiment_id)["progress"]["images_total"]
        ),
    )
    runs = runs_of(client, experiment_id)
    total = sum(r["progress"]["images_total"] for r in runs)
    assert seen == sorted(seen) and len(set(seen)) >= 2
    assert detail_of(client, experiment_id)["progress"]["images_total"] == total
    assert {r["progress"]["images_total"] for r in runs} == {SUBSET, SLICE_IMAGES}


def test_queue_ahead_counts_search_max_seconds(api: Any, recorder: Recorder) -> None:
    """Experiment tìm ngưỡng đang chờ phía trước: `ahead_seconds` gồm `max_seconds` của nó (chưa
    dùng giây nào). `ahead_seconds` chỉ tính experiment `queued` (Phase 5): khi worker đã nhận thì
    experiment không còn đứng trước."""
    sec = 0.05
    search = search_attack("fgsm", **FGSM_SEARCH)
    target, client, first = setup(api, [search], sec=sec)
    later = [attack("fgsm", [1])]
    (row,) = _estimate(client, api, target, [search])["searches"]
    queued = _estimate(client, api, target, later)["queue"]
    assert queued["position"] == 2
    assert queued["ahead_seconds"] == pytest.approx(row["max_seconds"])

    def crash(result: SearchResult) -> None:
        raise Crash  # worker chết sau điểm đầu tiên: experiment đang chạy

    recorder.on_report = crash
    with pytest.raises(Crash):
        api.work(target, first)
    running = _estimate(client, api, target, later)["queue"]
    assert running == {"position": 1, "ahead_seconds": 0}


# ---------------------------------------------------------------- endpoint nội bộ của worker


def _leased_after_first_point(api: Any, recorder: Recorder, attacks: list[dict[str, Any]]) -> Any:
    """Worker chết ngay sau điểm tìm ngưỡng đầu tiên: lease còn hiệu lực, run đầu đã xong."""

    def crash(result: SearchResult) -> None:
        raise Crash

    recorder.on_report = crash
    target, client, experiment_id = setup(api, attacks)
    with pytest.raises(Crash):
        api.work(target, experiment_id)
    recorder.on_report = None
    worker = WorkerClient(api.client(), target.token, sleep=lambda _s: None)
    return worker, recorder.lease_ids[-1], UUID(experiment_id), client, recorder.reports[-1][1]


def _run(
    spec: str, lease: UUID, level: float, order: int, scope: EvalScope = EvalScope.SUBSET
) -> SearchRunCreate:
    return SearchRunCreate(lease_id=lease, attack_spec_id=get_spec(load_catalog(), name=spec).id,
                           level=level, scope=scope, search_order=order)  # fmt: skip


def test_dynamic_run_violations_are_422(api: Any, recorder: Recorder) -> None:
    attacks = [attack("fog", [1]), search_attack("fgsm", **FGSM_SEARCH)]
    worker, lease, experiment_id, _, first = _leased_after_first_point(api, recorder, attacks)
    order = len(first.trajectory)

    def rejected(body: SearchRunCreate) -> int:
        with pytest.raises(ApiError) as caught:
            worker.create_search_run(experiment_id, body)
        assert not isinstance(caught.value, LeaseLost)
        return caught.value.status_code

    assert rejected(_run("fgsm", lease, 20.0, order)) == 422  # ngoài [lo, hi]
    assert rejected(_run("fgsm", lease, -1.0, order)) == 422
    assert rejected(_run("fog", lease, 2.0, order)) == 422  # attack quét lưới
    # Tạo đủ max_points run rồi thêm một: 422.
    created = first.points_used
    levels = iter([0.5 + k for k in range(first.max_points)])
    while created < first.max_points:
        worker.create_search_run(experiment_id, _run("fgsm", lease, next(levels), order))
        order, created = order + 1, created + 1
    assert rejected(_run("fgsm", lease, 15.5, order)) == 422
    # Lease vẫn còn: các 422 không làm mất lease.
    assert worker.heartbeat(lease, experiment_id).action == "continue"


def test_other_target_token_is_403(api: Any, recorder: Recorder) -> None:
    _, lease, experiment_id, _, first = _leased_after_first_point(
        api, recorder, [search_attack("fgsm", **FGSM_SEARCH)]
    )
    other = api.target()
    stranger = WorkerClient(api.client(), other.token, sleep=lambda _s: None)
    with pytest.raises(ApiError) as caught:
        stranger.create_search_run(experiment_id, _run("fgsm", lease, 1.0, len(first.trajectory)))
    assert caught.value.status_code == 403


def test_worker_keeps_going_after_422(
    api: Any, recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Worker gửi level ngoài dải cho FGSM (API trả 422): tìm ngưỡng FGSM `failed`, tìm ngưỡng fog
    vẫn chạy xong, experiment `completed`."""
    original = WorkerClient.create_search_run

    def out_of_range(self: WorkerClient, experiment_id: UUID, body: SearchRunCreate) -> Any:
        if body.attack_spec_id == get_spec(load_catalog(), name="fgsm").id:
            body = body.model_copy(update={"level": 99.0})
        return original(self, experiment_id, body)

    monkeypatch.setattr(WorkerClient, "create_search_run", out_of_range)
    attacks = [
        search_attack("fgsm", **FGSM_SEARCH),
        search_attack("fog", threshold=0.2, lo=1, hi=5, tol=4 / 256),
    ]
    target, client, experiment_id = setup(api, attacks)
    api.work(target, experiment_id)
    detail = detail_of(client, experiment_id)
    assert detail["status"] == "completed"
    failed = result_of(detail, "fgsm")
    assert failed.status == SearchStatus.FAILED and failed.message
    assert result_of(detail, "fog").status not in (None, SearchStatus.FAILED)


def test_artifact_url_for_finished_run_predictions(api: Any, recorder: Recorder) -> None:
    worker, lease, _, _, first = _leased_after_first_point(
        api, recorder, [search_attack("fgsm", **FGSM_SEARCH)]
    )
    (point,) = [p for p in first.trajectory if not p.synthetic]
    assert point.run_id is not None
    run_id = point.run_id
    url = worker.artifact_url(run_id, lease, f"runs/{run_id}/predictions.json", "GET")
    assert url.startswith("http")
    refused: list[tuple[str, Literal["PUT", "GET", "DELETE"]]] = [
        (f"runs/{run_id}/predictions.json", "PUT"),
        (f"runs/{run_id}/predictions.json", "DELETE"),
        (f"runs/{run_id}/manifest.json", "GET"),
    ]
    for key, method in refused:
        with pytest.raises(LeaseLost) as caught:
            worker.artifact_url(run_id, lease, key, method)
        assert caught.value.status_code == 409, (key, method)


def test_cached_run_has_own_predictions_copy(api: Any) -> None:
    target, client, grid_id = setup(api, [attack("fgsm", [4])])
    api.work(target, grid_id)
    target, client, search_id = setup(api, [search_attack("fgsm", **FGSM_SEARCH)])
    api.work(target, search_id)
    cached = [
        r
        for r in runs_of(client, search_id)
        if (r.get("status_reason") or {}).get("code") == "cached"
    ]
    assert cached
    for run in cached:
        assert run["predictions_key"] == f"runs/{run['run_id']}/predictions.json"


def test_skip_search_run_is_422(api: Any, recorder: Recorder) -> None:
    worker, lease, experiment_id, _, first = _leased_after_first_point(
        api, recorder, [search_attack("fgsm", **FGSM_SEARCH)]
    )
    run = worker.create_search_run(experiment_id, _run("fgsm", lease, 1.0, len(first.trajectory)))
    (done,) = [p for p in first.trajectory if not p.synthetic]
    assert done.run_id is not None
    body = RunSkipRequest(lease_id=lease, code="early_stop", trigger_run_id=done.run_id,
                          message="thử bỏ run tìm ngưỡng")  # fmt: skip
    with pytest.raises(ApiError) as caught:
        worker.skip(run.run_id, body)
    assert caught.value.status_code == 422


# ---------------------------------------------------------------- migration


def test_migration_0008_down_and_up_with_grants(
    alembic_config: Config, owner_engine: Engine
) -> None:
    # Bảng `search_results` có từ trước (khung của Phase 5); 0008 thêm cột và ràng buộc.
    command.downgrade(alembic_config, "0007")
    try:
        runs = {c["name"] for c in inspect(owner_engine).get_columns("runs")}
        assert not {"scope", "search_order", "predictions_key"} & runs
        results = {c["name"] for c in inspect(owner_engine).get_columns("search_results")}
        assert "updated_at" not in results
    finally:
        command.upgrade(alembic_config, "head")
    runs = {c["name"] for c in inspect(owner_engine).get_columns("runs")}
    assert {"scope", "search_order", "predictions_key"} <= runs
    results = {c["name"] for c in inspect(owner_engine).get_columns("search_results")}
    assert "updated_at" in results
    with owner_engine.connect() as conn:
        for privilege in ("SELECT", "INSERT", "UPDATE"):
            granted: bool = conn.execute(
                text("SELECT has_table_privilege('advertest_app', 'search_results', :p)"),
                {"p": privilege},
            ).scalar_one()
            assert granted, privilege
        missing: list[str] = list(
            conn.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                    " AND tablename <> 'alembic_version'"
                    " AND NOT has_table_privilege("
                    "'advertest_app', format('%I.%I', schemaname, tablename), 'SELECT')"
                )
            )
            .scalars()
            .all()
        )
    assert missing == []
