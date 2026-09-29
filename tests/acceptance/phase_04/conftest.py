"""Fixture cho test nghiệm thu Phase 4 (validation.md Phase 4, Automated Tests).

Mọi test ở đây cần Postgres thật (marker `db`; `make test-db` hoặc job acceptance của CI). Mỗi test
gọi API FastAPI thật qua TestClient với DB thật và đồng hồ giả; người dùng được tạo **qua API**
(yêu cầu truy cập rồi admin duyệt), không chèn thẳng vào DB. Mỗi client có IP gốc riêng (gửi qua
`X-Forwarded-For` từ proxy tin cậy) để giới hạn đăng nhập sai theo IP của test này không ảnh hưởng
test khác.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from advertest_contracts.models import ErrorResponse
from backend.admin_cli.seed import AdminAccount, seed
from backend.app.api.deps import get_clock, get_sessionmaker
from backend.app.db import models as m
from backend.app.main import create_app

REPO = Path(__file__).resolve().parents[3]
ADMIN_EMAIL = "admin-phase04@example.com"
ADMIN_PASSWORD = "mat-khau-admin-phase-04"
PASSWORD = "mat-khau-du-dai-1"
NEW_PASSWORD = "mat-khau-moi-dai-2"
T0 = datetime(2026, 9, 29, 8, 0, tzinfo=UTC)
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
SESSION_COOKIE = "advertest_session"


def env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Thiếu {name}. Chạy test nghiệm thu cần DB bằng `make test-db`.")
    return value


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
    # Tài khoản admin đầu tiên như khi triển khai (`python -m backend.admin_cli.seed`).
    seed(engine, AdminAccount(email=ADMIN_EMAIL, password=ADMIN_PASSWORD))
    yield engine
    engine.dispose()


class FakeClock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


def random_ip() -> str:
    raw = uuid.uuid4().bytes
    return f"10.{raw[0]}.{raw[1]}.{raw[2] or 1}"


def new_email(prefix: str = "u") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}@phase04.test"


@dataclass
class Api:
    engine: Engine
    clock: FakeClock = field(default_factory=FakeClock)

    def client(self, ip: str | None = None) -> TestClient:
        """Client mới (cookie riêng), IP gốc riêng qua proxy tin cậy."""
        app = create_app()
        factory = sessionmaker(self.engine)
        app.dependency_overrides[get_sessionmaker] = lambda: factory
        app.dependency_overrides[get_clock] = lambda: self.clock
        return TestClient(app, headers={"X-Forwarded-For": ip or random_ip()})

    def admin(self) -> TestClient:
        client = self.client()
        assert login(client, ADMIN_EMAIL, ADMIN_PASSWORD).status_code == 200
        return client

    def request_access(self, email: str, password: str = PASSWORD, role: str = "engineer") -> None:
        body = access_body(email, password, role)
        assert self.client().post("/auth/request-access", json=body).status_code == 202

    def user_id(self, email: str) -> uuid.UUID:
        with Session(self.engine) as session:
            return session.scalars(select(m.User.id).where(m.User.email == email.lower())).one()

    def create_user(
        self, *roles: str, status: str = "active", password: str = PASSWORD
    ) -> tuple[uuid.UUID, str]:
        """Người dùng qua luồng thật: yêu cầu truy cập, rồi admin duyệt/từ chối/vô hiệu hóa."""
        email = new_email()
        self.request_access(email, password, roles[0] if roles else "engineer")
        user_id = self.user_id(email)
        if status == "pending":
            return user_id, email
        admin = self.admin()
        if status == "rejected":
            ok(post(admin, f"/admin/users/{user_id}/reject", {"reason": "Không thuộc nhóm"}))
            return user_id, email
        ok(post(admin, f"/admin/users/{user_id}/approve", {"roles": list(roles or ["engineer"])}))
        if status == "disabled":
            ok(post(admin, f"/admin/users/{user_id}/disable"))
        return user_id, email

    def logged_in(self, *roles: str) -> tuple[uuid.UUID, str, TestClient]:
        user_id, email = self.create_user(*roles)
        client = self.client()
        ok(login(client, email))
        return user_id, email, client


@pytest.fixture
def api(app_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Api:
    # TestClient kết nối từ host "testclient": coi là proxy tin cậy để test chọn được IP gốc.
    monkeypatch.setenv("TRUSTED_PROXIES", "testclient")
    return Api(app_engine)


def access_body(email: str, password: str = PASSWORD, role: str = "engineer") -> dict[str, Any]:
    return {
        "full_name": "Người thử nghiệm",
        "email": email,
        "organization": "VinAI",
        "requested_role": role,
        "reason": "Kiểm thử Phase 4",
        "password": password,
    }


def login(client: TestClient, email: str, password: str = PASSWORD) -> httpx.Response:
    response: httpx.Response = client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    return response


def csrf(client: TestClient) -> dict[str, str]:
    return {CSRF_HEADER: client.cookies.get(CSRF_COOKIE) or ""}


def post(client: TestClient, path: str, body: Any = None) -> httpx.Response:
    response: httpx.Response = client.post(path, json=body, headers=csrf(client))
    return response


def put(client: TestClient, path: str, body: Any) -> httpx.Response:
    response: httpx.Response = client.put(path, json=body, headers=csrf(client))
    return response


def error(response: httpx.Response) -> tuple[int, str]:
    body = ErrorResponse.model_validate(response.json())
    return response.status_code, body.error.code


def ok(response: httpx.Response) -> httpx.Response:
    assert response.status_code < 300, (response.status_code, response.text)
    return response
