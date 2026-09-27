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
