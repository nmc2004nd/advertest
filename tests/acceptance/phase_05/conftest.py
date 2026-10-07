"""Fixture cho test nghiệm thu Phase 5 (validation.md Phase 5, Automated Tests backend).

Mọi test ở đây cần Postgres và MinIO thật (marker `db`; `make test-db` hoặc job acceptance của CI)
và fixture của Phase 0 (`make fixtures`: 5 ảnh KITTI, YOLOv8n).

Dựng một lần mỗi phiên (như test nghiệm thu Phase 3):
- `LocalStore` từ fixture qua CLI `advertest` (import-kitti, model register, slice 5 ảnh seed 42,
  mapping kitti-coco), cộng một YOLOv8n ngẫu nhiên có bài kiểm tra gradient không đạt;
- DB đã migrate, seed (attack catalog, admin, `local-dev`), `advertest-admin import-local`.

Mỗi test gọi API công khai thật qua TestClient (DB, MinIO, đồng hồ giả); người dùng tạo qua API
(yêu cầu truy cập rồi admin duyệt). Worker thật (`JobRunner`, CPU) gọi API nội bộ qua TestClient.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
import torch
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from typer.testing import CliRunner, Result
from ultralytics.models import YOLO
from ultralytics.nn.tasks import DetectionModel

from advertest_contracts.models import CostProfile, ErrorResponse, GradientCheck
from advertest_worker.cache import JobCache
from advertest_worker.client import WorkerClient
from advertest_worker.job import BatchHook, JobRunner, PerturbationFactory
from attacks.registry import get_spec, load_catalog
from backend.admin_cli import cli as admin_cli
from backend.admin_cli.seed import AdminAccount, seed
from backend.app.api.deps import (
    Storage,
    get_artifact_reader,
    get_clock,
    get_sessionmaker,
    get_storage,
)
from backend.app.db import models as m
from backend.app.main import create_app
from backend.app.presign import Presigner
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
from ml_core.runner.provenance import Provenance

REPO = Path(__file__).resolve().parents[3]
KITTI_ROOT = FIXTURES_DIR / "kitti"
WEIGHTS = FIXTURES_DIR / "yolov8n.pt"
ADMIN_EMAIL = "admin-phase05@example.com"
ADMIN_PASSWORD = "mat-khau-admin-phase-05"
PASSWORD = "mat-khau-du-dai-1"
T0 = datetime(2026, 9, 30, 8, 0, tzinfo=UTC)
DEV_OPEN = "2edcdef5-0d3a-5d5f-98ac-b02637fa6718"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"


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
    seed(engine, AdminAccount(email=ADMIN_EMAIL, password=ADMIN_PASSWORD))
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def cli_env() -> dict[str, str]:
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
            continue
        # DB vừa dựng lại từ đầu: xóa object của phase trước (cùng key nội dung nhưng card khác
        # thời điểm đăng ký → import-local báo KeyConflictError).
        for page in raw.get_paginator("list_objects_v2").paginate(Bucket=name):
            keys = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
            if keys:
                raw.delete_objects(Bucket=name, Delete={"Objects": keys})
    return Buckets.from_client(client)


def admin_cli_run(cli_env: dict[str, str], *args: str) -> Result:
    result = CliRunner().invoke(admin_cli.app, list(args), env=cli_env)
    assert result.exit_code == 0, result.output
    return result


def ml(store_dir: Path, *args: str) -> Any:
    result = CliRunner().invoke(ml_app, ["--store-dir", str(store_dir), *args])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


# ---------------------------------------------------------------- dữ liệu


@dataclass(frozen=True)
class World:
    model_id: str
    slice_id: str
    mapping_id: str
    image_ids: list[str]
    dataset_id: UUID
    random_model_id: str  # supports_gradients = false
    random_mapping_id: str


@pytest.fixture(scope="session")
def world(
    app_engine: Engine,
    buckets: Buckets,
    cli_env: dict[str, str],
    tmp_path_factory: pytest.TempPathFactory,
) -> World:
    assert WEIGHTS.is_file() and KITTI_ROOT.is_dir(), "Thiếu fixture: chạy `make fixtures`"
    tmp = tmp_path_factory.mktemp("phase05")
    store_dir = tmp / "store"
    sha = ml(store_dir, "dataset", "import-kitti", "--root", str(KITTI_ROOT))[
        "dataset_version_sha256"
    ]
    model = ml(store_dir, "model", "register", "--weights", str(WEIGHTS), "--name", "yolov8n-coco")
    slice_spec = ml(store_dir, "slice", "create", "--dataset", sha, "--size", "5", "--seed", "42")
    mapping = ml(store_dir, "mapping", "create", "--dataset", sha, "--model", model["id"])

    torch.manual_seed(0)
    random_weights = tmp / "yolov8n-random.pt"
    yolo = YOLO("yolov8n.yaml")
    assert isinstance(yolo.model, DetectionModel)
    names = {0: "person", 2: "car", 7: "truck"}
    yolo.model.names = {i: names.get(i, f"class{i}") for i in range(80)}
    yolo.save(random_weights)
    failed = GradientCheck(passed=False, checked_at=T0, details="giả lập trong test nghiệm thu")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(register_module, "run_gradient_check", lambda *a, **k: failed)
        random_model = ml(
            store_dir, "model", "register", "--weights", str(random_weights),
            "--name", "yolov8n-random",
        )  # fmt: skip
    random_mapping = ml(store_dir, "mapping", "create", "--dataset", sha, "--model",
                        random_model["id"])  # fmt: skip

    admin_cli_run(cli_env, "import-local", "--store", str(store_dir), "--as", ADMIN_EMAIL)
    with Session(app_engine) as session:
        dataset_id = session.scalars(
            select(m.Dataset.id)
            .join(m.DatasetVersion, m.DatasetVersion.dataset_id == m.Dataset.id)
            .join(m.Slice, m.Slice.dataset_version_id == m.DatasetVersion.id)
            .where(m.Slice.id == UUID(slice_spec["id"]))
        ).one()
    return World(
        model_id=model["id"],
        slice_id=slice_spec["id"],
        mapping_id=mapping["id"],
        image_ids=list(slice_spec["image_ids"]),
        dataset_id=dataset_id,
        random_model_id=random_model["id"],
        random_mapping_id=random_mapping["id"],
    )


@pytest.fixture(autouse=True)
def fresh_fingerprint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mỗi test một git commit riêng: run không trúng cache của test khác (cần worker chạy thật)."""
    monkeypatch.setenv("GIT_COMMIT", uuid.uuid4().hex + uuid.uuid4().hex[:8])
    monkeypatch.delenv("DOCKER_IMAGE_DIGEST", raising=False)
    monkeypatch.delenv("DEV_ALLOW_UNBLURRED", raising=False)
    # TestClient kết nối từ host "testclient": coi là proxy tin cậy để mỗi client có IP riêng.
    monkeypatch.setenv("TRUSTED_PROXIES", "testclient")


def attack(name: str, levels: list[float], seed: int = 0) -> dict[str, Any]:
    spec = get_spec(load_catalog(), name=name)
    return {
        "attack_spec_id": str(spec.id),
        "spec_sha256": spec.spec_sha256,
        "mode": "grid",
        "grid": {"levels": levels},
        "seed": seed,
    }


def spec_id(name: str) -> str:
    return str(get_spec(load_catalog(), name=name).id)


# ---------------------------------------------------------------- API, người dùng, worker


class FakeClock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def presigner() -> Presigner:
    return Presigner.for_endpoint(
        env("ADVERTEST_TEST_MINIO_ENDPOINT"),
        env("ADVERTEST_TEST_MINIO_ACCESS_KEY"),
        env("ADVERTEST_TEST_MINIO_SECRET_KEY"),
    )


def random_ip() -> str:
    raw = uuid.uuid4().bytes
    return f"10.{raw[0]}.{raw[1]}.{raw[2] or 1}"


def csrf(client: TestClient) -> dict[str, str]:
    return {CSRF_HEADER: client.cookies.get(CSRF_COOKIE) or ""}


def post(client: TestClient, path: str, body: Any = None) -> httpx.Response:
    response: httpx.Response = client.post(path, json=body, headers=csrf(client))
    return response


def ok(response: httpx.Response) -> httpx.Response:
    assert response.status_code < 300, (response.status_code, response.text)
    return response


def error(response: httpx.Response) -> tuple[int, str, list[str]]:
    body = ErrorResponse.model_validate(response.json()).error
    return response.status_code, body.code, [f.path for f in body.fields or []]


@dataclass
class Target:
    id: str
    name: str
    token: str


@dataclass
class Api:
    engine: Engine
    buckets: Buckets
    cli_env: dict[str, str]
    world: World
    tmp: Path
    clock: FakeClock = field(default_factory=FakeClock)
    # Seam của worker (Phase R1): test thay cách dựng perturbation và provenance qua đây thay vì
    # patch tên cấp module của `advertest_worker.job`.
    perturbation_factory: PerturbationFactory | None = None
    provenance: Provenance | None = None

    def app(self) -> FastAPI:
        app = create_app()
        factory = sessionmaker(self.engine)
        storage = Storage(self.buckets, presigner())
        app.dependency_overrides[get_sessionmaker] = lambda: factory
        app.dependency_overrides[get_clock] = lambda: self.clock
        app.dependency_overrides[get_storage] = lambda: storage
        app.dependency_overrides[get_artifact_reader] = lambda: self.buckets.artifacts.get
        return app

    def client(self) -> TestClient:
        return TestClient(self.app(), headers={"X-Forwarded-For": random_ip()})

    def login(self, client: TestClient, email: str, password: str = PASSWORD) -> None:
        response = client.post("/auth/login", json={"email": email, "password": password})
        assert response.status_code == 200, response.text

    def admin(self) -> TestClient:
        client = self.client()
        self.login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
        return client

    def user(self, *roles: str) -> tuple[UUID, str, TestClient]:
        """Người dùng qua luồng thật: yêu cầu truy cập, admin duyệt, rồi đăng nhập."""
        email = f"u-{uuid.uuid4().hex[:10]}@phase05.test"
        body = {
            "full_name": "Người thử Phase 5", "email": email, "organization": "VinAI",
            "requested_role": roles[0] if roles else "engineer",
            "reason": "Kiểm thử Phase 5", "password": PASSWORD,
        }  # fmt: skip
        assert self.client().post("/auth/request-access", json=body).status_code == 202
        with Session(self.engine) as session:
            user_id = session.scalars(select(m.User.id).where(m.User.email == email)).one()
        ok(
            post(
                self.admin(),
                f"/admin/users/{user_id}/approve",
                {"roles": list(roles or ["engineer"])},
            )
        )
        client = self.client()
        self.login(client, email)
        return user_id, email, client

    def target(self, *, time_limit: int = 7200) -> Target:
        name = f"t-{uuid.uuid4().hex[:8]}"
        out = admin_cli_run(self.cli_env, "compute-target", "create", "--name", name,
                            "--time-limit", str(time_limit), "--as", ADMIN_EMAIL)  # fmt: skip
        token = out.output.strip().splitlines()[-1]
        with Session(self.engine) as session:
            target_id = session.scalars(
                select(m.ComputeTarget.id).where(m.ComputeTarget.name == name)
            ).one()
        return Target(str(target_id), name, token)

    def body(
        self,
        target: Target,
        attacks: list[dict[str, Any]],
        *,
        gradient: bool = True,
        **changes: Any,
    ) -> dict[str, Any]:
        w = self.world
        body: dict[str, Any] = {
            "schema_version": 1,
            "protocol_id": DEV_OPEN,
            "model_version_id": w.model_id if gradient else w.random_model_id,
            "slice_id": w.slice_id,
            "class_mapping_id": w.mapping_id if gradient else w.random_mapping_id,
            "compute_target_id": target.id,
            "attacks": attacks,
            "limit": {"kind": "time", "value": "7200"},
        }
        body.update(changes)
        return body

    def profile(self, target: Target, *, sec: float, batch: int, attacks: Sequence[str]) -> None:
        """Cost profile qua API nội bộ của worker (bỏ qua calibration)."""
        client = WorkerClient(TestClient(self.app()), target.token, sleep=lambda _s: None)
        for name in attacks:
            client.cost_profile(
                CostProfile.model_validate(
                    {
                        "compute_target_id": target.id, "model_version_id": self.world.model_id,
                        "attack_spec_id": spec_id(name), "sec_per_image": sec,
                        "peak_vram_mb": 0, "batch_size": batch,
                        "measured_at": T0.isoformat(),
                        "environment": {"compute_target_id": target.id, "gpu_model": None,
                                        "cuda_version": None, "driver_version": None},
                    }
                )
            )  # fmt: skip

    def work(
        self, target: Target, experiment_id: str, *, on_batch: BatchHook | None = None,
        heartbeat: float = 3600,
    ) -> None:  # fmt: skip
        """Worker thật nhận đúng experiment này và chạy tới khi xong, dừng hoặc bị hủy."""
        runner = JobRunner(
            WorkerClient(TestClient(self.app()), target.token, sleep=lambda _s: None),
            JobCache(self.tmp / f"cache-{uuid.uuid4().hex[:6]}"),
            "cpu",
            url_http=httpx.Client(timeout=120),
            heartbeat_interval_s=heartbeat,
            clock=self.clock,
            on_batch=on_batch,
            perturbation_factory=self.perturbation_factory,
            provenance=self.provenance,
        )
        lease = runner.client.lease()
        assert lease is not None and str(lease.experiment_id) == experiment_id
        runner.run_lease(lease)


@pytest.fixture
def api(
    app_engine: Engine, buckets: Buckets, cli_env: dict[str, str], world: World, tmp_path: Path
) -> Api:
    return Api(app_engine, buckets, cli_env, world, tmp_path)
