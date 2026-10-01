"""API nội bộ Phase 7 (plan task 21, 22, 22b): tạo run động, SearchResult, hoàn tất experiment
khi còn tìm ngưỡng, đọc prediction của run đã kết thúc, sao chép prediction khi trúng cache."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from advertest_contracts.enums import (
    EvalScope,
    ExperimentStatus,
    LimitKind,
    RunStatus,
    SearchStatus,
    ThresholdKind,
)
from advertest_contracts.models import (
    BundleRun,
    ExperimentConfig,
    RunMetrics,
    SearchConfig,
    WorkerJobBundle,
    WorkerLease,
)
from attacks.registry import get_spec, load_catalog
from backend.app.db import models as m
from backend.app.services import compute_targets, experiment_views, experiments, registry
from backend.app.storage import Buckets
from ml_core.data.slice import create_slice, save_slice
from ml_core.metrics.threshold import threshold_quantity
from ml_core.search.bounds import search_bounds

from .test_worker_api import _auth, _error, _lease, client, clock
from .test_worker_services import FakeClock, World, _completion, _start_request, world

pytestmark = pytest.mark.db
__all__ = ["client", "clock", "world"]
DEV_OPEN = UUID("2edcdef5-0d3a-5d5f-98ac-b02637fa6718")


@pytest.fixture(scope="module")
def big_slice(world: World, app_engine: Engine, buckets: Buckets) -> Iterator[tuple[UUID, int]]:
    """Slice 3 ảnh (fixture có 3 ảnh hợp lệ; slice của `world` chỉ 2 ảnh, không có tập con nào
    nhỏ hơn được), đăng ký qua import-local. Xóa object mới upload khi xong (MinIO dùng chung)."""
    local = world.local
    spec = create_slice(local.manifest, size=3, seed=11)
    save_slice(local.store, spec)
    before = set(buckets.datasets.list())
    with Session(app_engine) as session, session.begin():
        admin = session.get_one(m.User, world.admin_id)
        registry.import_local(session, local.store, buckets, actor=admin)
    yield spec.id, len(spec.image_ids)
    for key in set(buckets.datasets.list()) - before:
        buckets.datasets.delete(key)


@dataclass(frozen=True)
class Setup:
    token: str
    experiment_id: UUID
    target_id: UUID
    search: SearchConfig
    pgd_id: UUID
    fgsm_id: UUID
    images: int


def _setup(
    app_engine: Engine,
    world: World,
    clock: FakeClock,
    big: tuple[UUID, int],
    *,
    grid: bool = True,
    subset_size: int = 2,
    limit: str = "7200",
    use_big: bool = True,
) -> Setup:
    catalog = load_catalog()
    fgsm, pgd = get_spec(catalog, name="fgsm"), get_spec(catalog, name="pgd_linf")
    search = {
        "threshold_kind": "relative_drop", "threshold": 0.2, "lo": 0, "hi": 32, "tol": 0.125,
        "coarse_n": 4, "subset_size": subset_size,
    }  # fmt: skip
    attacks: list[dict[str, Any]] = [
        {"attack_spec_id": str(pgd.id), "spec_sha256": pgd.spec_sha256, "mode": "search",
         "search": search, "seed": 3},
    ]  # fmt: skip
    specs = [pgd]
    if grid:
        attacks.insert(
            0,
            {"attack_spec_id": str(fgsm.id), "spec_sha256": fgsm.spec_sha256, "mode": "grid",
             "grid": {"levels": [4]}, "seed": 0},
        )  # fmt: skip
        specs.insert(0, fgsm)
    with Session(app_engine) as session, session.begin():
        admin = session.get_one(m.User, world.admin_id)
        issued = compute_targets.create(session, actor=admin, name=f"p7-{uuid.uuid4().hex[:8]}")
        config = ExperimentConfig.model_validate(
            {
                "protocol_id": str(DEV_OPEN),
                "model_version_id": str(world.local.card.id),
                "slice_id": str(big[0] if use_big else world.local.slice.id),
                "class_mapping_id": str(world.local.mapping.id),
                "compute_target_id": str(issued.target.id),
                "attacks": attacks,
                "limit": {"kind": LimitKind.TIME, "value": limit},
            }
        )
        slice_row = session.get_one(m.Slice, big[0] if use_big else world.local.slice.id)
        experiment = experiments.create_experiment(
            session, actor=admin, config=config, slice_row=slice_row, specs=specs, clock=clock
        )
        images = len(slice_row.image_ids)
        return Setup(
            issued.token,
            experiment.id,
            issued.target.id,
            SearchConfig.model_validate(search),
            pgd.id,
            fgsm.id,
            images,
        )


def _max_points(world: World, setup: Setup) -> int:
    param = get_spec(load_catalog(), name="pgd_linf").primary_param
    return search_bounds(setup.search, param, setup.images).max_points


def _create(client: TestClient, setup: Setup, lease: WorkerLease, **body: Any) -> Any:
    payload = {
        "lease_id": str(lease.lease_id),
        "attack_spec_id": str(setup.pgd_id),
        "level": 8,
        "scope": "subset",
        "search_order": 1,
        **body,
    }
    return client.post(
        f"/internal/worker/experiments/{setup.experiment_id}/runs",
        json=payload,
        headers=_auth(setup.token),
    )


def _run(app_engine: Engine, run_id: UUID) -> m.Run:
    with Session(app_engine) as session:
        return session.get_one(m.Run, run_id)


def _finish_run(
    client: TestClient,
    app_engine: Engine,
    buckets: Buckets,
    setup: Setup,
    lease: WorkerLease,
    run_id: UUID,
    *,
    status: str = "completed",
    predictions: bool = True,
) -> RunMetrics | None:
    start = client.post(
        f"/internal/worker/runs/{run_id}/start",
        json=_start_request(lease.lease_id).model_dump(mode="json"),
        headers=_auth(setup.token),
    )
    assert start.status_code == 200, start.text
    run = _run(app_engine, run_id)
    completion = _completion(run, lease.lease_id, buckets, status=status, cases=0)
    update: dict[str, Any] = {"scope": EvalScope(run.scope), "search_order": run.search_order}
    if predictions:
        key = f"runs/{run_id}/predictions.json"
        buckets.artifacts.put(key, b'{"key": "x"}')
        update["predictions_key"] = key
    completion = completion.model_copy(
        update={"run_result": completion.run_result.model_copy(update=update)}
    )
    done = client.post(
        f"/internal/worker/runs/{run_id}/complete",
        json=completion.model_dump(mode="json"),
        headers=_auth(setup.token),
    )
    assert done.status_code == 204, done.text
    return completion.run_result.metrics


def _result(
    world: World,
    setup: Setup,
    points: list[tuple[UUID, float, str, float | None]],
    *,
    final: SearchStatus | None = None,
    bracket: tuple[float, float] = (0, 32),
) -> dict[str, Any]:
    """SearchResult với điểm synthetic ở level 0 rồi các `points` (run, level, scope, drop)."""
    trajectory: list[dict[str, Any]] = [
        {"order": 0, "level": 0, "scope": "subset", "drop": 0.0, "synthetic": True,
         "run_id": None},
    ]  # fmt: skip
    for order, (run_id, level, scope, drop) in enumerate(points, start=1):
        trajectory.append(
            {"order": order, "level": level, "scope": scope, "drop": drop, "run_id": str(run_id)}
        )
    found = final in (SearchStatus.FOUND, SearchStatus.NON_MONOTONIC)
    return {
        "experiment_id": str(setup.experiment_id),
        "attack_spec_id": str(setup.pgd_id),
        "stage": "done" if final is not None else "coarse",
        "status": final.value if final is not None else None,
        "threshold_kind": "relative_drop",
        "threshold": 0.2,
        "class_filter": None,
        "metric_kind": "map50",
        "breaking_point": bracket[1] if found else None,
        "bracket": list(bracket),
        "near_threshold": False,
        "max_points": _max_points(world, setup),
        "points_used": len(points),
        "message": "lỗi" if final == SearchStatus.FAILED else None,
        "trajectory": trajectory,
    }


def _post_result(
    client: TestClient, setup: Setup, lease: WorkerLease, result: dict[str, Any]
) -> Any:
    return client.post(
        f"/internal/worker/experiments/{setup.experiment_id}/search-result",
        json={"lease_id": str(lease.lease_id), "result": result},
        headers=_auth(setup.token),
    )


def _relative(metrics: RunMetrics | None) -> float:
    assert metrics is not None
    value = threshold_quantity(metrics, ThresholdKind.RELATIVE_DROP)
    assert value is not None
    return value


def _experiment(app_engine: Engine, experiment_id: UUID) -> m.Experiment:
    with Session(app_engine) as session:
        return session.get_one(m.Experiment, experiment_id)


# ---------------------------------------------------------------- tạo run động (task 21)


def test_create_run_after_grid_runs(
    client: TestClient,
    app_engine: Engine,
    world: World,
    clock: FakeClock,
    big_slice: tuple[UUID, int],
) -> None:
    setup = _setup(app_engine, world, clock, big_slice)
    lease = _lease(client, setup.token)
    response = _create(client, setup, lease)
    assert response.status_code == 201, response.text
    run = BundleRun.model_validate(response.json())
    assert (run.scope, run.search_order, run.images_total, run.seed) == ("subset", 1, 2, 3)
    assert run.status == RunStatus.QUEUED
    rows = sorted((r for r in _runs(app_engine, setup.experiment_id)), key=lambda r: r.ordinal)
    assert rows[-1].id == run.run_id and rows[-1].ordinal > rows[0].ordinal
    full = _create(client, setup, lease, level=4, scope="full", search_order=2)
    assert BundleRun.model_validate(full.json()).images_total == setup.images
    bundle = client.get(
        f"/internal/worker/experiments/{setup.experiment_id}/bundle", headers=_auth(setup.token)
    )
    assert bundle.status_code == 200, bundle.text
    runs = WorkerJobBundle.model_validate(bundle.json()).runs
    assert [(r.scope, r.search_order) for r in runs] == [
        ("full", None), ("subset", 1), ("full", 2),
    ]  # fmt: skip


def _runs(app_engine: Engine, experiment_id: UUID) -> list[m.Run]:
    with Session(app_engine) as session:
        return experiments.runs_of(session, experiment_id)


@pytest.mark.parametrize(
    "body",
    [
        {"level": 40},
        {"level": -1},
        {"search_order": 1, "level": 4},  # trùng search_order với run đầu
    ],
)
def test_create_run_violations_are_422(
    client: TestClient,
    app_engine: Engine,
    world: World,
    clock: FakeClock,
    body: dict[str, Any],
    big_slice: tuple[UUID, int],
) -> None:
    setup = _setup(app_engine, world, clock, big_slice)
    lease = _lease(client, setup.token)
    assert _create(client, setup, lease).status_code == 201
    response = _create(client, setup, lease, **body)
    assert response.status_code == 422 and _error(response) == "invalid_request"


def test_create_run_for_grid_attack_or_bad_scope_is_422(
    client: TestClient,
    app_engine: Engine,
    world: World,
    clock: FakeClock,
    big_slice: tuple[UUID, int],
) -> None:
    setup = _setup(app_engine, world, clock, big_slice)
    lease = _lease(client, setup.token)
    grid = _create(client, setup, lease, attack_spec_id=str(setup.fgsm_id))
    assert grid.status_code == 422
    whole = _setup(app_engine, world, clock, big_slice, use_big=False)
    lease_whole = _lease(client, whole.token)
    assert _create(client, whole, lease_whole).status_code == 422  # slice không lớn hơn tập con


def test_create_run_beyond_max_points_is_422(
    client: TestClient,
    app_engine: Engine,
    world: World,
    clock: FakeClock,
    big_slice: tuple[UUID, int],
) -> None:
    setup = _setup(app_engine, world, clock, big_slice)
    lease = _lease(client, setup.token)
    limit = _max_points(world, setup)
    for order in range(1, limit + 1):
        assert _create(client, setup, lease, search_order=order).status_code == 201
    over = _create(client, setup, lease, search_order=limit + 1)
    assert over.status_code == 422 and _error(over) == "invalid_request"


def test_create_run_with_other_target_token_is_403(
    client: TestClient,
    app_engine: Engine,
    world: World,
    clock: FakeClock,
    big_slice: tuple[UUID, int],
) -> None:
    setup = _setup(app_engine, world, clock, big_slice)
    lease = _lease(client, setup.token)
    other = _setup(app_engine, world, clock, big_slice)
    response = client.post(
        f"/internal/worker/experiments/{setup.experiment_id}/runs",
        json={"lease_id": str(lease.lease_id), "attack_spec_id": str(setup.pgd_id), "level": 8,
              "scope": "subset", "search_order": 1},
        headers=_auth(other.token),
    )  # fmt: skip
    assert response.status_code == 403


# ---------------------------------------------------------------- SearchResult (task 22)


def test_interim_then_final_result_and_completion(
    client: TestClient,
    app_engine: Engine,
    buckets: Buckets,
    world: World,
    clock: FakeClock,
    big_slice: tuple[UUID, int],
) -> None:
    setup = _setup(app_engine, world, clock, big_slice)
    lease = _lease(client, setup.token)
    grid_run = next(r for r in _runs(app_engine, setup.experiment_id) if r.search_order is None)
    _finish_run(client, app_engine, buckets, setup, lease, grid_run.id)
    # Quét lưới xong nhưng còn tìm ngưỡng: experiment vẫn chạy, giữ lease.
    experiment = _experiment(app_engine, setup.experiment_id)
    assert experiment.status == ExperimentStatus.RUNNING and experiment.lease_id is not None

    run = BundleRun.model_validate(_create(client, setup, lease).json())
    metrics = _finish_run(client, app_engine, buckets, setup, lease, run.run_id)
    point = (run.run_id, 8.0, "subset", _relative(metrics))
    interim = _post_result(client, setup, lease, _result(world, setup, [point]))
    assert interim.status_code == 204, interim.text
    with Session(app_engine) as session:
        detail = experiment_views.detail(session, setup.experiment_id)
    assert [r.points_used for r in detail.search_results] == [1]
    assert detail.attack_ranking[0].attack_spec_id == setup.fgsm_id
    assert len(detail.attack_ranking) == 1

    final = _result(world, setup, [point], final=SearchStatus.NOT_REACHED, bracket=(32, 32))
    assert _post_result(client, setup, lease, final).status_code == 204
    experiment = _experiment(app_engine, setup.experiment_id)
    assert experiment.status == ExperimentStatus.COMPLETED and experiment.lease_id is None
    again = _post_result(client, setup, lease, final)
    assert again.status_code == 409  # lease đã bỏ khi experiment xong


def test_final_result_cannot_be_replaced(
    client: TestClient,
    app_engine: Engine,
    buckets: Buckets,
    world: World,
    clock: FakeClock,
    big_slice: tuple[UUID, int],
) -> None:
    setup = _setup(app_engine, world, clock, big_slice)
    lease = _lease(client, setup.token)
    grid_run = next(r for r in _runs(app_engine, setup.experiment_id) if r.search_order is None)
    run = BundleRun.model_validate(_create(client, setup, lease).json())
    metrics = _finish_run(client, app_engine, buckets, setup, lease, run.run_id)
    point = (run.run_id, 8.0, "subset", _relative(metrics))
    failed = _result(world, setup, [point], final=SearchStatus.FAILED)
    assert _post_result(client, setup, lease, failed).status_code == 204
    # Lưới chưa xong nên experiment còn chạy và lease còn: thay kết quả cuối → 422.
    assert _run(app_engine, grid_run.id).status == RunStatus.QUEUED
    replaced = _post_result(client, setup, lease, _result(world, setup, [point]))
    assert replaced.status_code == 422 and _error(replaced) == "invalid_request"


@pytest.mark.parametrize("change", ["order", "level", "drop", "foreign_run", "max_points"])
def test_result_must_match_runs(
    client: TestClient,
    app_engine: Engine,
    buckets: Buckets,
    world: World,
    clock: FakeClock,
    change: str,
    big_slice: tuple[UUID, int],
) -> None:
    setup = _setup(app_engine, world, clock, big_slice)
    lease = _lease(client, setup.token)
    run = BundleRun.model_validate(_create(client, setup, lease).json())
    metrics = _finish_run(client, app_engine, buckets, setup, lease, run.run_id)
    drop = _relative(metrics)
    level, run_id = 8.0, run.run_id
    if change == "level":
        level = 9.0
    if change == "drop":
        drop += 0.1
    if change == "foreign_run":
        run_id = uuid.uuid4()
    result = _result(world, setup, [(run_id, level, "subset", drop)])
    if change == "order":
        result["trajectory"].insert(
            1, {"order": 1, "level": 1, "scope": "subset", "drop": 0.0, "synthetic": True,
                "run_id": None}
        )  # fmt: skip
        for i, point in enumerate(result["trajectory"]):
            point["order"] = i
    if change == "max_points":
        result["max_points"] += 1
    response = _post_result(client, setup, lease, result)
    assert response.status_code == 422, response.text


def test_search_only_experiment_completes_on_final_result(
    client: TestClient,
    app_engine: Engine,
    buckets: Buckets,
    world: World,
    clock: FakeClock,
    big_slice: tuple[UUID, int],
) -> None:
    setup = _setup(app_engine, world, clock, big_slice, grid=False)
    lease = _lease(client, setup.token)
    bundle = client.get(
        f"/internal/worker/experiments/{setup.experiment_id}/bundle", headers=_auth(setup.token)
    )
    assert bundle.status_code == 200 and WorkerJobBundle.model_validate(bundle.json()).runs == []
    run = BundleRun.model_validate(_create(client, setup, lease).json())
    metrics = _finish_run(client, app_engine, buckets, setup, lease, run.run_id)
    assert _experiment(app_engine, setup.experiment_id).status == ExperimentStatus.RUNNING
    point = (run.run_id, 8.0, "subset", _relative(metrics))
    final = _result(world, setup, [point], final=SearchStatus.FAILED)
    assert _post_result(client, setup, lease, final).status_code == 204
    assert _experiment(app_engine, setup.experiment_id).status == ExperimentStatus.COMPLETED


def test_bundle_has_latest_search_result(
    client: TestClient,
    app_engine: Engine,
    buckets: Buckets,
    world: World,
    clock: FakeClock,
    big_slice: tuple[UUID, int],
) -> None:
    setup = _setup(app_engine, world, clock, big_slice, grid=False)
    lease = _lease(client, setup.token)
    run = BundleRun.model_validate(_create(client, setup, lease).json())
    metrics = _finish_run(client, app_engine, buckets, setup, lease, run.run_id)
    point = (run.run_id, 8.0, "subset", _relative(metrics))
    assert _post_result(client, setup, lease, _result(world, setup, [point])).status_code == 204
    bundle = WorkerJobBundle.model_validate(
        client.get(
            f"/internal/worker/experiments/{setup.experiment_id}/bundle",
            headers=_auth(setup.token),
        ).json()
    )
    (result,) = bundle.search_results
    assert result.points_used == 1 and result.trajectory[1].run_id == run.run_id


# ---------------------------------------------------------------- hủy, hết thời gian


def test_cancel_without_worker_finalizes_interim_as_stopped_limit(
    client: TestClient,
    app_engine: Engine,
    buckets: Buckets,
    world: World,
    clock: FakeClock,
    big_slice: tuple[UUID, int],
) -> None:
    setup = _setup(app_engine, world, clock, big_slice, grid=False)
    lease = _lease(client, setup.token)
    run = BundleRun.model_validate(_create(client, setup, lease).json())
    metrics = _finish_run(client, app_engine, buckets, setup, lease, run.run_id)
    point = (run.run_id, 8.0, "subset", _relative(metrics))
    assert _post_result(client, setup, lease, _result(world, setup, [point])).status_code == 204
    clock.advance(300)  # worker chết: lease hết hạn
    with Session(app_engine) as session, session.begin():
        admin = session.get_one(m.User, world.admin_id)
        experiments.cancel(session, actor=admin, experiment_id=setup.experiment_id, clock=clock)
    with Session(app_engine) as session:
        (result,) = experiment_views.detail(session, setup.experiment_id).search_results
    assert result.status == SearchStatus.STOPPED_LIMIT and result.points_used == 1


def test_out_of_time_create_run_finalizes_and_stops(
    client: TestClient,
    app_engine: Engine,
    buckets: Buckets,
    world: World,
    clock: FakeClock,
    big_slice: tuple[UUID, int],
) -> None:
    setup = _setup(app_engine, world, clock, big_slice, grid=False, limit="10")
    lease = _lease(client, setup.token)
    run = BundleRun.model_validate(_create(client, setup, lease).json())
    metrics = _finish_run(client, app_engine, buckets, setup, lease, run.run_id)
    point = (run.run_id, 8.0, "subset", _relative(metrics))
    assert _post_result(client, setup, lease, _result(world, setup, [point])).status_code == 204
    with Session(app_engine) as session, session.begin():
        row = session.get_one(m.Experiment, setup.experiment_id)
        row.processing_seconds_used = Decimal(10)
    response = _create(client, setup, lease, search_order=2)
    assert response.status_code == 409
    experiment = _experiment(app_engine, setup.experiment_id)
    assert experiment.status == ExperimentStatus.COMPLETED
    with Session(app_engine) as session:
        (result,) = experiment_views.detail(session, setup.experiment_id).search_results
    assert result.status == SearchStatus.STOPPED_LIMIT


# ---------------------------------------------------------------- dừng sớm (task 22a)


def test_skip_rejects_search_run(
    client: TestClient,
    app_engine: Engine,
    world: World,
    clock: FakeClock,
    big_slice: tuple[UUID, int],
) -> None:
    setup = _setup(app_engine, world, clock, big_slice)
    lease = _lease(client, setup.token)
    run = BundleRun.model_validate(_create(client, setup, lease).json())
    response = client.post(
        f"/internal/worker/runs/{run.run_id}/skip",
        json={"lease_id": str(lease.lease_id), "code": "early_stop",
              "trigger_run_id": str(uuid.uuid4()), "message": "x"},
        headers=_auth(setup.token),
    )  # fmt: skip
    assert response.status_code == 422


# ---------------------------------------------------------------- prediction (task 22b)


def test_predictions_key_saved_and_readable_after_finish(
    client: TestClient,
    app_engine: Engine,
    buckets: Buckets,
    world: World,
    clock: FakeClock,
    big_slice: tuple[UUID, int],
) -> None:
    setup = _setup(app_engine, world, clock, big_slice)
    lease = _lease(client, setup.token)
    run = BundleRun.model_validate(_create(client, setup, lease).json())
    _finish_run(client, app_engine, buckets, setup, lease, run.run_id)
    key = f"runs/{run.run_id}/predictions.json"
    assert _run(app_engine, run.run_id).predictions_key == key

    def url(method: str, target: str) -> int:
        response = client.post(
            f"/internal/worker/runs/{run.run_id}/artifact-url",
            json={"lease_id": str(lease.lease_id), "key": target, "method": method},
            headers=_auth(setup.token),
        )
        return int(response.status_code)

    assert url("GET", key) == 200
    assert url("PUT", key) == 409
    assert url("DELETE", key) == 409
    assert url("GET", f"runs/{run.run_id}/manifest.json") == 409


def test_complete_requires_predictions_file(
    client: TestClient,
    app_engine: Engine,
    buckets: Buckets,
    world: World,
    clock: FakeClock,
    big_slice: tuple[UUID, int],
) -> None:
    setup = _setup(app_engine, world, clock, big_slice)
    lease = _lease(client, setup.token)
    run = BundleRun.model_validate(_create(client, setup, lease).json())
    client.post(
        f"/internal/worker/runs/{run.run_id}/start",
        json=_start_request(lease.lease_id).model_dump(mode="json"),
        headers=_auth(setup.token),
    )
    row = _run(app_engine, run.run_id)
    completion = _completion(row, lease.lease_id, buckets, cases=0)
    result = completion.run_result.model_copy(
        update={
            "scope": EvalScope(row.scope),
            "search_order": row.search_order,
            "predictions_key": f"runs/{run.run_id}/predictions.json",  # chưa upload
        }
    )
    response = client.post(
        f"/internal/worker/runs/{run.run_id}/complete",
        json=completion.model_copy(update={"run_result": result}).model_dump(mode="json"),
        headers=_auth(setup.token),
    )
    assert response.status_code == 422


def test_cached_run_gets_copy_of_predictions(
    client: TestClient,
    app_engine: Engine,
    buckets: Buckets,
    world: World,
    clock: FakeClock,
    big_slice: tuple[UUID, int],
) -> None:
    first = _setup(app_engine, world, clock, big_slice, grid=False)
    lease = _lease(client, first.token)
    run = BundleRun.model_validate(_create(client, first, lease, scope="full").json())
    start = _start_request(lease.lease_id, seed=777)
    assert (
        client.post(
            f"/internal/worker/runs/{run.run_id}/start",
            json=start.model_dump(mode="json"),
            headers=_auth(first.token),
        ).status_code
        == 200
    )
    row = _run(app_engine, run.run_id)
    completion = _completion(row, lease.lease_id, buckets, cases=0)
    key = f"runs/{run.run_id}/predictions.json"
    buckets.artifacts.put(key, b'{"predictions": {}}')
    result = completion.run_result.model_copy(
        update={
            "scope": EvalScope(row.scope),
            "search_order": row.search_order,
            "predictions_key": key,
        }
    )
    client.post(
        f"/internal/worker/runs/{run.run_id}/complete",
        json=completion.model_copy(update={"run_result": result}).model_dump(mode="json"),
        headers=_auth(first.token),
    )
    second = _setup(app_engine, world, clock, big_slice, grid=False)
    lease2 = _lease(client, second.token)
    run2 = BundleRun.model_validate(_create(client, second, lease2, scope="full").json())
    again = start.model_copy(update={"lease_id": lease2.lease_id})
    response = client.post(
        f"/internal/worker/runs/{run2.run_id}/start",
        json=again.model_dump(mode="json"),
        headers=_auth(second.token),
    )
    assert response.json()["action"] == "skip_cached"
    copied = f"runs/{run2.run_id}/predictions.json"
    assert _run(app_engine, run2.run_id).predictions_key == copied
    assert buckets.artifacts.get(copied) == buckets.artifacts.get(key)


def test_cached_run_without_origin_file_still_skips(
    client: TestClient,
    app_engine: Engine,
    buckets: Buckets,
    world: World,
    clock: FakeClock,
    big_slice: tuple[UUID, int],
) -> None:
    """Review Group 4 #1: file prediction của run gốc đã mất → không sao chép, `start` vẫn trả
    `skip_cached` (không lỗi 500)."""
    first = _setup(app_engine, world, clock, big_slice, grid=False)
    lease = _lease(client, first.token)
    run = BundleRun.model_validate(_create(client, first, lease, scope="full").json())
    start = _start_request(lease.lease_id, seed=778)
    client.post(
        f"/internal/worker/runs/{run.run_id}/start",
        json=start.model_dump(mode="json"),
        headers=_auth(first.token),
    )
    row = _run(app_engine, run.run_id)
    completion = _completion(row, lease.lease_id, buckets, cases=0)
    key = f"runs/{run.run_id}/predictions.json"
    buckets.artifacts.put(key, b"{}")
    result = completion.run_result.model_copy(
        update={
            "scope": EvalScope(row.scope),
            "search_order": row.search_order,
            "predictions_key": key,
        }
    )
    done = client.post(
        f"/internal/worker/runs/{run.run_id}/complete",
        json=completion.model_copy(update={"run_result": result}).model_dump(mode="json"),
        headers=_auth(first.token),
    )
    assert done.status_code == 204, done.text
    buckets.artifacts.delete(key)  # file gốc mất
    second = _setup(app_engine, world, clock, big_slice, grid=False)
    lease2 = _lease(client, second.token)
    run2 = BundleRun.model_validate(_create(client, second, lease2, scope="full").json())
    response = client.post(
        f"/internal/worker/runs/{run2.run_id}/start",
        json=start.model_copy(update={"lease_id": lease2.lease_id}).model_dump(mode="json"),
        headers=_auth(second.token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["action"] == "skip_cached"
    assert _run(app_engine, run2.run_id).predictions_key is None
    assert not buckets.artifacts.exists(f"runs/{run2.run_id}/predictions.json")
