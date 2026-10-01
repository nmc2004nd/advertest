"""Fixture cho test nghiệm thu Phase 6 (validation.md Phase 6, Automated Tests).

Hai loại test:
- Thuật toán (không cần DB): batch letterbox của 5 ảnh KITTI fixture (ground truth, ignore region,
  mask vùng ảnh thật), YOLOv8n thật trên CPU.
- Hệ thống (marker `db`, `make test-db`): dùng lại hạ tầng của Phase 5 (DB tạm đã migrate và seed,
  MinIO, API thật qua TestClient, worker CPU thật `JobRunner`). Dữ liệu riêng của Phase 6:
  - slice đánh giá 3 ảnh và slice huấn luyện 2 ảnh còn lại (`slice create --exclude-slice`);
  - slice 4 ảnh (giao slice đánh giá) và slice của một dataset version khác (bỏ một ảnh);
  - spec patch `adv_patch` có `max_iter = 4`, `checkpoint_every = 2` (version riêng của test,
    như `scripts/e2e.sh` task 36a) để train trên CPU trong vài giây.
"""

from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np
import pytest
from sqlalchemy import Engine, insert, select
from sqlalchemy.orm import Session

from advertest_contracts.ids import content_id
from advertest_contracts.models import (
    AttackSpec,
    CostProfile,
    ProgressReport,
    compute_spec_sha256,
)
from advertest_worker.client import WorkerClient
from attacks.registry import get_spec, load_catalog
from backend.app.db import models as m
from ml_core.data.loader import Batch, SliceLoader
from ml_core.fixtures import FIXTURES_DIR
from ml_core.runner.images import letterbox_mask
from ml_core.store import LocalStore

from ._phase05 import load

P5 = load()

# Hạ tầng của Phase 5: DB tạm (downgrade/upgrade rồi seed), MinIO, API, worker thật.
alembic_config = P5.alembic_config
owner_engine = P5.owner_engine
app_engine = P5.app_engine
cli_env = P5.cli_env
buckets = P5.buckets
fresh_fingerprint = P5.fresh_fingerprint
Api = P5.Api
World = P5.World
Target = P5.Target
FakeClock = P5.FakeClock
ADMIN_EMAIL: str = P5.ADMIN_EMAIL
DEV_OPEN: str = P5.DEV_OPEN
T0 = P5.T0
admin_cli_run = P5.admin_cli_run
ml = P5.ml
attack = P5.attack
spec_id = P5.spec_id
post = P5.post
ok = P5.ok
error = P5.error

KITTI_ROOT = FIXTURES_DIR / "kitti"
WEIGHTS = FIXTURES_DIR / "yolov8n.pt"
PATCH_MAX_ITER = 4
PATCH_CHECKPOINT_EVERY = 2
PATCH_VERSION = 906  # version riêng của test, không trùng seed


# ---------------------------------------------------------------- thuật toán (không cần DB)


@dataclass(frozen=True)
class Kitti:
    """5 ảnh fixture trong một batch letterbox; `targets` như `RunExecutor` truyền cho
    `Perturbation.apply` (Phase 6: có `image_id` và `ignore_boxes`)."""

    batch: Batch
    mask: np.ndarray
    targets: list[dict[str, Any]]
    store_dir: Path
    ids: dict[str, str]  # model, slice, mapping

    def subset(self, order: list[int]) -> tuple[np.ndarray, list[dict[str, Any]], np.ndarray]:
        return (
            self.batch.images[order].copy(),
            [self.targets[i] for i in order],
            self.mask[order].copy(),
        )


@pytest.fixture(scope="session")
def kitti(tmp_path_factory: pytest.TempPathFactory) -> Kitti:
    assert WEIGHTS.is_file() and KITTI_ROOT.is_dir(), "Thiếu fixture: chạy `make fixtures`"
    store_dir = tmp_path_factory.mktemp("phase06-kitti") / "store"
    sha = ml(store_dir, "dataset", "import-kitti", "--root", str(KITTI_ROOT))[
        "dataset_version_sha256"
    ]
    model = ml(store_dir, "model", "register", "--weights", str(WEIGHTS), "--name", "yolov8n-coco")
    slice_spec = ml(store_dir, "slice", "create", "--dataset", sha, "--size", "5", "--seed", "42")
    mapping = ml(store_dir, "mapping", "create", "--dataset", sha, "--model", model["id"])
    loader = SliceLoader.from_ids(
        LocalStore(store_dir), UUID(slice_spec["id"]), UUID(mapping["id"])
    )
    batch = next(loader.batches(5))
    targets = [
        {**target, "image_id": image_id, "ignore_boxes": ignore["boxes"]}
        for target, image_id, ignore in zip(
            batch.targets, batch.image_ids, batch.ignore, strict=True
        )
    ]
    ids = {"model": model["id"], "slice": slice_spec["id"], "mapping": mapping["id"]}
    return Kitti(batch, letterbox_mask(batch.infos), targets, store_dir, ids)


# ---------------------------------------------------------------- hệ thống (DB, API, worker)


@dataclass(frozen=True)
class World6:
    base: Any  # World của Phase 5: slice đánh giá 3 ảnh
    training_slice_id: str
    training_image_ids: list[str]
    overlap_slice_id: str  # 4 ảnh, giao slice đánh giá
    other_version_slice_id: str  # dataset version khác
    dataset_version_id: str
    patch: AttackSpec  # adv_patch max_iter nhỏ


def _patch_spec() -> AttackSpec:
    base = get_spec(load_catalog(), name="adv_patch")
    body = base.model_dump(mode="json", exclude={"id", "spec_sha256"})
    body["version"] = PATCH_VERSION
    body["training"]["max_iter"] = PATCH_MAX_ITER
    body["training"]["checkpoint_every"] = PATCH_CHECKPOINT_EVERY
    sha = compute_spec_sha256(body)
    return AttackSpec.model_validate({**body, "id": str(content_id(sha)), "spec_sha256": sha})


@pytest.fixture(scope="session")
def world(
    app_engine: Engine,
    owner_engine: Engine,
    buckets: Any,
    cli_env: dict[str, str],
    tmp_path_factory: pytest.TempPathFactory,
) -> World6:
    assert WEIGHTS.is_file() and KITTI_ROOT.is_dir(), "Thiếu fixture: chạy `make fixtures`"
    tmp = tmp_path_factory.mktemp("phase06")
    store = tmp / "store"
    sha = ml(store, "dataset", "import-kitti", "--root", str(KITTI_ROOT))["dataset_version_sha256"]
    model = ml(store, "model", "register", "--weights", str(WEIGHTS), "--name", "yolov8n-coco")
    evaluation = ml(store, "slice", "create", "--dataset", sha, "--size", "3", "--seed", "6")
    training = ml(store, "slice", "create", "--dataset", sha, "--size", "2", "--seed", "6",
                  "--exclude-slice", evaluation["id"])  # fmt: skip
    overlap = ml(store, "slice", "create", "--dataset", sha, "--size", "4", "--seed", "1")
    mapping = ml(store, "mapping", "create", "--dataset", sha, "--model", model["id"])

    # Dataset version khác: cùng fixture bỏ một ảnh.
    other_root = tmp / "kitti-4"
    shutil.copytree(KITTI_ROOT, other_root)
    dropped = sorted((other_root / "image_2").glob("*.png"))[0]
    dropped.unlink()
    (other_root / "label_2" / f"{dropped.stem}.txt").unlink()
    other_sha = ml(store, "dataset", "import-kitti", "--root", str(other_root))[
        "dataset_version_sha256"
    ]
    other = ml(store, "slice", "create", "--dataset", other_sha, "--size", "2", "--seed", "6")
    admin_cli_run(cli_env, "import-local", "--store", str(store), "--as", ADMIN_EMAIL)

    patch = _patch_spec()
    with Session(owner_engine) as session, session.begin():
        session.execute(
            insert(m.AttackSpecRow).values(
                id=patch.id, name=patch.name, version=patch.version, kind=patch.kind,
                access=patch.access, spec=patch.model_dump(mode="json"),
                spec_sha256=patch.spec_sha256,
            )
        )  # fmt: skip
    with Session(app_engine) as session:
        row = session.get(m.Slice, UUID(evaluation["id"]))
        assert row is not None
        dataset_id = session.scalars(
            select(m.DatasetVersion.dataset_id).where(m.DatasetVersion.id == row.dataset_version_id)
        ).one()
        version_id = str(row.dataset_version_id)
    base = World(
        model_id=model["id"],
        slice_id=evaluation["id"],
        mapping_id=mapping["id"],
        image_ids=list(evaluation["image_ids"]),
        dataset_id=dataset_id,
        # Phase 6 không dùng model không hỗ trợ gradient: trỏ về model thật.
        random_model_id=model["id"],
        random_mapping_id=mapping["id"],
    )
    return World6(
        base=base,
        training_slice_id=training["id"],
        training_image_ids=list(training["image_ids"]),
        overlap_slice_id=overlap["id"],
        other_version_slice_id=other["id"],
        dataset_version_id=version_id,
        patch=patch,
    )


@pytest.fixture
def api(app_engine: Engine, buckets: Any, cli_env: dict[str, str], world: World6,
        tmp_path: Path) -> Any:  # fmt: skip
    return Api(app_engine, buckets, cli_env, world.base, tmp_path)


def patch_attack(world: World6, levels: list[float], *, training: str | None = None,
                 early_stop: bool | None = None) -> dict[str, Any]:  # fmt: skip
    """Attack patch (spec `max_iter` nhỏ của test) với slice huấn luyện của world."""
    entry: dict[str, Any] = {
        "attack_spec_id": str(world.patch.id),
        "spec_sha256": world.patch.spec_sha256,
        "mode": "grid",
        "grid": {"levels": levels},
        "seed": 0,
        "training_slice_id": training or world.training_slice_id,
    }
    if early_stop is not None:
        entry["grid"]["early_stop"] = early_stop
    return entry


def grid_attack(
    name: str, levels: list[float], *, early_stop: bool | None = None
) -> dict[str, Any]:
    entry: dict[str, Any] = attack(name, levels)
    if early_stop is not None:
        entry["grid"] = {**entry["grid"], "early_stop": early_stop}
    return entry


def profile(
    api: Any,
    target: Any,
    specs: dict[UUID, float],
    *,
    batch: int = 4,
    sec_per_image_iteration: dict[UUID, float] | None = None,
) -> None:
    """Cost profile qua API nội bộ (bỏ qua calibration); `specs` là spec id → giây/ảnh."""
    client = WorkerClient(api.client(), target.token, sleep=lambda _s: None)
    for attack_spec_id, sec in specs.items():
        client.cost_profile(
            CostProfile.model_validate(
                {
                    "compute_target_id": target.id, "model_version_id": api.world.model_id,
                    "attack_spec_id": str(attack_spec_id), "sec_per_image": sec,
                    "peak_vram_mb": 0, "batch_size": batch, "measured_at": T0.isoformat(),
                    "environment": {"compute_target_id": target.id, "gpu_model": None,
                                    "cuda_version": None, "driver_version": None},
                    "sec_per_image_iteration": (sec_per_image_iteration or {}).get(
                        attack_spec_id
                    ),
                }
            )
        )  # fmt: skip


@dataclass
class ProgressLog:
    reports: list[tuple[UUID, ProgressReport]]

    def phases(self, run_id: UUID) -> list[str]:
        return [r.phase.value for rid, r in self.reports if rid == run_id]


@pytest.fixture
def progress_log(monkeypatch: pytest.MonkeyPatch) -> Iterator[ProgressLog]:
    """Ghi lại mọi `ProgressReport` worker gửi lên (vẫn gửi thật)."""
    log = ProgressLog([])
    original = WorkerClient.progress

    def spy(self: WorkerClient, run_id: UUID, body: ProgressReport) -> Any:
        log.reports.append((run_id, body))
        return original(self, run_id, body)

    monkeypatch.setattr(WorkerClient, "progress", spy)
    yield log


def runs_of(client: Any, experiment_id: str) -> list[dict[str, Any]]:
    response = client.get(f"/experiments/{experiment_id}/runs")
    assert response.status_code == 200, response.text
    runs: list[dict[str, Any]] = response.json()
    return runs


def new_id() -> str:
    return str(uuid.uuid4())


def dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
