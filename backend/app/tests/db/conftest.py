"""Fixture cho test cần Postgres thật. Chạy bằng `make test-db` (tự dựng container Postgres).

Biến môi trường:
    ADVERTEST_TEST_OWNER_URL: kết nối bằng advertest_owner (chạy migration, tạo dữ liệu mẫu)
    ADVERTEST_TEST_APP_URL:   kết nối bằng advertest_app (kiểm tra quyền)
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from advertest_contracts.enums import Role, UserStatus
from backend.app.db import models as m
from backend.app.storage import (
    BUCKET_ARTIFACTS,
    BUCKET_DATASETS,
    BUCKET_MODELS,
    BUCKET_REPORTS,
    Buckets,
    make_s3_client,
)

ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"


def _url(name: str) -> str:
    url = os.environ.get(name)
    if not url:
        raise RuntimeError(f"Thiếu {name}. Chạy test DB bằng `make test-db`.")
    return url


@pytest.fixture(scope="session")
def alembic_config() -> Config:
    config = Config(str(ALEMBIC_INI))
    config.attributes["url"] = _url("ADVERTEST_TEST_OWNER_URL")
    return config


@pytest.fixture(scope="session")
def owner_engine(alembic_config: Config) -> Iterator[Engine]:
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    engine = create_engine(_url("ADVERTEST_TEST_OWNER_URL"))
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def app_engine(owner_engine: Engine) -> Iterator[Engine]:
    engine = create_engine(_url("ADVERTEST_TEST_APP_URL"))
    yield engine
    engine.dispose()


@pytest.fixture
def db(app_engine: Engine) -> Iterator[Session]:
    """Session bằng role advertest_app (kiểm tra luôn quyền); commit khi test xong."""
    with Session(app_engine) as session, session.begin():
        yield session


def make_user(session: Session, *, role: Role | None = Role.ADMIN, active: bool = True) -> m.User:
    tag = uuid.uuid4().hex[:8]
    user = m.User(
        email=f"user-{tag}@x.test",
        full_name="U",
        password_hash="x",
        status=UserStatus.ACTIVE if active else UserStatus.PENDING,
    )
    session.add(user)
    session.flush()
    if role is not None:
        session.add(m.UserRole(user_id=user.id, role=role))
        session.flush()
    return user


@pytest.fixture
def admin(db: Session) -> m.User:
    return make_user(db)


@pytest.fixture(scope="session")
def buckets() -> Buckets:
    """MinIO tạm của `make test-db`, đủ 4 bucket mà backend dùng."""
    client = make_s3_client(
        _url("ADVERTEST_TEST_MINIO_ENDPOINT"),
        _url("ADVERTEST_TEST_MINIO_ACCESS_KEY"),
        _url("ADVERTEST_TEST_MINIO_SECRET_KEY"),
    )
    raw: Any = client
    existing = {b["Name"] for b in raw.list_buckets().get("Buckets", [])}
    for name in (BUCKET_MODELS, BUCKET_DATASETS, BUCKET_ARTIFACTS, BUCKET_REPORTS):
        if name not in existing:
            raw.create_bucket(Bucket=name)
    return Buckets.from_client(client)
