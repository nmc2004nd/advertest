"""LiveChecks kết nối được Postgres thật bằng role advertest_app."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine

from backend.app.api.health import LiveChecks

pytestmark = pytest.mark.db


def test_postgres_check_ok(app_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", app_engine.url.render_as_string(hide_password=False))
    assert LiveChecks().postgres().ok is True
