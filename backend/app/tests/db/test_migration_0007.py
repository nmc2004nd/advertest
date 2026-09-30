"""Migration 0007 (Phase 6): bảng patches, cột mới của cost_profiles, failure_cases, runs."""

from __future__ import annotations

import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.db


def test_downgrade_and_upgrade_0007(alembic_config: Config, owner_engine: Engine) -> None:
    command.downgrade(alembic_config, "0006")
    try:
        assert "patches" not in inspect(owner_engine).get_table_names()
    finally:
        command.upgrade(alembic_config, "head")
    columns = {
        table: {c["name"] for c in inspect(owner_engine).get_columns(table)}
        for table in ("cost_profiles", "failure_cases", "runs", "patches")
    }
    assert "sec_per_image_iteration" in columns["cost_profiles"]
    assert {"anonymization", "perturbation_kind"} <= columns["failure_cases"]
    assert {"phase", "iterations_done", "iterations_total"} <= columns["runs"]
    assert {"key", "artifact", "checkpoint_key"} <= columns["patches"]


def test_patch_cannot_be_done_and_have_checkpoint(owner_engine: Engine) -> None:
    with owner_engine.connect() as conn:
        spec_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO attack_specs (id, name, version, kind, access, spec, spec_sha256)"
                " VALUES (:id, :name, 1, 'attack', 'white_box', '{}'::jsonb, :sha)"
            ),
            {"id": spec_id, "name": f"p{spec_id.hex[:8]}", "sha": uuid.uuid4().hex * 2},
        )
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO patches (key, attack_spec_id, area_ratio, artifact,"
                    " checkpoint_key) VALUES (:key, :spec, 0.1, '{}'::jsonb, 'patches/x/c.npz')"
                ),
                {"key": "d" * 64, "spec": spec_id},
            )
        conn.rollback()
