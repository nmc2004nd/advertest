"""Fixture cho golden Phase R1.

- Đường CLI (`test_golden_cli.py`) không cần fixture ở đây.
- Đường worker (`test_golden_worker.py`, marker `db`): dùng lại world của Phase 6 (qua đó là hạ tầng
  Phase 5: DB tạm, MinIO, API thật qua TestClient, worker CPU thật `JobRunner`). DB được dựng sạch
  bằng `DROP OWNED BY` như Phase 7 (chạy chung phiên sau các phase khác).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

from . import golden
from ._phase06 import load

P6 = load()
P5 = P6.P5

alembic_config = P5.alembic_config
app_engine = P5.app_engine
cli_env = P5.cli_env
buckets = P5.buckets
world = P6.world
pinned_threads = golden.pinned_threads


@pytest.fixture(scope="session")
def owner_engine(alembic_config: Config) -> Iterator[Engine]:
    engine = create_engine(P5.env("ADVERTEST_TEST_OWNER_URL"))
    with engine.begin() as conn:
        conn.execute(text("DROP OWNED BY advertest_owner"))
    command.upgrade(alembic_config, "head")
    yield engine
    engine.dispose()
