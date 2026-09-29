"""Migration chạy được hai chiều (chạy trước test_schema theo thứ tự file)."""

from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

pytestmark = pytest.mark.db


def test_upgrade_downgrade_upgrade(alembic_config: Config, owner_engine: Engine) -> None:
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")


def test_models_match_migrations(owner_engine: Engine) -> None:
    """Model ORM không lệch migration (tương đương `alembic check`)."""
    from alembic.autogenerate import compare_metadata
    from alembic.runtime.migration import MigrationContext

    from backend.app.db.models import Base

    with owner_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_dev_open_protocol_seeded(app_engine: Engine) -> None:
    from sqlalchemy import text

    with app_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id::text, status::text, created_by, body FROM protocols"
                " WHERE name = 'dev-open'"
            )
        ).one()
    assert row == ("2edcdef5-0d3a-5d5f-98ac-b02637fa6718", "dev", None, {})
