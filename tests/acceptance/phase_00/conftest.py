"""Fixture cho test nghiệm thu Phase 0.

Test đánh dấu `db` cần Postgres và MinIO thật, chạy bằng `make test-db` (hoặc job acceptance của
CI). Biến môi trường: ADVERTEST_TEST_OWNER_URL, ADVERTEST_TEST_APP_URL,
ADVERTEST_TEST_MINIO_ENDPOINT, ADVERTEST_TEST_MINIO_ACCESS_KEY, ADVERTEST_TEST_MINIO_SECRET_KEY.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine

REPO = Path(__file__).resolve().parents[3]


def env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Thiếu {name}. Chạy test nghiệm thu cần DB bằng `make test-db`.")
    return value


@pytest.fixture(scope="session")
def repo() -> Path:
    return REPO


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
