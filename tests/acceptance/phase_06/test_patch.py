"""validation.md Phase 6, Patch (`test_patch.py`). Hình học và train trên YOLOv8n thật (CPU); luồng
train → đăng ký → dùng lại → chạy tiếp qua API và worker thật với spec `max_iter = 4`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import numpy as np
import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from advertest_contracts.models import PatchArtifact, ProgressReport, compute_patch_key
from advertest_worker import patch as worker_patch
from advertest_worker.client import WorkerClient
from attacks.patch.adapter import PatchPerturbation
from attacks.patch.artifact import build_artifact
from attacks.patch.geometry import Region, image_regions
from attacks.patch.training import PatchTrainer
from backend.app.db import models as m
from ml_core.models.estimator import build_estimator
from ml_core.models.wrapper import (
    DEFAULT_INFERENCE_PARAMS,
    UltralyticsDetector,
    load_detection_model,
)

from .conftest import (
    PATCH_MAX_ITER,
    WEIGHTS,
    Kitti,
    ProgressLog,
    World6,
    _patch_spec,
    error,
    grid_attack,
    ok,
    patch_attack,
    post,
    profile,
)


class Crash(BaseException):
    """Worker chết đột ngột (kill -9): không gửi gì thêm."""


# ---------------------------------------------------------------- hình học và train (không DB)


@pytest.fixture(scope="module")
def estimator() -> Any:
    return build_estimator(
        UltralyticsDetector(load_detection_model(WEIGHTS), DEFAULT_INFERENCE_PARAMS)
    )


@pytest.mark.parametrize("area_ratio", [0.1, 0.25])
def test_patch_area_and_inside_real_region(kitti: Kitti, estimator: Any, area_ratio: float) -> None:
    spec = _patch_spec()
    images, targets, mask = kitti.subset(list(range(len(kitti.targets))))
    trainer = PatchTrainer(spec, estimator, area_ratio=area_ratio, seed=0)
    geometry = trainer.geometry(images, mask)
    region = image_regions(mask, len(images), *images.shape[2:])[0]
    assert abs(geometry.side**2 - area_ratio * region.area) <= 0.01 * area_ratio * region.area
    inside = Region(geometry.top, geometry.top + geometry.side,
                    geometry.left, geometry.left + geometry.side)  # fmt: skip
    assert region.top <= inside.top and inside.bottom <= region.bottom
    assert region.left <= inside.left and inside.right <= region.right

    # Khi đánh giá: patch dán ở tâm vùng ảnh thật của từng ảnh, nằm trọn trong vùng đó.
    patch = np.full((3, geometry.side, geometry.side), 0.5, dtype=np.float32)
    out = PatchPerturbation(spec, patch, area_ratio=area_ratio).apply(
        images, targets, area_ratio, 0, mask
    )
    for i in range(len(images)):
        rows, cols = np.nonzero(np.any(out[i] != images[i], axis=0))
        assert mask[i, 0, rows, cols].all()  # mọi điểm đổi đều trong vùng ảnh thật
        assert rows.max() - rows.min() + 1 <= geometry.side
        assert cols.max() - cols.min() + 1 <= geometry.side


def test_training_improves_objective_and_builds_valid_artifact(
    kitti: Kitti, estimator: Any
) -> None:
    spec = _patch_spec()
    images, _, mask = kitti.subset(list(range(len(kitti.targets))))
    trainer = PatchTrainer(spec, estimator, area_ratio=0.1, seed=0)
    state = trainer.train(images, mask)
    history = state.objective_history
    assert state.iterations_done == PATCH_MAX_ITER and len(history) == PATCH_MAX_ITER
    # Attack untargeted làm loss của detector trên ảnh đã dán patch tăng (requirements.md Phase 6).
    assert history[-1] > history[0], history
    artifact, files = build_artifact(
        spec, state, weights_sha256="a" * 64, training_slice_sha256="b" * 64,
        area_ratio=0.1, seed=0, created_at=datetime(2026, 10, 1, tzinfo=UTC),
    )  # fmt: skip
    assert PatchArtifact.model_validate(artifact.model_dump()) == artifact
    assert artifact.iterations == PATCH_MAX_ITER and artifact.patch_sha256 == files.sha256


# ---------------------------------------------------------------- qua API và worker (DB)


def _setup(
    api: Any, world: World6, attacks: list[dict[str, Any]], **changes: Any
) -> tuple[Any, Any, str]:
    target = api.target()
    profile(api, target, {world.patch.id: 0.05}, sec_per_image_iteration={world.patch.id: 0.2})
    api.profile(target, sec=0.05, batch=3, attacks=["fgsm"])
    _, _, client = api.user("engineer")
    created = ok(post(client, "/experiments", api.body(target, attacks, **changes))).json()
    return target, client, created["id"]


def _runs(client: Any, experiment_id: str) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = client.get(f"/experiments/{experiment_id}/runs").json()
    return runs


def _patch_row(owner_engine: Engine, key: str) -> m.Patch | None:
    with Session(owner_engine) as session:
        return session.get(m.Patch, key)


def _key(owner_engine: Engine, world: World6, area_ratio: float) -> str:
    with Session(owner_engine) as session:
        training = session.get(m.Slice, UUID(world.training_slice_id))
        model = session.get(m.ModelVersion, UUID(world.base.model_id))
        assert training is not None and training.slice_sha256 and model is not None
        return compute_patch_key(
            spec_sha256=world.patch.spec_sha256, weights_sha256=model.weights_sha256,
            training_slice_sha256=training.slice_sha256, area_ratio=area_ratio, seed=0,
        )  # fmt: skip


@pytest.mark.db
def test_training_slice_rules(api: Any, world: World6, owner_engine: Engine) -> None:
    """Slice huấn luyện giao slice đánh giá, khác dataset version, hơn 50 ảnh, hoặc thiếu → 422."""
    with Session(owner_engine) as session, session.begin():
        big = m.Slice(
            dataset_version_id=UUID(world.dataset_version_id), name=f"big-{uuid.uuid4().hex[:6]}",
            filter={}, seed=0, image_ids=[f"x{i}" for i in range(51)],
            image_ids_sha256=uuid.uuid4().hex * 2, slice_sha256=uuid.uuid4().hex * 2,
        )  # fmt: skip
        session.add(big)
        session.flush()
        big_id = str(big.id)
    target = api.target()
    _, _, client = api.user("engineer")
    path = ["attacks.0.training_slice_id"]
    for training in (world.overlap_slice_id, world.other_version_slice_id, big_id):
        body = api.body(target, [patch_attack(world, [0.1], training=training)])
        status, code, fields = error(post(client, "/experiments", body))
        assert (status, code, set(fields)) == (422, "invalid_request", set(path)), training
    missing = {k: v for k, v in patch_attack(world, [0.1]).items() if k != "training_slice_id"}
    assert error(post(client, "/experiments", api.body(target, [missing]))) == (
        422, "invalid_request", path,
    )  # fmt: skip


@pytest.mark.db
def test_train_register_reuse_and_fingerprint(
    api: Any,
    world: World6,
    owner_engine: Engine,
    progress_log: ProgressLog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attacks = [patch_attack(world, [0.1]), grid_attack("fgsm", [4])]
    target, client, first_id = _setup(api, world, attacks)
    api.work(target, first_id)
    runs = {r["attack_spec"]["name"]: r for r in _runs(client, first_id)}
    patch_run, fgsm_run = runs["adv_patch"], runs["fgsm"]
    assert patch_run["status"] == "completed" and patch_run["metrics"], patch_run

    # Tiến độ: giai đoạn train (đủ max_iter vòng) rồi đánh giá.
    phases = progress_log.phases(UUID(patch_run["run_id"]))
    assert phases[0] == "training" and phases[-1] == "evaluating"
    assert phases == sorted(phases, key=lambda p: p != "training")  # train xong mới đánh giá
    iterations = [
        r.iterations_done for rid, r in progress_log.reports
        if rid == UUID(patch_run["run_id"]) and r.phase == "training"
    ]  # fmt: skip
    assert iterations == list(range(1, PATCH_MAX_ITER + 1))

    key = _key(owner_engine, world, 0.1)
    row = _patch_row(owner_engine, key)
    assert row is not None and row.artifact is not None and row.checkpoint_key is None
    artifact = PatchArtifact.model_validate(row.artifact)
    assert artifact.iterations == PATCH_MAX_ITER

    # fingerprint_inputs.patch_key: có với run patch, null với run khác.
    manifest = client.get(f"/runs/{patch_run['run_id']}/manifest").json()
    assert manifest["fingerprint_inputs"]["patch_key"] == key
    other = client.get(f"/runs/{fgsm_run['run_id']}/manifest").json()
    assert other["fingerprint_inputs"].get("patch_key") is None

    # Experiment thứ hai cùng khóa patch: không train lại, dùng đúng patch đã đăng ký.
    def no_training(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("Không được train lại patch đã có")

    monkeypatch.setattr(worker_patch.PatchTrainer, "train", no_training)
    monkeypatch.setenv(
        "GIT_COMMIT", (uuid.uuid4().hex + uuid.uuid4().hex)[:40]
    )  # không trúng cache
    target2, client2, second_id = _setup(api, world, [patch_attack(world, [0.1])])
    api.work(target2, second_id)
    (again,) = _runs(client2, second_id)
    assert again["status"] == "completed", again
    assert "training" not in progress_log.phases(UUID(again["run_id"]))
    reused = _patch_row(owner_engine, key)
    assert reused is not None and reused.artifact is not None
    assert PatchArtifact.model_validate(reused.artifact).patch_sha256 == artifact.patch_sha256
    assert (
        client2.get(f"/runs/{again['run_id']}/manifest").json()["fingerprint_inputs"]["patch_key"]
        == key
    )


@pytest.mark.db
def test_interrupted_training_resumes_from_checkpoint(
    api: Any, world: World6, owner_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = WorkerClient.progress
    reports: list[tuple[int, int | None]] = []  # (lần chạy worker, vòng)
    attempt = [1]

    def crash_at_two(self: WorkerClient, run_id: UUID, body: ProgressReport) -> Any:
        directive = original(self, run_id, body)
        if body.phase == "training":
            reports.append((attempt[0], body.iterations_done))
            if attempt[0] == 1 and body.iterations_done == 2:
                raise Crash
        return directive

    monkeypatch.setattr(WorkerClient, "progress", crash_at_two)
    # Area ratio riêng: khóa patch chưa có (không dùng lại patch của test khác).
    target, client, experiment_id = _setup(api, world, [patch_attack(world, [0.2])])
    with pytest.raises(Crash):
        api.work(target, experiment_id)
    key = _key(owner_engine, world, 0.2)
    row = _patch_row(owner_engine, key)
    assert row is not None and row.artifact is None and row.checkpoint_key  # checkpoint còn

    api.clock.advance(61)  # lease hết hạn
    attempt[0] = 2
    api.work(target, experiment_id)  # worker mới (cache mới)
    (run,) = _runs(client, experiment_id)
    assert run["status"] == "completed", run
    assert [i for a, i in reports if a == 1] == [1, 2]
    assert [i for a, i in reports if a == 2] == list(range(3, PATCH_MAX_ITER + 1))
    done = _patch_row(owner_engine, key)
    assert done is not None and done.artifact is not None
    assert PatchArtifact.model_validate(done.artifact).iterations == PATCH_MAX_ITER


@pytest.mark.db
def test_limit_during_training_stops_run_and_counts_training_time(
    api: Any, world: World6, owner_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mỗi vòng train báo như 100 giây; giới hạn 150 giây: chạm giới hạn giữa lúc train."""
    original = WorkerClient.progress

    def slow_training(self: WorkerClient, run_id: UUID, body: ProgressReport) -> Any:
        if body.phase == "training":
            body = body.model_copy(update={"processing_seconds_delta": 100.0})
        return original(self, run_id, body)

    monkeypatch.setattr(WorkerClient, "progress", slow_training)
    target, client, experiment_id = _setup(
        api, world, [patch_attack(world, [0.15])], limit={"kind": "time", "value": "150"}
    )
    api.work(target, experiment_id)
    (run,) = _runs(client, experiment_id)
    assert run["status"] == "stopped_limit", run
    detail = client.get(f"/experiments/{experiment_id}").json()
    assert Decimal(str(detail["processing_seconds_used"])) >= Decimal(200)
    row = _patch_row(owner_engine, _key(owner_engine, world, 0.15))
    assert (
        row is not None and row.artifact is None and row.checkpoint_key
    )  # train dở, giữ checkpoint
