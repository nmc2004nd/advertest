"""Fixture cho test nghiệm thu Phase 1 (validation.md Phase 1).

Chạy trên CPU với fixture của Phase 0 (`make fixtures`): 5 ảnh KITTI kèm label gốc và YOLOv8n.
Luồng đầy đủ được dựng một lần mỗi phiên qua CLI `advertest`, trong một store tạm:
import-kitti → model register → slice create (5 ảnh, seed 42) → mapping create (kitti-coco).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from ml_core.cli import app
from ml_core.fixtures import FIXTURES_DIR

KITTI_ROOT = FIXTURES_DIR / "kitti"
WEIGHTS = FIXTURES_DIR / "yolov8n.pt"
GOLDEN = FIXTURES_DIR / "golden" / "phase_01.json"


def run_cli(store_dir: Path, *args: str) -> str:
    """Chạy `advertest --store-dir <store_dir> ...`, fail nếu mã thoát khác 0; trả stdout."""
    result = CliRunner().invoke(app, ["--store-dir", str(store_dir), *args])
    assert result.exit_code == 0, result.output
    return result.stdout


@dataclass(frozen=True)
class Pipeline:
    store_dir: Path
    dataset_sha256: str
    dataset_id: str
    model: dict[str, Any]
    slice: dict[str, Any]
    mapping: dict[str, Any]


@pytest.fixture(scope="session")
def pipeline(tmp_path_factory: pytest.TempPathFactory) -> Pipeline:
    assert WEIGHTS.is_file() and KITTI_ROOT.is_dir(), "Thiếu fixture: chạy `make fixtures`"
    store_dir = tmp_path_factory.mktemp("phase01") / "store"
    imported = json.loads(run_cli(store_dir, "dataset", "import-kitti", "--root", str(KITTI_ROOT)))
    sha = imported["dataset_version_sha256"]
    model = json.loads(
        run_cli(store_dir, "model", "register", "--weights", str(WEIGHTS), "--name", "yolov8n-coco")
    )
    slice_spec = json.loads(
        run_cli(store_dir, "slice", "create", "--dataset", sha, "--size", "5", "--seed", "42")
    )
    mapping = json.loads(
        run_cli(store_dir, "mapping", "create", "--dataset", sha, "--model", model["id"])
    )
    return Pipeline(store_dir, sha, imported["id"], model, slice_spec, mapping)


@pytest.fixture(scope="session")
def golden() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(GOLDEN.read_text())
    return data


@pytest.fixture
def git_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    """`eval` cần git commit; cố định để test không phụ thuộc trạng thái working tree."""
    monkeypatch.setenv("GIT_COMMIT", "0" * 40)
