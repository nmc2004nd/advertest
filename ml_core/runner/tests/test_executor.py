"""`RunExecutor` theo batch: checkpoint, chạy tiếp, ứng viên failure case (Phase 3, Group 1).

Dùng dữ liệu tổng hợp của `test_run.py` (KITTI 3 ảnh) với attack FGSM thật trên YOLOv8n ngẫu
nhiên. Model ngẫu nhiên không detect được gì ở `operating_conf`, nên prediction dùng estimator
giả nhưng tất định: ảnh sạch detect đúng mọi ground truth; ảnh sau tấn công mất object và có
detection sai, số lượng tính từ nội dung ảnh (không phụ thuộc cách chia batch).
"""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np
import pytest
from PIL import Image

from attacks.art_adapter import build_perturbation
from ml_core.cli.evaluate import ground_truth
from ml_core.metrics.filters import Prediction
from ml_core.runner.candidates import CANDIDATE_FILES, StoreCandidates
from ml_core.runner.executor import (
    CheckpointMismatchError,
    FinalizedRun,
    RunContext,
    RunExecutor,
    build_context,
    linf_eps,
)
from ml_core.runner.images import thumbnail_webp
from ml_core.runner.run import Runner
from ml_core.runner.tests.test_run import Base, _attack, _build, _config
from ml_core.store import DeletableStore, KeyNotFoundError, LocalStore

FP = "a" * 64
RUN_ID = UUID("11111111-2222-5333-8444-555555555555")


class MemStore:
    """Store xóa được, trong bộ nhớ (vai trò của MinIO / presigned URL trong test)."""

    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> None:
        self.data[key] = data

    def get(self, key: str) -> bytes:
        if key not in self.data:
            raise KeyNotFoundError(key)
        return self.data[key]

    def exists(self, key: str) -> bool:
        return key in self.data

    def delete(self, key: str) -> None:
        self.data.pop(key, None)

    def keys(self, prefix: str) -> list[str]:
        return sorted(k for k in self.data if k.startswith(prefix))


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Base:
    return _build(tmp_path_factory.mktemp("executor"), supports_gradients=True)


class FakeEstimator:
    """Sau tấn công: không còn object thật, thêm 1-4 detection sai trên nền (class car)."""

    def __init__(self, car: int) -> None:
        self.car = car

    def predict(self, images: np.ndarray, batch_size: int) -> list[Prediction]:
        preds = []
        for image in images:
            n = int(float(image.sum()) * 1000) % 4 + 1
            boxes = np.asarray([[500 + 20 * k, 10, 515 + 20 * k, 30] for k in range(n)], np.float32)
            preds.append(
                {
                    "boxes": boxes,
                    "labels": np.full(n, self.car, np.int64),
                    "scores": np.linspace(0.9, 0.5, n).astype(np.float32),
                }
            )
        return preds


def _clean_predictions(runner: Runner) -> dict[str, Prediction]:
    targets, _ = ground_truth(runner.loader)
    return {
        image_id: {
            "boxes": t["boxes"].reshape(-1, 4),
            "labels": t["labels"],
            "scores": np.full(len(t["labels"]), 0.95, np.float32),
        }
        for image_id, t in targets.items()
    }


@pytest.fixture(scope="module")
def setup(base: Base, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("executor-store") / "store"
    shutil.copytree(base.root, root)
    runner = Runner(
        LocalStore(root), _config(base, [_attack("fgsm", [8])], failure_cases_per_run=3)
    )
    context = build_context(runner.loader, _clean_predictions(runner), runner.params, 2)
    spec = runner.specs[0]
    perturbation = build_perturbation(spec, runner.estimator)
    return {
        "runner": runner,
        "estimator": FakeEstimator(runner.card.class_names.index("car")),
        "context": context,
        "perturbation": perturbation,
        "eps": linf_eps(spec, perturbation, 8.0),
    }


def _executor(setup: dict[str, Any], store: DeletableStore, **overrides: Any) -> RunExecutor:
    args: dict[str, Any] = {
        "fingerprint": FP,
        "level": 8.0,
        "seed": 0,
        "perturbation": setup["perturbation"],
        "estimator": setup["estimator"],
        "context": setup["context"],
        "candidates": StoreCandidates(store, f"runs/{RUN_ID}", setup["eps"]),
        **overrides,
    }
    return RunExecutor(**args)


def _run_all(executor: RunExecutor, setup: dict[str, Any], batch_size: int) -> None:
    for batch in executor.batches(setup["runner"].loader, batch_size):
        executor.process_batch(batch)


@pytest.fixture(scope="module")
def straight(setup: dict[str, Any]) -> tuple[FinalizedRun, MemStore]:
    """Chạy liền mạch, batch 3."""
    store = MemStore()
    executor = _executor(setup, store)
    _run_all(executor, setup, 3)
    return executor.finalize(RUN_ID), store


def test_straight_run_has_failure_cases(straight: tuple[FinalizedRun, MemStore]) -> None:
    finalized, store = straight
    assert finalized.images_done == 3 and not finalized.metrics.partial
    assert finalized.failure_cases, "fixture phải có ít nhất một failure case"
    for record in finalized.failure_cases:
        assert record.run_id == RUN_ID and record.fingerprint == FP
        artifacts = record.artifacts
        assert artifacts.clean_thumb is not None and artifacts.adversarial_thumb is not None
        for key in (
            artifacts.clean_png,
            artifacts.adversarial_png,
            artifacts.perturbation_png,
            artifacts.clean_thumb,
            artifacts.adversarial_thumb,
        ):
            assert key.startswith(f"runs/{RUN_ID}/cases/{record.id}/") and store.exists(key)
    assert store.keys(f"runs/{RUN_ID}/candidates/") == []


def test_thumbnails_are_320px_webp(straight: tuple[FinalizedRun, MemStore]) -> None:
    finalized, store = straight
    for record in finalized.failure_cases:
        for key in (record.artifacts.clean_thumb, record.artifacts.adversarial_thumb):
            assert key is not None
            image = Image.open(io.BytesIO(store.get(key)))
            assert image.format == "WEBP" and image.size == (320, 320)


def _resume(
    setup: dict[str, Any], checkpoint: dict[str, Any], store: MemStore, batch_size: int
) -> RunExecutor:
    """Chạy tiếp từ checkpoint đã qua JSON, như khi worker mới nhận lại job."""
    restored = json.loads(json.dumps(checkpoint))
    executor = RunExecutor.from_checkpoint(
        restored,
        fingerprint=FP,
        level=8.0,
        seed=0,
        perturbation=setup["perturbation"],
        estimator=setup["estimator"],
        context=setup["context"],
        candidates=StoreCandidates(store, f"runs/{RUN_ID}", setup["eps"]),
    )
    _run_all(executor, setup, batch_size)
    return executor


def test_resume_matches_straight_run(
    setup: dict[str, Any], straight: tuple[FinalizedRun, MemStore]
) -> None:
    expected, expected_store = straight
    store = MemStore()
    first = _executor(setup, store)
    first.process_batch(next(first.batches(setup["runner"].loader, 1)))
    # Gián đoạn hai lần, batch size khác lần chạy liền mạch.
    second = RunExecutor.from_checkpoint(
        json.loads(json.dumps(first.to_checkpoint())),
        fingerprint=FP,
        level=8.0,
        seed=0,
        perturbation=setup["perturbation"],
        estimator=setup["estimator"],
        context=setup["context"],
        candidates=StoreCandidates(store, f"runs/{RUN_ID}", setup["eps"]),
    )
    second.process_batch(next(second.batches(setup["runner"].loader, 1)))
    third = _resume(setup, second.to_checkpoint(), store, 2)
    finalized = third.finalize(RUN_ID)

    assert finalized.metrics == expected.metrics
    assert finalized.failure_cases == expected.failure_cases
    for record in finalized.failure_cases:
        for key in (record.artifacts.clean_png, record.artifacts.perturbation_png):
            assert store.get(key) == expected_store.get(key)
    assert store.keys(f"runs/{RUN_ID}/candidates/") == []


def test_each_image_processed_once(setup: dict[str, Any]) -> None:
    store = MemStore()
    executor = _executor(setup, store)
    batch = next(executor.batches(setup["runner"].loader, 2))
    executor.process_batch(batch)
    with pytest.raises(ValueError, match="đã xử lý"):
        executor.process_batch(batch)
    resumed = _resume(setup, executor.to_checkpoint(), store, 2)
    assert resumed.done == setup["context"].image_ids
    assert resumed.remaining_ids() == []


def test_checkpoint_has_no_image_data(setup: dict[str, Any]) -> None:
    executor = _executor(setup, MemStore())
    _run_all(executor, setup, 2)
    checkpoint = executor.to_checkpoint()
    assert set(checkpoint) == {
        "version",
        "fingerprint",
        "images_total",
        "done",
        "predictions",
        "stats",
        "top",
        "offered",
        "case_inputs",
        "processing_seconds",
    }
    size = len(json.dumps(checkpoint))
    assert size < 3 * 640 * 640  # nhỏ hơn nhiều so với một ảnh 640x640x3
    # Prediction đã lọc class đích.
    labels = {label for p in checkpoint["predictions"].values() for label in p["labels"]}
    assert labels <= set(setup["context"].target_labels)


def test_checkpoint_mismatch_rejected(setup: dict[str, Any]) -> None:
    executor = _executor(setup, MemStore())
    executor.process_batch(next(executor.batches(setup["runner"].loader, 1)))
    checkpoint = executor.to_checkpoint()
    kwargs: dict[str, Any] = {
        "level": 8.0,
        "seed": 0,
        "perturbation": setup["perturbation"],
        "estimator": None,
        "context": setup["context"],
        "candidates": StoreCandidates(MemStore(), "runs/x", None),
    }
    with pytest.raises(CheckpointMismatchError, match="fingerprint"):
        RunExecutor.from_checkpoint(checkpoint, fingerprint="b" * 64, **kwargs)
    with pytest.raises(CheckpointMismatchError, match="slice"):
        RunExecutor.from_checkpoint({**checkpoint, "images_total": 99}, fingerprint=FP, **kwargs)
    with pytest.raises(CheckpointMismatchError, match="version"):
        RunExecutor.from_checkpoint({**checkpoint, "version": 0}, fingerprint=FP, **kwargs)


def test_partial_finalize_uses_processed_images_only(setup: dict[str, Any]) -> None:
    context: RunContext = setup["context"]
    executor = _executor(setup, MemStore())
    executor.process_batch(next(executor.batches(setup["runner"].loader, 2)))
    with pytest.raises(ValueError, match="chưa xử lý"):
        executor.finalize(RUN_ID)
    finalized = executor.finalize(RUN_ID, partial=True)
    assert finalized.images_done == 2 and finalized.metrics.partial
    clean = context.clean_metrics_on(executor.done)
    assert finalized.metrics.clean.map50 == clean.map50
    assert all(r.image_id in executor.done for r in finalized.failure_cases)


def test_finalize_without_images_fails(setup: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="Chưa xử lý"):
        _executor(setup, MemStore()).finalize(RUN_ID, partial=True)


def test_store_candidates_promote_is_idempotent_and_discard_cleans() -> None:
    store = MemStore()
    candidates = StoreCandidates(store, "runs/r", 4 / 255)
    image = np.full((3, 640, 640), 0.5, np.float32)
    candidates.add("000001", image, image)
    candidates.add("000002", image, image)
    assert store.keys("runs/r/candidates/000001/") == [
        f"runs/r/candidates/000001/{name}" for name in sorted(CANDIDATE_FILES)
    ]
    case_id = UUID("22222222-2222-5333-8444-555555555555")
    first = candidates.promote("000001", case_id)
    again = candidates.promote("000001", case_id)  # chạy lại finalize sau khi worker chết
    assert first == again
    candidates.discard("000002")
    candidates.discard("000002")
    assert store.keys("runs/r/candidates/") == []
    assert len(store.keys(f"runs/r/cases/{case_id}/")) == len(CANDIDATE_FILES)


def test_thumbnail_keeps_aspect_ratio() -> None:
    wide = np.zeros((3, 100, 640), np.float32)
    image = Image.open(io.BytesIO(thumbnail_webp(wide)))
    assert image.format == "WEBP" and image.size == (320, 50)


def test_local_store_is_not_deletable(tmp_path: Path) -> None:
    assert not isinstance(LocalStore(tmp_path), DeletableStore)
    assert isinstance(MemStore(), DeletableStore)
