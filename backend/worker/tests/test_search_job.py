"""`JobRunner` chạy tìm ngưỡng với executor thật (requirements.md Phase 7, mục Worker; plan task
13-18). API và MinIO là bản giả trong bộ nhớ; endpoint thật của tìm ngưỡng thuộc Group 4.

Dữ liệu: KITTI tổng hợp 3 ảnh (`ml_core/runner/tests/test_run.py`), spec `fog` (rời rạc 1-5, tìm
ngưỡng) và `contrast` (quét lưới). Perturbation và estimator là bản giả tất định (perturbation cộng
hằng số theo level, estimator mất hết object từ level 2.5), để kiểm logic của worker chứ không
kiểm corruption (đã có test riêng ở `attacks/`).
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid5

import httpx
import numpy as np
import pytest

from advertest_contracts.enums import EvalScope, RunStatus, SearchStage, SearchStatus
from advertest_contracts.models import (
    AttackConfig,
    AttackSpec,
    BundleRun,
    Environment,
    FingerprintInputs,
    RunCompletion,
    RunStartRequest,
    RunStartResponse,
    SearchResult,
    SearchResultReport,
    SearchRunCreate,
    WorkerDirective,
    WorkerLease,
)
from advertest_worker import job as job_module
from advertest_worker.job import DirectiveBox, JobRunner
from attacks.registry import get_spec, load_catalog
from ml_core.metrics.bootstrap import load_run_predictions
from ml_core.metrics.filters import Prediction
from ml_core.runner.run import Runner
from ml_core.runner.tests.test_run import Base, _attack, _build, _config
from ml_core.search.subset import eval_image_ids_sha256, select_subset
from ml_core.store import LocalStore

NS = UUID("3d1c0a5e-6f4b-4c8e-9a2d-7e5f1b3c9d0a")
EXPERIMENT = uuid5(NS, "experiment")
LEASE = WorkerLease(
    experiment_id=EXPERIMENT,
    lease_id=uuid5(NS, "lease"),
    lease_expires_at=datetime(2026, 10, 1, 0, 10, tzinfo=UTC),
)
SUBSET = 2


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Base:
    return _build(tmp_path_factory.mktemp("search-job"), supports_gradients=True)


OFFSET = 0.02  # mỗi đơn vị level cộng 0.02 vào mọi điểm ảnh


class FakePerturbation:
    """Cộng hằng số `level * OFFSET`: estimator giả suy ra đúng ảnh và level."""

    def __init__(self, spec: AttackSpec) -> None:
        self.spec = spec

    def apply(
        self,
        images: np.ndarray,
        targets: list[dict[str, Any]],
        level: float,
        seed: int,
        mask: np.ndarray | None = None,
    ) -> np.ndarray:
        return (images + np.float32(level * OFFSET)).astype(np.float32)


class FakeEstimator:
    """Ảnh sạch → giữ mọi ground truth; level ≥ 2.5 → mất hết object (mức sụt tăng theo level)."""

    def __init__(self, clean: dict[str, np.ndarray], targets: dict[str, Any]):
        self.clean, self.targets = clean, targets

    def predict(self, images: np.ndarray, batch_size: int) -> list[Prediction]:
        preds: list[Prediction] = []
        for image in images:
            image_id, level = next(
                (i, float((image - c).mean()) / OFFSET)
                for i, c in self.clean.items()
                if float((image - c).std()) < 1e-4
            )
            target = self.targets[image_id]
            keep = len(target["labels"]) if level < 2.5 else 0
            preds.append(
                {
                    "boxes": np.asarray(target["boxes"], np.float32).reshape(-1, 4)[:keep],
                    "labels": np.asarray(target["labels"], np.int64)[:keep],
                    "scores": np.full(keep, 0.9, np.float32),
                }
            )
        return preds


@dataclass
class World:
    store: LocalStore
    runner_cfg: Runner
    estimator: FakeEstimator
    fog: AttackSpec
    contrast: AttackSpec


@pytest.fixture(scope="module")
def world(base: Base, tmp_path_factory: pytest.TempPathFactory) -> World:
    root = tmp_path_factory.mktemp("search-job-store") / "store"
    shutil.copytree(base.root, root)
    store = LocalStore(root)
    runner = Runner(store, _config(base, [_attack("contrast", [3])]))
    loader = runner.loader
    clean, targets = {}, {}
    for image_id in loader.slice.image_ids:
        image, target, _, _ = loader.load(image_id)
        clean[image_id], targets[image_id] = image, target
    catalog = load_catalog()
    fog, contrast = get_spec(catalog, name="fog"), get_spec(catalog, name="contrast")
    return World(store, runner, FakeEstimator(clean, targets), fog, contrast)


# ---------------------------------------------------------------- API và MinIO giả


@dataclass
class FakeApi:
    attack: AttackConfig
    events: list[tuple[str, Any]] = field(default_factory=list)
    objects: dict[str, bytes] = field(default_factory=dict)
    starts: dict[UUID, FingerprintInputs] = field(default_factory=dict)
    completions: dict[UUID, RunCompletion] = field(default_factory=dict)
    reports: list[SearchResult] = field(default_factory=list)
    created: list[BundleRun] = field(default_factory=list)
    cancel_after_progress: int | None = None
    progress_calls: int = 0

    def http(self) -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            key = request.url.path.removeprefix("/store/")
            if request.method == "PUT":
                self.objects[key] = request.content
                return httpx.Response(200)
            if request.method == "DELETE":
                self.objects.pop(key, None)
                return httpx.Response(204)
            if key not in self.objects:
                return httpx.Response(404)
            return httpx.Response(200, content=self.objects[key])

        return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://store")

    # Các endpoint mà JobRunner gọi.
    def start(self, run_id: UUID, body: RunStartRequest) -> RunStartResponse:
        self.starts[run_id] = body.fingerprint_inputs
        self.events.append(("start", run_id))
        return RunStartResponse(action="run")

    def progress(self, run_id: UUID, body: Any) -> WorkerDirective:
        self.progress_calls += 1
        cancel = (
            self.cancel_after_progress is not None
            and self.progress_calls >= self.cancel_after_progress
        )
        return WorkerDirective(action="cancel" if cancel else "continue", remaining_seconds=None)

    def artifact_url(self, run_id: UUID, lease_id: UUID, key: str, method: str) -> str:
        return f"http://store/store/{key}"

    def complete(self, run_id: UUID, body: RunCompletion) -> None:
        self.completions[run_id] = body
        self.events.append(("complete", run_id))

    def create_search_run(self, experiment_id: UUID, body: SearchRunCreate) -> BundleRun:
        assert self.attack.search is not None
        total = SUBSET if body.scope == EvalScope.SUBSET else 3
        run = BundleRun(
            run_id=uuid5(NS, f"search/{body.search_order}/{len(self.created)}"),
            attack_spec_id=body.attack_spec_id,
            level=body.level,
            seed=self.attack.seed,
            status=RunStatus.QUEUED,
            images_done=0,
            images_total=total,
            checkpoint=None,
            scope=body.scope,
            search_order=body.search_order,
        )
        self.created.append(run)
        self.events.append(("create", run.run_id))
        return run

    def search_result(self, experiment_id: UUID, body: SearchResultReport) -> None:
        self.reports.append(body.result)
        self.events.append(("report", body.result.points_used))


def _search_attack(world: World, **search: Any) -> AttackConfig:
    body = {
        "threshold_kind": "attack_success_rate",
        "threshold": 0.3,
        "lo": 1,
        "hi": 5,
        "tol": 0.5,
        "coarse_n": 3,
        "subset_size": SUBSET,
        "bootstrap_samples": 30,
        **search,
    }
    return AttackConfig.model_validate(
        {
            "attack_spec_id": str(world.fog.id),
            "spec_sha256": world.fog.spec_sha256,
            "mode": "search",
            "search": body,
            "seed": 7,
        }
    )


def _grid_attack(world: World) -> AttackConfig:
    return AttackConfig.model_validate(
        {
            "attack_spec_id": str(world.contrast.id),
            "spec_sha256": world.contrast.spec_sha256,
            "mode": "grid",
            "grid": {"levels": [3]},
            "seed": 0,
        }
    )


def _bundle(
    world: World,
    attacks: list[AttackConfig],
    runs: list[BundleRun],
    search_results: list[SearchResult] | None = None,
) -> Any:
    runner = world.runner_cfg
    return SimpleNamespace(
        experiment_id=EXPERIMENT,
        model_card=runner.card,
        slice=runner.slice,
        class_mapping=runner.mapping,
        inference_params=runner.params,
        config=SimpleNamespace(attacks=attacks),
        attack_specs=[world.fog, world.contrast],
        runs=runs,
        search_results=search_results or [],
        failure_cases_per_run=2,
        limit=SimpleNamespace(kind="time", value=Decimal(7200), used=Decimal(0)),
    )


def _runner(world: World, api: FakeApi, monkeypatch: pytest.MonkeyPatch) -> JobRunner:
    runner = JobRunner(
        cast(Any, api), cast(Any, SimpleNamespace(store=world.store)), "cpu", url_http=api.http()
    )
    runner._estimators[world.runner_cfg.card.weights_sha256] = world.estimator
    monkeypatch.setattr(job_module, "build_perturbation", lambda spec, est: FakePerturbation(spec))
    monkeypatch.setattr(runner, "calibrate_bundle", lambda bundle, loader, force=False: {})
    monkeypatch.setattr(
        runner,
        "_environment",
        lambda bundle: Environment(
            compute_target_id=None, gpu_model=None, cuda_version=None, driver_version=None
        ),
    )
    return runner


def _run(world: World, api: FakeApi, runner: JobRunner, bundle: Any) -> None:
    runner._run_bundle(LEASE, bundle, cast(Any, world.runner_cfg.loader), DirectiveBox())


def _grid_run(world: World) -> BundleRun:
    return BundleRun(
        run_id=uuid5(NS, "grid/contrast/3"),
        attack_spec_id=world.contrast.id,
        level=3,
        seed=0,
        status=RunStatus.QUEUED,
        images_done=0,
        images_total=3,
        checkpoint=None,
    )


# ---------------------------------------------------------------- test


def test_grid_first_then_search_with_runs_per_point(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = FakeApi(attack=_search_attack(world))
    runner = _runner(world, api, monkeypatch)
    grid = _grid_run(world)
    _run(world, api, runner, _bundle(world, [_grid_attack(world), api.attack], [grid]))

    # Quét lưới chạy trước mọi run tìm ngưỡng.
    first_create = next(i for i, (kind, _) in enumerate(api.events) if kind == "create")
    assert api.events.index(("complete", grid.run_id)) < first_create

    final = api.reports[-1]
    assert final.stage == SearchStage.DONE and final.status is not None
    assert final.status != SearchStatus.FAILED, final.message
    assert final.points_used == len(api.created) <= final.max_points
    assert {r.scope for r in api.created} == {EvalScope.SUBSET, EvalScope.FULL}
    # Gãy giữa severity 2 và 3 trên cả tập con và toàn slice.
    assert (final.status, final.bracket) == (SearchStatus.FOUND, (2.0, 3.0))
    # SearchResult tạm thời sau mỗi điểm.
    assert [r.points_used for r in api.reports[:-1]] == list(range(1, len(api.created)))

    subset_ids = select_subset(world.runner_cfg.slice.image_ids, 7, SUBSET)
    for run in api.created:
        completion = api.completions[run.run_id]
        result = completion.run_result
        point = final.trajectory[run.search_order or 0]
        assert (point.run_id, point.level, point.scope) == (run.run_id, run.level, run.scope)
        assert (result.scope, result.search_order) == (run.scope, run.search_order)
        inputs = api.starts[run.run_id]
        if run.scope == EvalScope.SUBSET:
            assert result.progress.images_total == SUBSET
            assert inputs.eval_image_ids_sha256 == eval_image_ids_sha256(subset_ids)
        else:
            assert result.progress.images_total == 3
            assert inputs.eval_image_ids_sha256 is None
        # Prediction theo ảnh đã upload, đọc lại được (plan task 13a).
        assert result.predictions_key == f"runs/{run.run_id}/predictions.json"
        predictions = load_run_predictions(api.objects[result.predictions_key], run.run_id)
        expected = (
            set(subset_ids)
            if run.scope == EvalScope.SUBSET
            else set(world.runner_cfg.slice.image_ids)
        )
        assert set(predictions) == expected
        assert result.metrics is not None and result.metrics.per_class is not None

    # Run quét lưới cũng có prediction; fingerprint toàn slice không có eval_image_ids_sha256.
    grid_result = api.completions[grid.run_id].run_result
    assert grid_result.predictions_key is not None and grid_result.search_order is None
    assert api.starts[grid.run_id].eval_image_ids_sha256 is None

    full = [p for p in final.trajectory if p.scope == EvalScope.FULL and not p.synthetic]
    assert full and all(p.drop_ci is not None for p in full)


def test_resume_continues_from_interim_result(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    straight = FakeApi(attack=_search_attack(world))
    _run(
        world,
        straight,
        _runner(world, straight, monkeypatch),
        _bundle(world, [straight.attack], []),
    )
    expected = straight.reports[-1]
    cut = 3
    previous = straight.reports[cut - 1]
    done = [
        r.model_copy(
            update={
                "status": RunStatus.COMPLETED,
                "images_done": r.images_total,
                "metrics": straight.completions[r.run_id].run_result.metrics,
            }
        )
        for r in straight.created[:cut]
    ]
    pending = straight.created[cut]  # đã tạo, chưa chạy
    resumed = FakeApi(attack=straight.attack)
    runner = _runner(world, resumed, monkeypatch)
    _run(world, resumed, runner, _bundle(world, [straight.attack], [*done, pending], [previous]))
    final = resumed.reports[-1]
    assert (final.status, final.bracket) == (expected.status, expected.bracket)
    assert [(p.level, p.scope, p.drop) for p in final.trajectory] == [
        (p.level, p.scope, p.drop) for p in expected.trajectory
    ]
    assert resumed.events[0] == ("start", pending.run_id)  # chạy run đã tạo, không tạo lại
    assert not {r.run_id for r in done} & set(resumed.starts)
    assert len(resumed.created) == len(straight.created) - cut - 1


def test_cancel_during_search_stops_with_stopped_limit(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = FakeApi(attack=_search_attack(world), cancel_after_progress=3)
    runner = _runner(world, api, monkeypatch)
    _run(world, api, runner, _bundle(world, [api.attack], []))
    final = api.reports[-1]
    assert final.status == SearchStatus.STOPPED_LIMIT
    cancelled = [c for c in api.completions.values() if c.run_result.status == RunStatus.CANCELLED]
    assert len(cancelled) == 1
    assert final.points_used == len(api.created) - 1


def test_failed_point_ends_search_failed(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    api = FakeApi(attack=_search_attack(world))
    runner = _runner(world, api, monkeypatch)
    calls = {"n": 0}
    original: Callable[[np.ndarray, int], list[Prediction]] = world.estimator.predict

    def broken(images: np.ndarray, batch_size: int) -> list[Prediction]:
        clean = list(world.estimator.clean.values())
        attacked = any(min(float(np.abs(i - c).mean()) for c in clean) > 1e-6 for i in images)
        if attacked:  # chỉ đếm lần predict ảnh đã biến đổi (ảnh sạch có thể đã trong cache)
            calls["n"] += 1
            if calls["n"] > 2:
                raise RuntimeError("estimator hỏng")
        return original(images, batch_size)

    monkeypatch.setattr(world.estimator, "predict", broken)
    _run(world, api, runner, _bundle(world, [api.attack], []))
    final = api.reports[-1]
    assert final.status == SearchStatus.FAILED
    assert final.message is not None and "estimator hỏng" in final.message


def test_predictions_file_is_json(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    api = FakeApi(attack=_search_attack(world, bootstrap_samples=0))
    runner = _runner(world, api, monkeypatch)
    _run(world, api, runner, _bundle(world, [api.attack], []))
    key = f"runs/{api.created[0].run_id}/predictions.json"
    assert json.loads(api.objects[key])["key"] == key
    assert api.reports[-1].confidence_interval is None
