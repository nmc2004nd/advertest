"""Migration 0008 (Phase 7): cột tìm ngưỡng của runs, mỗi (experiment, attack) một SearchResult."""

from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect

pytestmark = pytest.mark.db


def test_downgrade_and_upgrade_0008(alembic_config: Config, owner_engine: Engine) -> None:
    command.downgrade(alembic_config, "0007")
    try:
        columns = {c["name"] for c in inspect(owner_engine).get_columns("runs")}
        assert not {"scope", "search_order", "predictions_key"} & columns
    finally:
        command.upgrade(alembic_config, "head")
    inspector = inspect(owner_engine)
    runs = {c["name"]: c for c in inspector.get_columns("runs")}
    assert {"scope", "search_order", "predictions_key"} <= set(runs)
    assert not runs["scope"]["nullable"]
    checks = {c["name"] for c in inspector.get_check_constraints("runs")}
    assert {"ck_runs_scope_value", "ck_runs_subset_has_search_order"} <= checks
    indexes = {i["name"]: i for i in inspector.get_indexes("runs")}
    assert indexes["uq_runs_search_order"]["unique"]
    uniques = {u["name"] for u in inspector.get_unique_constraints("search_results")}
    assert "uq_search_results_experiment_attack" in uniques
    assert "updated_at" in {c["name"] for c in inspector.get_columns("search_results")}
