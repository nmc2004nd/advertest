"""Lấy hoặc train patch trong worker (validation.md Phase 6, mục Patch; plan task 17).

Estimator giả của `attacks/tests`, store trong bộ nhớ, client giả ghi lại mọi lời gọi.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import numpy as np
import pytest

from advertest_contracts.enums import RunPhase
from advertest_contracts.models import (
    AttackSpec,
    BundlePatch,
    PatchArtifact,
    PatchRegistration,
    ProgressReport,
    WorkerDirective,
)
from advertest_worker.client import LeaseLost
from advertest_worker.patch import PatchInterrupted, PatchJob, checkpoint_key, obtain_patch
from attacks.patch.geometry import patch_key
from attacks.patch.training import TrainingState
from attacks.registry import get_spec, load_catalog
from attacks.tests import fake_detector as fd

RUN = UUID(int=1)
LEASE = UUID(int=2)
WEIGHTS = "a" * 64
TRAINING = "b" * 64
MAX_ITER = 5
CONTINUE = WorkerDirective(action="continue", remaining_seconds=100.0)


def _spec() -> AttackSpec:
    base = get_spec(load_catalog(), name="adv_patch")
    assert base.training is not None
    training = base.training.model_copy(
        update={"max_iter": MAX_ITER, "checkpoint_every": 2, "batch_size": 2}
    )
    return base.model_copy(update={"training": training})


def _key(spec: AttackSpec) -> str:
    return patch_key(
        spec, weights_sha256=WEIGHTS, training_slice_sha256=TRAINING, area_ratio=0.1, seed=0
    )


class Store:
    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}
        self.deleted: list[str] = []
        self.fail_delete: Exception | None = None

    def get(self, key: str) -> bytes:
        return self.data[key]

    def put(self, key: str, data: bytes) -> None:
        self.data[key] = data

    def delete(self, key: str) -> None:
        if self.fail_delete is not None:
            raise self.fail_delete
        self.deleted.append(key)
        self.data.pop(key, None)


class Client:
    def __init__(self, directives: dict[int, WorkerDirective] | None = None) -> None:
        self.directives = directives or {}  # vòng → chỉ thị trả về
        self.reports: list[ProgressReport] = []
        self.registered: list[PatchArtifact] = []
        self.answer: PatchArtifact | None = None  # bản API trả (mặc định: bản gửi lên)

    def progress(self, run_id: UUID, body: ProgressReport) -> WorkerDirective:
        self.reports.append(body)
        return self.directives.get(body.iterations_done or 0, CONTINUE)

    def register_patch(self, run_id: UUID, body: PatchRegistration) -> PatchArtifact:
        self.registered.append(body.artifact)
        return self.answer or body.artifact


def _job(
    store: Store,
    client: Client,
    *,
    artifact: PatchArtifact | None = None,
    checkpoint: str | None = None,
) -> PatchJob:
    spec = _spec()
    return PatchJob(
        spec=spec,
        estimator=fd.estimator(),
        patch=BundlePatch(
            key=_key(spec),
            attack_spec_id=spec.id,
            area_ratio=0.1,
            training_slice_id=UUID(int=3),
            artifact=artifact,
            checkpoint_key=checkpoint,
        ),
        run_id=RUN,
        lease_id=LEASE,
        seed=0,
        weights_sha256=WEIGHTS,
        training_slice_sha256=TRAINING,
        store=store,
        client=client,
        clock=lambda: datetime(2026, 10, 1, tzinfo=UTC),
    )


def test_trains_reports_progress_registers_and_cleans_checkpoints() -> None:
    store, client = Store(), Client()
    patch, artifact = obtain_patch(_job(store, client), fd.images(3), fd.mask(3))
    assert patch.shape == (3, artifact.side_px, artifact.side_px)
    assert artifact.iterations == MAX_ITER and len(client.registered) == 1
    reports = client.reports
    assert [r.iterations_done for r in reports] == [1, 2, 3, 4, 5]
    assert all(r.phase == RunPhase.TRAINING and r.images_done == 0 for r in reports)
    assert all(r.iterations_total == MAX_ITER for r in reports)
    # Checkpoint vòng 0, 2, 4; báo tiến độ trỏ vào checkpoint mới nhất đã ghi.
    key = artifact.key
    assert [r.checkpoint_key for r in reports] == [
        checkpoint_key(key, 0),
        checkpoint_key(key, 2),
        checkpoint_key(key, 2),
        checkpoint_key(key, 4),
        checkpoint_key(key, 4),
    ]
    assert sum(r.processing_seconds_delta for r in reports) > 0
    # Patch và PNG đã upload; mọi checkpoint đã xóa sau khi đăng ký.
    assert artifact.npy_key in store.data and artifact.png_key in store.data
    assert not [k for k in store.data if "/checkpoints/" in k]


def test_existing_patch_is_downloaded_not_trained() -> None:
    store, client = Store(), Client()
    trained, artifact = obtain_patch(_job(store, client), fd.images(3), fd.mask(3))
    again_client = Client()
    patch, same = obtain_patch(_job(store, again_client, artifact=artifact), None, None)
    np.testing.assert_array_equal(patch, trained)
    assert same == artifact and again_client.reports == [] and again_client.registered == []


def test_resume_from_checkpoint_reaches_max_iter_with_same_patch() -> None:
    straight, _ = obtain_patch(_job(Store(), Client()), fd.images(3), fd.mask(3))

    store = Store()
    stop = WorkerDirective(action="stop_limit", remaining_seconds=0.0)
    with pytest.raises(PatchInterrupted) as interrupted:
        obtain_patch(_job(store, Client({3: stop})), fd.images(3), fd.mask(3))
    assert interrupted.value.directive.action == "stop_limit"
    key = _key(_spec())
    saved = checkpoint_key(key, 2)
    assert saved in store.data  # checkpoint giữ lại để chạy tiếp
    assert TrainingState.from_bytes(store.data[saved]).iterations_done == 2

    client = Client()
    patch, artifact = obtain_patch(_job(store, client, checkpoint=saved), fd.images(3), fd.mask(3))
    assert artifact.iterations == MAX_ITER
    assert [r.iterations_done for r in client.reports] == [3, 4, 5]
    np.testing.assert_array_equal(patch, straight)


def test_lease_lost_while_deleting_checkpoint_propagates() -> None:
    store, client = Store(), Client()
    store.fail_delete = LeaseLost(409, "conflict", "lease mất")
    with pytest.raises(LeaseLost):
        obtain_patch(_job(store, client), fd.images(3), fd.mask(3))


def test_training_needs_images() -> None:
    with pytest.raises(ValueError, match="slice huấn luyện"):
        obtain_patch(_job(Store(), Client()), None, None)
