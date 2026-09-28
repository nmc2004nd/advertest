"""Nghiệm thu Phase 1, mục Chung (validation.md)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from advertest_contracts.hashing import sha256_of
from advertest_contracts.models import DatasetManifest, IgnoreRegion
from advertest_contracts.registry import SCHEMAS
from ml_core.cli import app

REPO = Path(__file__).resolve().parents[3]
PHASE0_FIXTURE_SHA = "9f5b413eb8a78a6a4b216011c2cf26e5b877728f7a160bbb80964a917d976069"


@pytest.mark.parametrize(
    "schema", ["model_card", "clean_eval_result", "slice_spec", "class_mapping"]
)
def test_new_schema_mocks_validate(schema: str) -> None:
    mocks = sorted((REPO / "contracts" / "mocks" / schema).glob("*.json"))
    assert mocks, f"Thiếu mock cho {schema}"
    for path in mocks:
        SCHEMAS[schema].model_validate_json(path.read_text())


def test_ignore_region_accepts_difficulty_and_fixture_hash_unchanged() -> None:
    IgnoreRegion(image_id="000001", bbox=(0, 0, 10, 10), source="difficulty:Car")
    manifest = DatasetManifest.model_validate(
        json.loads((REPO / "tests" / "fixtures" / "manifest.json").read_text())
    )
    assert sha256_of(manifest) == PHASE0_FIXTURE_SHA


def test_help_lists_command_groups() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for group in ("model", "dataset", "slice", "mapping", "eval", "viz"):
        assert group in result.stdout
