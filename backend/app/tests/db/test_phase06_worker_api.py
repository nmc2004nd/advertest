"""API nội bộ Phase 6 (plan task 26, 26a): bundle có patch và slice huấn luyện, tiến độ train,
URL cho thư mục patch, đăng ký patch, bỏ run do dừng sớm, lưu làm mờ của failure case."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from advertest_contracts.enums import DisplayMode, LimitKind, RunStatus
from advertest_contracts.models import (
    CaseAnonymization,
    ExperimentConfig,
    PatchArtifact,
    WorkerJobBundle,
    compute_failure_case_id,
    compute_patch_key,
)
from attacks.registry import get_spec, load_catalog
from backend.app.db import models as m
from backend.app.services import (
    artifacts,
    compute_targets,
    experiment_views,
    experiments,
    registry,
)
from backend.app.storage import Buckets
from ml_core.data.slice import create_slice, save_slice

from .test_worker_api import _auth, _error, _lease, client, clock
from .test_worker_services import FakeClock, World, _completion, _start_request, world

pytestmark = pytest.mark.db
__all__ = ["client", "clock", "world"]
DEV_OPEN = UUID("2edcdef5-0d3a-5d5f-98ac-b02637fa6718")


@dataclass(frozen=True)
class Setup:
    token: str
    experiment_id: UUID
    training_slice: UUID
    training_sha: str
    training_ids: list[str]


@pytest.fixture(scope="module")
def training(world: World, app_engine: Engine, buckets: Buckets) -> tuple[UUID, str, list[str]]:
    """Slice huấn luyện 1 ảnh (fixture chỉ có 3 ảnh hợp lệ) không giao slice đánh giá, đăng ký
    qua import-local."""
    local = world.local
    spec = create_slice(local.manifest, size=1, seed=5, exclude=local.slice.image_ids)
    save_slice(local.store, spec)
    with Session(app_engine) as session, session.begin():
        admin = session.get_one(m.User, world.admin_id)
        registry.import_local(session, local.store, buckets, actor=admin)
    return spec.id, spec.slice_sha256, list(spec.image_ids)


def _setup(
    app_engine: Engine, world: World, clock: FakeClock, training: tuple[UUID, str, list[str]]
) -> Setup:
    slice_id, slice_sha, ids = training
    catalog = load_catalog()
    fgsm = get_spec(catalog, name="fgsm")
    patch = get_spec(catalog, name="adv_patch")
    attacks: list[dict[str, Any]] = [
        {"attack_spec_id": str(fgsm.id), "spec_sha256": fgsm.spec_sha256, "mode": "grid",
         "grid": {"levels": [2, 4]}, "seed": 0},
        {"attack_spec_id": str(patch.id), "spec_sha256": patch.spec_sha256, "mode": "grid",
         "grid": {"levels": [0.1]}, "seed": 0, "training_slice_id": str(slice_id)},
    ]  # fmt: skip
    with Session(app_engine) as session, session.begin():
        admin = session.get_one(m.User, world.admin_id)
        issued = compute_targets.create(session, actor=admin, name=f"p6-{uuid.uuid4().hex[:8]}")
        config = ExperimentConfig.model_validate(
            {
                "protocol_id": str(DEV_OPEN),
                "model_version_id": str(world.local.card.id),
                "slice_id": str(world.local.slice.id),
                "class_mapping_id": str(world.local.mapping.id),
                "compute_target_id": str(issued.target.id),
                "attacks": attacks,
                "limit": {"kind": LimitKind.TIME, "value": "7200"},
            }
        )
        slice_row = session.get_one(m.Slice, world.local.slice.id)
        experiment = experiments.create_experiment(
            session, actor=admin, config=config, slice_row=slice_row, specs=[fgsm, patch],
            clock=clock,
        )  # fmt: skip
        return Setup(issued.token, experiment.id, slice_id, slice_sha, ids)


def _bundle(client: TestClient, setup: Setup) -> WorkerJobBundle:
    response = client.get(
        f"/internal/worker/experiments/{setup.experiment_id}/bundle", headers=_auth(setup.token)
    )
    assert response.status_code == 200, response.text
    return WorkerJobBundle.model_validate(response.json())


def _patch_run(bundle: WorkerJobBundle) -> Any:
    return next(r for r in bundle.runs if r.patch_key is not None)


def _key(world: World, setup: Setup) -> str:
    patch = get_spec(load_catalog(), name="adv_patch")
    return compute_patch_key(
        spec_sha256=patch.spec_sha256,
        weights_sha256=world.local.card.weights_sha256,
        training_slice_sha256=setup.training_sha,
        area_ratio=0.1,
        seed=0,
    )


def test_bundle_has_training_slice_and_patch(
    client: TestClient, app_engine: Engine, world: World, clock: FakeClock, training: Any
) -> None:
    setup = _setup(app_engine, world, clock, training)
    _lease(client, setup.token)
    bundle = _bundle(client, setup)
    assert [s.id for s in bundle.training_slices] == [setup.training_slice]
    assert set(setup.training_ids) <= set(bundle.downloads.images)
    run = _patch_run(bundle)
    assert run.patch_key == _key(world, setup)
    (patch,) = bundle.patches
    assert (patch.key, patch.area_ratio, patch.artifact, patch.checkpoint_key) == (
        run.patch_key, 0.1, None, None,
    )  # fmt: skip
    assert all(r.metrics is None for r in bundle.runs)


def test_training_progress_urls_and_registration(
    client: TestClient,
    app_engine: Engine,
    world: World,
    clock: FakeClock,
    training: Any,
    buckets: Buckets,
) -> None:
    setup = _setup(app_engine, world, clock, training)
    lease = _lease(client, setup.token)
    run = _patch_run(_bundle(client, setup))
    key = run.patch_key
    base = f"/internal/worker/runs/{run.run_id}"
    auth = _auth(setup.token)
    started = client.post(
        f"{base}/start", json=_start_request(lease.lease_id).model_dump(mode="json"), headers=auth
    )
    assert started.status_code == 200

    def url(object_key: str) -> httpx.Response:
        body = {"lease_id": str(lease.lease_id), "key": object_key, "method": "PUT"}
        response: httpx.Response = client.post(f"{base}/artifact-url", json=body, headers=auth)
        return response

    assert url(f"patches/{key}/checkpoints/0.npz").status_code == 200
    other = url(f"patches/{'e' * 64}/x.npy")
    assert other.status_code == 403 and _error(other) == "forbidden"

    def progress(checkpoint: str, done: int) -> httpx.Response:
        report = {
            "lease_id": str(lease.lease_id), "images_done": 0, "batch_index": 0,
            "checkpoint_key": checkpoint, "processing_seconds_delta": 3.0, "phase": "training",
            "iterations_done": done, "iterations_total": 200,
        }  # fmt: skip
        response: httpx.Response = client.post(f"{base}/progress", json=report, headers=auth)
        return response

    assert progress(f"runs/{run.run_id}/c.npz", 1).status_code == 422  # phải trong patches/<key>/
    checkpoint = f"patches/{key}/checkpoints/50.npz"
    assert progress(checkpoint, 50).status_code == 200
    with Session(app_engine) as session:
        row = session.get_one(m.Run, run.run_id)
        assert (row.phase, row.iterations_done, row.iterations_total) == ("training", 50, 200)
        assert row.gpu_seconds == pytest.approx(3.0)
    assert _bundle(client, setup).patches[0].checkpoint_key == checkpoint

    artifact = _artifact(world, setup, key, sha="1" * 64)
    missing = client.post(
        f"{base}/patch",
        json={"lease_id": str(lease.lease_id), "artifact": artifact.model_dump(mode="json")},
        headers=auth,
    )
    assert missing.status_code == 422  # file chưa có trong MinIO
    for object_key in (artifact.npy_key, artifact.png_key):
        buckets.artifacts.put(object_key, b"x")
    first = client.post(
        f"{base}/patch",
        json={"lease_id": str(lease.lease_id), "artifact": artifact.model_dump(mode="json")},
        headers=auth,
    )
    assert first.status_code == 200 and PatchArtifact.model_validate(first.json()) == artifact
    other_artifact = _artifact(world, setup, key, sha="2" * 64)
    for object_key in (other_artifact.npy_key, other_artifact.png_key):
        buckets.artifacts.put(object_key, b"y")
    second = client.post(
        f"{base}/patch",
        json={"lease_id": str(lease.lease_id), "artifact": other_artifact.model_dump(mode="json")},
        headers=auth,
    )
    assert PatchArtifact.model_validate(second.json()) == artifact  # giữ bản đăng ký trước
    patch = _bundle(client, setup).patches[0]
    assert patch.artifact == artifact and patch.checkpoint_key is None


def _artifact(world: World, setup: Setup, key: str, *, sha: str) -> PatchArtifact:
    patch = get_spec(load_catalog(), name="adv_patch")
    return PatchArtifact(
        key=key,
        spec_sha256=patch.spec_sha256,
        weights_sha256=world.local.card.weights_sha256,
        training_slice_sha256=setup.training_sha,
        area_ratio=0.1,
        seed=0,
        side_px=8,
        patch_sha256=sha,
        png_key=f"patches/{key}/{sha}.png",
        npy_key=f"patches/{key}/{sha}.npy",
        iterations=2,
        training_seconds=1.0,
        objective_history=[0.1, 0.2],
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
    )


def _metrics(attacked: float) -> dict[str, Any]:
    return {
        "clean": {"map50": 0.5, "map50_95": 0.3},
        "attacked": {"map50": attacked, "map50_95": attacked / 2},
        "relative_drop": (0.5 - attacked) / 0.5,
        "absolute_drop": 0.5 - attacked,
        "attack_success_rate": None,
        "partial": False,
    }


def test_skip_early_stop(
    client: TestClient, app_engine: Engine, world: World, clock: FakeClock, training: Any
) -> None:
    setup = _setup(app_engine, world, clock, training)
    lease = _lease(client, setup.token)
    bundle = _bundle(client, setup)
    low, high = sorted((r for r in bundle.runs if r.patch_key is None), key=lambda r: r.level)
    auth = _auth(setup.token)

    def skip(trigger: UUID) -> httpx.Response:
        body = {
            "lease_id": str(lease.lease_id), "code": "early_stop",
            "trigger_run_id": str(trigger), "message": "Bỏ qua: model đã sụp ở level 2",
        }  # fmt: skip
        response: httpx.Response = client.post(
            f"/internal/worker/runs/{high.run_id}/skip", json=body, headers=auth
        )
        return response

    with Session(app_engine) as session, session.begin():
        row = session.get_one(m.Run, low.run_id)
        row.status, row.metrics = RunStatus.COMPLETED, _metrics(0.3)  # chưa sụp
    assert skip(low.run_id).status_code == 422
    with Session(app_engine) as session, session.begin():
        session.get_one(m.Run, low.run_id).metrics = _metrics(0.01)
    assert skip(high.run_id).status_code == 422  # tự kích hoạt chính nó
    assert skip(low.run_id).status_code == 204
    with Session(app_engine) as session:
        row = session.get_one(m.Run, high.run_id)
        assert row.status == RunStatus.SKIPPED and row.finished_at is not None
        assert row.status_reason == {
            "code": "early_stop",
            "message": "Bỏ qua: model đã sụp ở level 2",
            "trigger_run_id": str(low.run_id),
        }
    again = skip(low.run_id)
    assert again.status_code == 409 and _error(again) == "conflict"
    assert _bundle(client, setup).runs[0].metrics is not None  # metric trong bundle


def test_complete_stores_anonymization_and_kind(
    client: TestClient,
    app_engine: Engine,
    world: World,
    clock: FakeClock,
    training: Any,
    buckets: Buckets,
) -> None:
    setup = _setup(app_engine, world, clock, training)
    lease = _lease(client, setup.token)
    run = next(r for r in _bundle(client, setup).runs if r.patch_key is None)
    auth = _auth(setup.token)
    base = f"/internal/worker/runs/{run.run_id}"
    client.post(
        f"{base}/start", json=_start_request(lease.lease_id).model_dump(mode="json"), headers=auth
    ).raise_for_status()
    with Session(app_engine) as session:
        current = session.get_one(m.Run, run.run_id)
    completion = _completion(current, lease.lease_id, buckets)
    anonymization = CaseAnonymization(applied=True, method="rule_v1", version=1, regions_count=3)
    cases = [
        case.model_copy(update={"anonymization": anonymization, "perturbation_kind": "difference"})
        for case in completion.failure_cases
    ]
    body = completion.model_copy(update={"failure_cases": cases}).model_dump(mode="json")
    done = client.post(f"{base}/complete", json=body, headers=auth)
    assert done.status_code == 204, done.text
    with Session(app_engine) as session:
        stored = session.get_one(m.FailureCase, cases[0].id)
        assert stored.anonymization == anonymization.model_dump(mode="json")
        assert stored.perturbation_kind == "difference"


def test_user_views_ranking_phase_and_display_mode(
    client: TestClient, app_engine: Engine, world: World, clock: FakeClock, training: Any
) -> None:
    """Plan task 27, 28: bảng xếp hạng, giai đoạn của run, `display_mode` theo từng case."""
    setup = _setup(app_engine, world, clock, training)
    _lease(client, setup.token)
    bundle = _bundle(client, setup)
    fgsm = sorted((r for r in bundle.runs if r.patch_key is None), key=lambda r: r.level)
    patch_run = _patch_run(bundle)
    with Session(app_engine) as session, session.begin():
        for run, attacked in zip(fgsm, (0.4, 0.1), strict=True):
            row = session.get_one(m.Run, run.run_id)
            row.status, row.metrics, row.fingerprint = (
                RunStatus.COMPLETED, _metrics(attacked), uuid.uuid4().hex * 2,
            )  # fmt: skip
            row.manifest_uri = f"s3://artifacts/runs/{run.run_id}/manifest.json"
        running = session.get_one(m.Run, patch_run.run_id)
        running.status, running.fingerprint = RunStatus.RUNNING, uuid.uuid4().hex * 2
        running.phase, running.iterations_done, running.iterations_total = "training", 7, 200
        session.flush()
        detail = experiment_views.detail(session, setup.experiment_id)
        names = [entry.name for entry in detail.attack_ranking]
        assert names == ["fgsm", "adv_patch"]
        fgsm_entry = detail.attack_ranking[0]
        assert fgsm_entry.levels_evaluated == 2 and fgsm_entry.auc_drop is not None
        assert detail.attack_ranking[1].auc_drop is None  # chưa có level nào có metric
        view = experiment_views.get_run(session, patch_run.run_id)
        assert view.phase == "training" and view.training is not None
        assert (view.training.done, view.training.total) == (7, 200)
        assert experiment_views.get_run(session, fgsm[0].run_id).phase is None

        base = {
            "run_id": fgsm[0].run_id, "severity_score": 1.0, "fingerprint": "a" * 64,
            "lost_objects": 1, "new_false_positives": 0,
            "detections": {"ground_truth": [], "clean": [], "attacked": [], "ignore_regions": []},
            "artifacts": {"clean_png": "runs/x/c.png", "adversarial_png": "runs/x/a.png",
                          "perturbation_png": "runs/x/p.png"},
        }  # fmt: skip
        blurred = m.FailureCase(
            id=compute_failure_case_id("a" * 64, fgsm[0].run_id, "b"),
            image_id="b", rank=0, perturbation_kind="difference",
            anonymization={"applied": True, "method": "rule_v1", "version": 1,
                           "regions_count": 2},
            **base,
        )  # fmt: skip
        old = m.FailureCase(
            id=compute_failure_case_id("a" * 64, fgsm[0].run_id, "o"), image_id="o", rank=1,
            **base,
        )  # fmt: skip
        session.add_all([blurred, old])
        session.flush()
        now = datetime(2026, 10, 1, tzinfo=UTC)
        assert artifacts.case_mode(blurred, DisplayMode.HIDDEN_UNANONYMIZED) == DisplayMode.NORMAL
        assert (
            artifacts.case_mode(old, DisplayMode.HIDDEN_UNANONYMIZED)
            == DisplayMode.HIDDEN_UNANONYMIZED
        )
        assert artifacts._view(blurred, DisplayMode.HIDDEN_UNANONYMIZED, True, now).urls.clean
        session.rollback()
