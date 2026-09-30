"""Lấy hoặc train patch cho một run patch (requirements.md Phase 6, mục Patch attack; task 17).

1. `bundle.patches[key].artifact` có sẵn: tải `patch.npy` (kiểm tra sha256), không train.
2. Chưa có: train trên slice huấn luyện, tiếp từ `checkpoint_key` nếu đang dở. Checkpoint ghi vào
   `patches/<key>/checkpoints/<vòng>.npz` (vòng 0 trước lần báo đầu); sau mỗi vòng gửi
   `ProgressReport` với `phase = training` (thời gian train tính vào giới hạn). Checkpoint cũ bị
   xóa sau khi API nhận checkpoint mới. Chỉ thị khác `continue` → `PatchInterrupted`, checkpoint
   giữ lại để chạy tiếp.
3. Train xong: upload `patch.npy`, `patch.png`, đăng ký (`register_patch`). Khóa đã có (worker khác
   đăng ký trước) thì API trả bản cũ: dùng bản đó.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from advertest_contracts.enums import RunPhase
from advertest_contracts.models import (
    AttackSpec,
    BundlePatch,
    PatchArtifact,
    PatchRegistration,
    ProgressReport,
    WorkerDirective,
    patch_prefix,
)
from advertest_contracts.perturbation import ImageBatch, MaskBatch
from advertest_worker.client import LeaseLost
from attacks.patch.artifact import build_artifact, load_patch
from attacks.patch.training import PatchArray, PatchTrainer, TrainingState, training_params

logger = logging.getLogger(__name__)


class PatchStore(Protocol):
    def get(self, key: str) -> bytes: ...

    def put(self, key: str, data: bytes) -> None: ...

    def delete(self, key: str) -> None: ...


class PatchClient(Protocol):
    def progress(self, run_id: UUID, body: ProgressReport) -> WorkerDirective: ...

    def register_patch(self, run_id: UUID, body: PatchRegistration) -> PatchArtifact: ...


class PatchInterrupted(Exception):
    """Train dừng giữa chừng theo chỉ thị của API (`cancel` hoặc `stop_limit`)."""

    def __init__(self, directive: WorkerDirective) -> None:
        super().__init__(f"Train patch dừng theo chỉ thị {directive.action}")
        self.directive = directive


@dataclass
class PatchJob:
    spec: AttackSpec
    estimator: Any
    patch: BundlePatch
    run_id: UUID
    lease_id: UUID
    seed: int
    weights_sha256: str
    training_slice_sha256: str
    store: PatchStore
    client: PatchClient
    clock: Callable[[], datetime]
    on_directive: Callable[[WorkerDirective], None] = lambda _directive: None


def checkpoint_key(key: str, iterations_done: int) -> str:
    return f"{patch_prefix(key)}checkpoints/{iterations_done}.npz"


def obtain_patch(
    job: PatchJob, images: ImageBatch | None, mask: MaskBatch | None
) -> tuple[PatchArray, PatchArtifact]:
    """Patch đã train của run (tải về hoặc train). `images`, `mask` là ảnh letterbox của slice
    huấn luyện; chỉ cần khi phải train (không dùng khi đã có patch)."""
    existing = job.patch.artifact
    if existing is not None:
        logger.info("Dùng patch có sẵn %s", existing.key)
        return load_patch(job.store.get(existing.npy_key), existing), existing
    if images is None:
        raise ValueError("Cần ảnh của slice huấn luyện để train patch")
    return _train(job, images, mask)


def _train(
    job: PatchJob, images: ImageBatch, mask: MaskBatch | None
) -> tuple[PatchArray, PatchArtifact]:
    params = training_params(job.spec)
    key = job.patch.key
    state: TrainingState | None = None
    latest: str | None = job.patch.checkpoint_key
    if latest is not None:
        state = TrainingState.from_bytes(job.store.get(latest))
        logger.info("Train patch tiếp từ vòng %d", state.iterations_done)
    reported = state.seconds if state is not None else 0.0
    acknowledged = latest  # checkpoint mà API đang trỏ tới
    stopped: list[WorkerDirective] = []

    def on_checkpoint(current: TrainingState) -> None:
        nonlocal latest
        latest = checkpoint_key(key, current.iterations_done)
        job.store.put(latest, current.to_bytes())

    def on_progress(current: TrainingState) -> bool:
        nonlocal reported, acknowledged
        assert latest is not None  # vòng 0 luôn có checkpoint trước lần báo đầu
        directive = job.client.progress(
            job.run_id,
            ProgressReport(
                lease_id=job.lease_id,
                images_done=0,
                batch_index=0,
                checkpoint_key=latest,
                processing_seconds_delta=max(0.0, current.seconds - reported),
                phase=RunPhase.TRAINING,
                iterations_done=current.iterations_done,
                iterations_total=params.max_iter,
            ),
        )
        reported = current.seconds
        job.on_directive(directive)
        if acknowledged is not None and acknowledged != latest:
            _delete_quietly(job.store, acknowledged)
        acknowledged = latest
        if directive.action != "continue" and current.iterations_done < params.max_iter:
            stopped.append(directive)
            return False
        return True

    trainer = PatchTrainer(job.spec, job.estimator, area_ratio=job.patch.area_ratio, seed=job.seed)
    state = trainer.train(
        images, mask, state=state, on_progress=on_progress, on_checkpoint=on_checkpoint
    )
    if stopped:
        raise PatchInterrupted(stopped[0])

    artifact, files = build_artifact(
        job.spec,
        state,
        weights_sha256=job.weights_sha256,
        training_slice_sha256=job.training_slice_sha256,
        area_ratio=job.patch.area_ratio,
        seed=job.seed,
        created_at=job.clock(),
    )
    job.store.put(artifact.npy_key, files.npy)
    job.store.put(artifact.png_key, files.png)
    registered = job.client.register_patch(
        job.run_id, PatchRegistration(lease_id=job.lease_id, artifact=artifact)
    )
    if latest is not None:
        _delete_quietly(job.store, latest)  # patch đã đăng ký, checkpoint không còn cần
    if registered.patch_sha256 != artifact.patch_sha256:
        logger.info("Khóa %s đã có patch khác; dùng bản đã đăng ký", key)
        return load_patch(job.store.get(registered.npy_key), registered), registered
    return state.patch, registered


def _delete_quietly(store: PatchStore, key: str) -> None:
    """Lỗi khi xóa checkpoint cũ chỉ ghi cảnh báo, trừ mất lease (dừng experiment ngay)."""
    try:
        store.delete(key)
    except LeaseLost:
        raise
    except Exception:
        logger.warning("Không xóa được checkpoint patch %s", key, exc_info=True)
