"""Fixture cho test nghiệm thu Phase 8 (validation.md Phase 8, Automated Tests).

Test hệ thống (marker `db`, `make test-db`) dùng lại hạ tầng của Phase 5: DB tạm đã migrate và seed,
MinIO, API thật qua TestClient (đồng hồ giả), worker CPU thật `JobRunner`, fixture KITTI 5 ảnh và
YOLOv8n. Thêm bucket `reports` và nối `get_report_stores` vào MinIO của test.

Experiment được tạo qua API công khai và chạy bằng worker thật; failure case được worker làm mờ thật
(Phase 6), nên case bắt buộc hiển thị bình thường và gửi duyệt được. Tình huống khó tạo được dựng
bằng cách can thiệp đúng chỗ trong worker (attack lỗi khi dựng, thời gian xử lý vượt giới hạn,
working tree có thay đổi chưa commit), không ghi thẳng vào DB.

Protocol mặc định: FGSM quét lưới eps 2 và 4 (mức sụt tương đối mAP@0.5 trên slice fixture khoảng
0.34 và 0.57, xem conftest Phase 7), tiêu chí sụt tối đa 0.9 tại eps 4 (đạt), 2 case bắt buộc mỗi
attack.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.orm import Session

from advertest_contracts.models import ExperimentDetail
from advertest_worker import job as job_module
from attacks.registry import get_spec, load_catalog
from backend.app.api import public
from backend.app.db import models as m
from backend.app.reports import service as report_service
from backend.app.storage import (
    BUCKET_ARTIFACTS,
    BUCKET_DATASETS,
    BUCKET_MODELS,
    BUCKET_REPORTS,
    Buckets,
    make_s3_client,
)
from ml_core.runner import env as env_module
from ml_core.runner import run as run_module

from ._phase05 import load

P5 = load()

# Hạ tầng của Phase 5 (seed, dữ liệu fixture); DB dựng như Phase 7 (`owner_engine` bên dưới).
alembic_config = P5.alembic_config
app_engine = P5.app_engine
cli_env = P5.cli_env
world = P5.world
fresh_fingerprint = P5.fresh_fingerprint
Target = P5.Target
post = P5.post
ok = P5.ok
error = P5.error
DEV_OPEN = P5.DEV_OPEN
LEVELS = [2.0, 4.0]
CASES_PER_ATTACK = 2
APPROVE: dict[str, Any] = {
    "decision": "approve",
    "model_verdict": "meets_criteria",
    "conclusion": "Bài test làm đúng protocol; FGSM eps 4 dưới ngưỡng sụt.",
    "mitigation": "Theo dõi FGSM ở eps lớn hơn trong lần kiểm thử sau.",
}
VERDICT: dict[str, Any] = {"severity": "minor", "kind": "acceptable", "mitigation": None}


@pytest.fixture(scope="session")
def owner_engine(alembic_config: Config) -> Iterator[Engine]:
    """DB sạch bằng `DROP OWNED BY` rồi `upgrade head` (như Phase 7): chạy chung phiên sau Phase 6,
    `downgrade base` vướng run trỏ tới spec của migration 0006 (Phase 8 task 37)."""
    engine = create_engine(P5.env("ADVERTEST_TEST_OWNER_URL"))
    with engine.begin() as conn:
        conn.execute(text("DROP OWNED BY advertest_owner"))
    command.upgrade(alembic_config, "head")
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def buckets(cli_env: dict[str, str]) -> Buckets:
    """Như Phase 5, thêm bucket `reports`; xóa object của phase trước (DB vừa dựng lại)."""
    client = make_s3_client(
        cli_env["MINIO_ENDPOINT"], cli_env["MINIO_ACCESS_KEY"], cli_env["MINIO_SECRET_KEY"]
    )
    raw: Any = client
    existing = {b["Name"] for b in raw.list_buckets().get("Buckets", [])}
    for name in (BUCKET_MODELS, BUCKET_DATASETS, BUCKET_ARTIFACTS, BUCKET_REPORTS):
        if name not in existing:
            raw.create_bucket(Bucket=name)
            continue
        for page in raw.get_paginator("list_objects_v2").paginate(Bucket=name):
            keys = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
            if keys:
                raw.delete_objects(Bucket=name, Delete={"Objects": keys})
    return Buckets.from_client(client)


def stores(buckets: Buckets) -> report_service.Stores:
    return report_service.Stores(
        read_artifact=buckets.artifacts.get, put=buckets.reports.put, get=buckets.reports.get
    )


Api = P5.Api


@pytest.fixture
def report_stores(buckets: Buckets) -> dict[str, report_service.Stores]:
    """Kho report mà mọi app tạo trong test dùng (thay được để ép lỗi khi lưu)."""
    return {"current": stores(buckets)}


@pytest.fixture(autouse=True)
def report_app(monkeypatch: pytest.MonkeyPatch, report_stores: dict[str, Any]) -> None:
    """`P5.Api.app()` dựng app bằng `create_app` của module Phase 5: bọc lại để nối kho report
    (`get_report_stores` mặc định đọc biến môi trường MinIO của bản triển khai)."""
    original = P5.create_app

    def create_app() -> FastAPI:
        app: FastAPI = original()
        app.dependency_overrides[public.get_report_stores] = lambda: report_stores["current"]
        return app

    monkeypatch.setattr(P5, "create_app", create_app)


@pytest.fixture
def api(
    app_engine: Engine, buckets: Buckets, cli_env: dict[str, str], world: Any, tmp_path: Any
) -> Any:
    return P5.Api(app_engine, buckets, cli_env, world, tmp_path)


# ---------------------------------------------------------------- protocol


def required_grid(name: str, levels: list[float]) -> dict[str, Any]:
    spec = get_spec(load_catalog(), name=name)
    return {
        "attack_spec_name": name,
        "spec_sha256": spec.spec_sha256,
        "mode": "grid",
        "grid": {"levels": levels},
    }


def max_drop(name: str, level: float, threshold: float = 0.9, **extra: Any) -> dict[str, Any]:
    return {
        "kind": "max_drop_at_level",
        "attack_spec_name": name,
        "level": level,
        "threshold_kind": "relative_drop",
        "threshold": threshold,
        "class_filter": None,
        **extra,
    }


def protocol_body(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "description": "Kiểm thử nghiệm thu Phase 8: FGSM quét lưới.",
        "required_attacks": [required_grid("fgsm", LEVELS)],
        "min_slice_size": 5,
        "pass_criteria": [max_drop("fgsm", 4.0)],
        "cases_to_review_per_attack": CASES_PER_ATTACK,
        "forbid_dirty_runs": True,
    }
    body.update(changes)
    return body


def unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------- luồng


def detail(client: TestClient, experiment_id: str) -> ExperimentDetail:
    response = client.get(f"/experiments/{experiment_id}")
    assert response.status_code == 200, response.text
    return ExperimentDetail.model_validate(response.json())


def runs_of(client: TestClient, experiment_id: str) -> list[dict[str, Any]]:
    response = client.get(f"/experiments/{experiment_id}/runs")
    assert response.status_code == 200, response.text
    runs: list[dict[str, Any]] = response.json()
    return runs


def audit_count(engine: Engine, action: str, entity_id: UUID | str) -> int:
    with Session(engine) as session:
        rows = session.scalars(
            select(m.AuditLog).where(
                m.AuditLog.action == action, m.AuditLog.entity_id == UUID(str(entity_id))
            )
        ).all()
    return len(rows)


@dataclass
class Flow:
    """Một reviewer tạo protocol; một engineer chạy experiment theo protocol đó bằng worker thật."""

    api: Any
    reviewer_id: UUID
    reviewer: TestClient
    owner_id: UUID
    owner_email: str
    owner: TestClient
    target: Any
    protocol: dict[str, Any]
    experiments: list[str] = field(default_factory=list)

    def experiment(
        self,
        *,
        attacks: list[dict[str, Any]] | None = None,
        protocol_id: str | None = None,
        run: bool = True,
        **changes: Any,
    ) -> str:
        attacks = attacks if attacks is not None else [P5.attack("fgsm", LEVELS)]
        body = self.api.body(
            self.target, attacks, protocol_id=protocol_id or self.protocol["id"], **changes
        )
        created = ok(post(self.owner, "/experiments", body)).json()
        experiment_id: str = created["id"]
        self.experiments.append(experiment_id)
        if run:
            self.api.work(self.target, experiment_id)
            assert detail(self.owner, experiment_id).status == "completed"
        return experiment_id

    def submit(self, experiment_id: str, **body: Any) -> httpx.Response:
        response: httpx.Response = post(self.owner, f"/experiments/{experiment_id}/submit", body)
        return response

    def claim(self, experiment_id: str, client: TestClient | None = None) -> httpx.Response:
        response: httpx.Response = post(client or self.reviewer, f"/reviews/{experiment_id}/claim")
        return response

    def required_cases(self, experiment_id: str) -> list[str]:
        review = detail(self.reviewer, experiment_id).review
        assert review is not None
        return [str(c.failure_case_id) for c in review.required_cases]

    def verdict(
        self, experiment_id: str, case_id: str, client: TestClient | None = None, **body: Any
    ) -> httpx.Response:
        response: httpx.Response = post(
            client or self.reviewer,
            f"/reviews/{experiment_id}/cases/{case_id}/verdicts",
            {**VERDICT, **body},
        )
        return response

    def review_all(self, experiment_id: str) -> None:
        for case_id in self.required_cases(experiment_id):
            assert self.verdict(experiment_id, case_id).status_code == 201

    def decide(
        self, experiment_id: str, client: TestClient | None = None, **body: Any
    ) -> httpx.Response:
        response: httpx.Response = post(
            client or self.reviewer, f"/reviews/{experiment_id}/decision", body
        )
        return response

    def submitted(self, **changes: Any) -> str:
        experiment_id = self.experiment(**changes)
        ok(self.submit(experiment_id))
        return experiment_id

    def in_review(self, **changes: Any) -> str:
        experiment_id = self.submitted(**changes)
        ok(self.claim(experiment_id))
        return experiment_id

    def approved(self, **changes: Any) -> str:
        experiment_id = self.in_review(**changes)
        self.review_all(experiment_id)
        ok(self.decide(experiment_id, **APPROVE))
        return experiment_id


@pytest.fixture
def flow(api: Any) -> Flow:
    reviewer_id, _, reviewer = api.user("reviewer")
    owner_id, owner_email, owner = api.user("engineer")
    target = api.target()
    api.profile(target, sec=0.05, batch=5, attacks=["fgsm"])
    protocol = ok(
        post(reviewer, "/protocols", {"name": unique("p8"), "body": protocol_body()})
    ).json()
    return Flow(api, reviewer_id, reviewer, owner_id, owner_email, owner, target, protocol)


# ---------------------------------------------------------------- can thiệp worker


@pytest.fixture
def fail_first_build(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Lần dựng attack đầu tiên lỗi (giả lập hết bộ nhớ): run đó `failed`, run khác chạy tiếp."""
    calls: list[str] = []
    original = job_module.build_perturbation

    def flaky(spec: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append(spec.name)
        if len(calls) == 1:
            raise RuntimeError("Giả lập hết bộ nhớ khi dựng attack")
        return original(spec, *args, **kwargs)

    monkeypatch.setattr(job_module, "build_perturbation", flaky)
    return calls


@pytest.fixture
def dirty_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    """Worker chạy từ working tree có thay đổi chưa commit."""
    commit = uuid.uuid4().hex + uuid.uuid4().hex[:8]
    state = env_module.GitState(commit=commit, dirty=True)
    # Worker lấy git cho fingerprint (`job.git_state`); RunExecutor lấy cho manifest.
    monkeypatch.setattr(job_module, "git_state", lambda: state)
    monkeypatch.setattr(run_module, "git_state", lambda: state)
