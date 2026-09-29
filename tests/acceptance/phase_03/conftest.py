"""Fixture cho test nghiệm thu Phase 3 (validation.md Phase 3).

Mọi test ở đây cần Postgres và MinIO thật (marker `db`; `make test-db` hoặc job acceptance của CI)
và fixture của Phase 0 (`make fixtures`: 5 ảnh KITTI, YOLOv8n).

Dựng một lần mỗi phiên:
- `LocalStore` từ fixture qua CLI `advertest` (import-kitti, model register, slice 5 ảnh seed 42,
  mapping kitti-coco) như Phase 2, cộng một YOLOv8n khởi tạo ngẫu nhiên có bài kiểm tra gradient
  không đạt (cho run `incompatible`);
- DB đã migrate, seed (attack catalog, admin, `local-dev`), `advertest-admin import-local`.

Mỗi test có API FastAPI riêng (DB, MinIO, đồng hồ giả) và worker thật (`JobRunner`) gọi API qua
TestClient; test cần HTTP thật (CLI `advertest-worker`) dùng `live_api` (uvicorn trong luồng).
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
import uuid
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
import torch
import uvicorn
import yaml
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from typer.testing import CliRunner, Result
from ultralytics.models import YOLO
from ultralytics.nn.tasks import DetectionModel

from advertest_contracts.hashing import sha256_of
from advertest_contracts.models import CostProfile, GradientCheck, RunStartRequest
from advertest_worker.cache import JobCache
from advertest_worker.client import WorkerClient
from advertest_worker.job import BatchHook, JobRunner
from attacks.registry import get_spec, load_catalog
from backend.admin_cli import cli as admin_cli
from backend.admin_cli.seed import AdminAccount, seed
from backend.app.api.deps import Storage, get_clock, get_sessionmaker, get_storage
from backend.app.db import models as m
from backend.app.main import create_app
from backend.app.presign import Presigner
from backend.app.services import experiments
from backend.app.storage import (
    BUCKET_ARTIFACTS,
    BUCKET_DATASETS,
    BUCKET_MODELS,
    Buckets,
    make_s3_client,
)
from ml_core.cli import app as ml_app
from ml_core.fixtures import FIXTURES_DIR
from ml_core.models import register as register_module

REPO = Path(__file__).resolve().parents[3]
KITTI_ROOT = FIXTURES_DIR / "kitti"
WEIGHTS = FIXTURES_DIR / "yolov8n.pt"
GOLDEN_PHASE_02 = FIXTURES_DIR / "golden" / "phase_02.json"
ADMIN = "admin-phase03@example.com"
COMMIT = "3" * 40
T0 = datetime(2026, 9, 29, 8, 0, tzinfo=UTC)


def env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Thiếu {name}. Chạy test nghiệm thu cần DB bằng `make test-db`.")
    return value


# ---------------------------------------------------------------- DB, MinIO


@pytest.fixture(scope="session")
def alembic_config() -> Config:
    config = Config(str(REPO / "backend" / "alembic.ini"))
    config.attributes["url"] = env("ADVERTEST_TEST_OWNER_URL")
    return config


@pytest.fixture(scope="session")
def owner_engine(alembic_config: Config) -> Iterator[Engine]:
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    engine = create_engine(env("ADVERTEST_TEST_OWNER_URL"))
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def app_engine(owner_engine: Engine) -> Iterator[Engine]:
    engine = create_engine(env("ADVERTEST_TEST_APP_URL"))
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def cli_env() -> dict[str, str]:
    """Biến môi trường của `advertest-admin` (như trong container api)."""
    return {
        "DATABASE_URL": env("ADVERTEST_TEST_APP_URL"),
        "MINIO_ENDPOINT": env("ADVERTEST_TEST_MINIO_ENDPOINT"),
        "MINIO_ACCESS_KEY": env("ADVERTEST_TEST_MINIO_ACCESS_KEY"),
        "MINIO_SECRET_KEY": env("ADVERTEST_TEST_MINIO_SECRET_KEY"),
    }


@pytest.fixture(scope="session")
def buckets(cli_env: dict[str, str]) -> Buckets:
    client = make_s3_client(
        cli_env["MINIO_ENDPOINT"], cli_env["MINIO_ACCESS_KEY"], cli_env["MINIO_SECRET_KEY"]
    )
    raw: Any = client
    existing = {b["Name"] for b in raw.list_buckets().get("Buckets", [])}
    for name in (BUCKET_MODELS, BUCKET_DATASETS, BUCKET_ARTIFACTS):
        if name not in existing:
            raw.create_bucket(Bucket=name)
    return Buckets.from_client(client)


def presigner(expires_s: int = 900) -> Presigner:
    return Presigner.for_endpoint(
        env("ADVERTEST_TEST_MINIO_ENDPOINT"),
        env("ADVERTEST_TEST_MINIO_ACCESS_KEY"),
        env("ADVERTEST_TEST_MINIO_SECRET_KEY"),
        expires_s,
    )


# ---------------------------------------------------------------- CLI


def admin(cli_env: dict[str, str], *args: str, code: int = 0) -> Result:
    """`advertest-admin ...`; kiểm tra mã thoát."""
    result = CliRunner().invoke(admin_cli.app, list(args), env=cli_env)
    assert result.exit_code == code, result.output
    return result


def ml(store_dir: Path, *args: str) -> Any:
    result = CliRunner().invoke(ml_app, ["--store-dir", str(store_dir), *args])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


# ---------------------------------------------------------------- dữ liệu


@dataclass(frozen=True)
class World:
    store_dir: Path
    model_id: str
    slice_id: str
    mapping_id: str
    image_ids: list[str]
    random_model_id: str  # supports_gradients = false
    random_mapping_id: str

    def config(
        self,
        attacks: dict[str, list[float]],
        *,
        seed: int = 0,
        gradient: bool = True,
        failure_cases: int = 3,
    ) -> dict[str, Any]:
        """`LocalRunConfig` cho `advertest-admin submit`."""
        catalog = load_catalog()
        entries = []
        for name, levels in attacks.items():
            spec = get_spec(catalog, name=name)
            entries.append(
                {
                    "attack_spec_id": str(spec.id),
                    "spec_sha256": spec.spec_sha256,
                    "mode": "grid",
                    "grid": {"levels": levels},
                    "seed": seed,
                }
            )
        return {
            "model_id": self.model_id if gradient else self.random_model_id,
            "slice_id": self.slice_id,
            "mapping_id": self.mapping_id if gradient else self.random_mapping_id,
            "attacks": entries,
            "failure_cases_per_run": failure_cases,
        }


@pytest.fixture(scope="session")
def world(
    app_engine: Engine,
    buckets: Buckets,
    cli_env: dict[str, str],
    tmp_path_factory: pytest.TempPathFactory,
) -> World:
    assert WEIGHTS.is_file() and KITTI_ROOT.is_dir(), "Thiếu fixture: chạy `make fixtures`"
    tmp = tmp_path_factory.mktemp("phase03")
    store_dir = tmp / "store"
    sha = ml(store_dir, "dataset", "import-kitti", "--root", str(KITTI_ROOT))[
        "dataset_version_sha256"
    ]
    model = ml(store_dir, "model", "register", "--weights", str(WEIGHTS), "--name", "yolov8n-coco")
    assert model["supports_gradients"] is True
    slice_spec = ml(store_dir, "slice", "create", "--dataset", sha, "--size", "5", "--seed", "42")
    mapping = ml(store_dir, "mapping", "create", "--dataset", sha, "--model", model["id"])

    # YOLOv8n ngẫu nhiên, bài kiểm tra gradient không đạt (cho run incompatible).
    torch.manual_seed(0)
    random_weights = tmp / "yolov8n-random.pt"
    yolo = YOLO("yolov8n.yaml")
    assert isinstance(yolo.model, DetectionModel)
    names = {0: "person", 2: "car", 7: "truck"}  # đủ class đích của preset kitti-coco
    yolo.model.names = {i: names.get(i, f"class{i}") for i in range(80)}
    yolo.save(random_weights)
    failed = GradientCheck(
        passed=False, checked_at=T0, details="loss không tăng (giả lập trong test nghiệm thu)"
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(register_module, "run_gradient_check", lambda *a, **k: failed)
        random_model = ml(
            store_dir, "model", "register", "--weights", str(random_weights),
            "--name", "yolov8n-random",
        )  # fmt: skip
    random_mapping = ml(store_dir, "mapping", "create", "--dataset", sha, "--model",
                        random_model["id"])  # fmt: skip

    seed(app_engine, AdminAccount(email=ADMIN, password="admin-phase03"))
    imported = admin(cli_env, "import-local", "--store", str(store_dir), "--as", ADMIN)
    assert "slice: 1" in imported.output
    return World(
        store_dir=store_dir,
        model_id=model["id"],
        slice_id=slice_spec["id"],
        mapping_id=mapping["id"],
        image_ids=list(slice_spec["image_ids"]),
        random_model_id=random_model["id"],
        random_mapping_id=random_mapping["id"],
    )


@pytest.fixture(scope="session")
def golden() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(GOLDEN_PHASE_02.read_text())
    return data


@pytest.fixture(autouse=True)
def git_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fingerprint cố định; test đổi GIT_COMMIT khi cần fingerprint khác (tránh cache)."""
    monkeypatch.setenv("GIT_COMMIT", COMMIT)
    monkeypatch.delenv("DOCKER_IMAGE_DIGEST", raising=False)


# ---------------------------------------------------------------- API, worker


class FakeClock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class Crash(BaseException):
    """Worker chết đột ngột (kill -9): không gửi gì thêm."""


def make_app(app_engine: Engine, buckets: Buckets, clock: FakeClock) -> FastAPI:
    app = create_app()
    factory = sessionmaker(app_engine)
    signer = presigner()
    app.dependency_overrides[get_sessionmaker] = lambda: factory
    app.dependency_overrides[get_storage] = lambda: Storage(buckets, signer)
    app.dependency_overrides[get_clock] = lambda: clock
    return app


@dataclass
class Harness:
    """API trong tiến trình + CLI quản trị + worker thật."""

    api: TestClient
    clock: FakeClock
    app_engine: Engine
    cli_env: dict[str, str]
    world: World
    tmp: Path
    counter: list[int] = field(default_factory=lambda: [0])

    # ---- quản trị

    def target(self, *, time_limit: int = 7200) -> tuple[str, str]:
        """Compute target mới; trả (tên, token)."""
        name = f"t-{uuid.uuid4().hex[:8]}"
        out = admin(self.cli_env, "compute-target", "create", "--name", name,
                    "--time-limit", str(time_limit), "--as", ADMIN)  # fmt: skip
        return name, out.output.strip().splitlines()[-1]

    def submit(self, target: str, config: dict[str, Any], time_limit: int | None = None) -> UUID:
        self.counter[0] += 1
        path = self.tmp / f"config-{self.counter[0]}.yaml"
        path.write_text(yaml.safe_dump(config))
        args = ["submit", "--config", str(path), "--target", target, "--as", ADMIN]
        if time_limit is not None:
            args += ["--time-limit", str(time_limit)]
        out = admin(self.cli_env, *args)
        return UUID(out.output.split()[1].rstrip(":"))

    def profile(
        self, target: str, token: str, *, sec: float, batch: int, attacks: Sequence[str]
    ) -> None:
        """Cost profile dựng sẵn (bỏ qua calibration, batch size cố định)."""
        with Session(self.app_engine) as session:
            target_row = session.query(m.ComputeTarget).filter_by(name=target).one()
            target_id = target_row.id
        client = self.client(token)
        for name in attacks:
            client.cost_profile(
                CostProfile.model_validate(
                    {
                        "compute_target_id": str(target_id),
                        "model_version_id": self.world.model_id,
                        "attack_spec_id": str(get_spec(load_catalog(), name=name).id),
                        "sec_per_image": sec,
                        "peak_vram_mb": 0,
                        "batch_size": batch,
                        "measured_at": T0.isoformat(),
                        "environment": {
                            "compute_target_id": str(target_id),
                            "gpu_model": None,
                            "cuda_version": None,
                            "driver_version": None,
                        },
                    }
                )
            )

    # ---- worker

    def client(self, token: str) -> WorkerClient:
        return WorkerClient(self.api, token, sleep=lambda _s: None)

    def runner(
        self, token: str, cache: str = "cache", on_batch: BatchHook | None = None,
        heartbeat: float = 3600,
    ) -> JobRunner:  # fmt: skip
        return JobRunner(
            self.client(token),
            JobCache(self.tmp / cache),
            "cpu",
            url_http=httpx.Client(timeout=120),
            heartbeat_interval_s=heartbeat,
            clock=self.clock,
            on_batch=on_batch,
        )

    def work(self, token: str, experiment_id: UUID, **kwargs: Any) -> None:
        """Worker nhận đúng experiment này (lease) và chạy tới khi xong hoặc dừng."""
        runner = self.runner(token, **kwargs)
        lease = runner.client.lease()
        assert lease is not None and lease.experiment_id == experiment_id
        runner.run_lease(lease)

    # ---- trạng thái

    def state(self, experiment_id: UUID) -> tuple[m.Experiment, list[m.Run]]:
        with Session(self.app_engine) as session:
            return session.get_one(m.Experiment, experiment_id), experiments.runs_of(
                session, experiment_id
            )

    def cases(self, run_id: UUID) -> list[m.FailureCase]:
        with Session(self.app_engine) as session:
            return list(
                session.query(m.FailureCase).filter_by(run_id=run_id).order_by(m.FailureCase.rank)
            )


@pytest.fixture
def harness(
    app_engine: Engine,
    buckets: Buckets,
    cli_env: dict[str, str],
    world: World,
    tmp_path: Path,
) -> Iterator[Harness]:
    clock = FakeClock()
    with TestClient(make_app(app_engine, buckets, clock)) as api:
        yield Harness(api, clock, app_engine, cli_env, world, tmp_path)


def batch_counter() -> tuple[list[tuple[UUID, str]], BatchHook]:
    """Spy đếm ảnh được xử lý (mỗi batch gọi hook một lần)."""
    seen: list[tuple[UUID, str]] = []

    def hook(run_id: UUID, ids: Sequence[str]) -> None:
        seen.extend((run_id, image_id) for image_id in ids)

    return seen, hook


def crash_after(batches: int, seen: list[tuple[UUID, str]] | None = None) -> BatchHook:
    """Hook làm worker chết sau `batches` batch (tính trên mọi run)."""
    count = [0]

    def hook(run_id: UUID, ids: Sequence[str]) -> None:
        if seen is not None:
            seen.extend((run_id, image_id) for image_id in ids)
        count[0] += 1
        if count[0] >= batches:
            raise Crash

    return hook


# ---------------------------------------------------------------- API qua HTTP thật


@dataclass
class LiveApi:
    url: str
    clock: FakeClock


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


@pytest.fixture
def live_api(app_engine: Engine, buckets: Buckets, world: World) -> Iterator[LiveApi]:
    """API chạy bằng uvicorn trong luồng (cho CLI `advertest-worker`)."""
    clock = FakeClock()
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(make_app(app_engine, buckets, clock), host="127.0.0.1", port=port,
                       log_level="warning")
    )  # fmt: skip
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started:
        assert time.monotonic() < deadline, "uvicorn không khởi động"
        time.sleep(0.05)
    yield LiveApi(f"http://127.0.0.1:{port}", clock)
    server.should_exit = True
    thread.join(timeout=10)


def start_request(lease_id: UUID) -> RunStartRequest:
    """`RunStartRequest` hợp lệ với fingerprint riêng mỗi lần (seed ngẫu nhiên trong
    fingerprint_inputs): run đã completed của test khác không làm lần này trúng cache."""
    data = json.loads((REPO / "contracts/mocks/run_start_request/gpu_local.json").read_text())
    data["lease_id"] = str(lease_id)
    data["fingerprint_inputs"]["seed"] = uuid.uuid4().int % (1 << 31)
    data["fingerprint"] = sha256_of(data["fingerprint_inputs"])
    return RunStartRequest.model_validate(data)


def artifact_keys(buckets: Buckets, run_id: UUID, sub: str) -> list[str]:
    return buckets.artifacts.list(f"runs/{run_id}/{sub}/")


Hook = Callable[[UUID, Sequence[str]], None]
