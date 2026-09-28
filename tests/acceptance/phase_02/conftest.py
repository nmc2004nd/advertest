"""Fixture cho test nghiệm thu Phase 2 (validation.md Phase 2).

Chạy trên CPU với fixture của Phase 0 (`make fixtures`): 5 ảnh KITTI kèm label và YOLOv8n.
Store tạm được dựng một lần mỗi phiên qua CLI `advertest` như Phase 1 (import-kitti → model
register → slice create 5 ảnh seed 42 → mapping create kitti-coco), rồi chạy một lần
`advertest run` cho cấu hình `SWEEP` bên dưới.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np
import pytest
import yaml
from typer.testing import CliRunner

from advertest_contracts.models import RunResult
from attacks.registry import get_spec, load_catalog
from ml_core.cli import app
from ml_core.data.loader import Batch, SliceLoader
from ml_core.fixtures import FIXTURES_DIR
from ml_core.runner.run import letterbox_mask
from ml_core.store import LocalStore

KITTI_ROOT = FIXTURES_DIR / "kitti"
WEIGHTS = FIXTURES_DIR / "yolov8n.pt"
GOLDEN = FIXTURES_DIR / "golden" / "phase_02.json"
COMMIT = "0" * 40
FAILURE_CASES = 3  # nhỏ hơn số ảnh (5) để kiểm tra giới hạn

SWEEP: dict[str, list[float]] = {
    "fgsm": [0, 4, 8],
    "pgd_linf": [0, 4, 8, 16],
    "pgd_l2": [0, 2],
}


def run_cli(store_dir: Path, *args: str, code: int = 0) -> Any:
    """Chạy `advertest --store-dir <store_dir> ...`, kiểm tra mã thoát; trả kết quả của Click."""
    result = CliRunner().invoke(app, ["--store-dir", str(store_dir), *args])
    assert result.exit_code == code, result.output
    return result


def attack_entry(name: str, levels: list[float], seed: int = 0) -> dict[str, Any]:
    spec = get_spec(load_catalog(), name=name)
    return {
        "attack_spec_id": str(spec.id),
        "spec_sha256": spec.spec_sha256,
        "mode": "grid",
        "grid": {"levels": levels},
        "seed": seed,
    }


@dataclass(frozen=True)
class Pipeline:
    store_dir: Path
    dataset_sha256: str
    model: dict[str, Any]
    slice: dict[str, Any]
    mapping: dict[str, Any]

    @property
    def store(self) -> LocalStore:
        return LocalStore(self.store_dir)

    def config(self, attacks: list[dict[str, Any]], **overrides: Any) -> dict[str, Any]:
        return {
            "model_id": self.model["id"],
            "slice_id": self.slice["id"],
            "mapping_id": self.mapping["id"],
            "attacks": attacks,
            "device": "cpu",
            "batch_size": 5,
            "failure_cases_per_run": FAILURE_CASES,
            **overrides,
        }

    def loader(self) -> SliceLoader:
        return SliceLoader.from_ids(self.store, UUID(self.slice["id"]), UUID(self.mapping["id"]))


def write_config(path: Path, config: dict[str, Any]) -> Path:
    path.write_text(yaml.safe_dump(config))
    return path


def run_results(stdout: str) -> list[RunResult]:
    return [RunResult.model_validate(item) for item in json.loads(stdout)]


@pytest.fixture(scope="session")
def pipeline(tmp_path_factory: pytest.TempPathFactory) -> Pipeline:
    assert WEIGHTS.is_file() and KITTI_ROOT.is_dir(), "Thiếu fixture: chạy `make fixtures`"
    store_dir = tmp_path_factory.mktemp("phase02") / "store"

    def cli(*args: str) -> Any:
        return json.loads(run_cli(store_dir, *args).stdout)

    sha = cli("dataset", "import-kitti", "--root", str(KITTI_ROOT))["dataset_version_sha256"]
    model = cli("model", "register", "--weights", str(WEIGHTS), "--name", "yolov8n-coco")
    slice_spec = cli("slice", "create", "--dataset", sha, "--size", "5", "--seed", "42")
    mapping = cli("mapping", "create", "--dataset", sha, "--model", model["id"])
    return Pipeline(store_dir, sha, model, slice_spec, mapping)


@dataclass(frozen=True)
class Sweep:
    config_path: Path
    config: dict[str, Any]
    results: dict[tuple[str, float], RunResult]
    stderr: str


@pytest.fixture(scope="session")
def sweep(pipeline: Pipeline, tmp_path_factory: pytest.TempPathFactory) -> Sweep:
    """Một lần `advertest run` cho mọi (attack, level) trong `SWEEP`, git commit cố định."""
    config = pipeline.config([attack_entry(name, levels) for name, levels in SWEEP.items()])
    path = write_config(tmp_path_factory.mktemp("sweep") / "sweep.yaml", config)
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("GIT_COMMIT", COMMIT)
        mp.delenv("DOCKER_IMAGE_DIGEST", raising=False)
        result = run_cli(pipeline.store_dir, "run", "--config", str(path))
    results = run_results(result.stdout)
    keys = [(name, float(level)) for name, levels in SWEEP.items() for level in levels]
    assert len(results) == len(keys)
    return Sweep(path, config, dict(zip(keys, results, strict=True)), result.stderr)


REPEAT = {"fgsm": [4], "pgd_linf": [4]}  # chạy lại với --force: so với golden và lần đầu


@dataclass(frozen=True)
class Rerun:
    results: dict[tuple[str, float], RunResult]
    original_hashes: dict[str, str]  # key result.json gốc → sha256 trước khi chạy lại


def _rerun(pipeline: Pipeline, sweep: Sweep, tmp: Path, batch_size: int) -> Rerun:
    config = pipeline.config(
        [attack_entry(name, levels) for name, levels in REPEAT.items()], batch_size=batch_size
    )
    path = write_config(tmp / f"rerun-b{batch_size}.yaml", config)
    store = pipeline.store
    keys = [(name, float(level)) for name, levels in REPEAT.items() for level in levels]
    originals = [f"runs/{sweep.results[k].fingerprint}/result.json" for k in keys]
    hashes = {key: hashlib.sha256(store.get(key)).hexdigest() for key in originals}
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("GIT_COMMIT", COMMIT)
        mp.delenv("DOCKER_IMAGE_DIGEST", raising=False)
        result = run_cli(pipeline.store_dir, "run", "--config", str(path), "--force")
    return Rerun(dict(zip(keys, run_results(result.stdout), strict=True)), hashes)


@pytest.fixture(scope="session")
def forced(pipeline: Pipeline, sweep: Sweep, tmp_path_factory: pytest.TempPathFactory) -> Rerun:
    """Chạy lại `REPEAT` với `--force`, cùng batch size 5 như lần đầu."""
    return _rerun(pipeline, sweep, tmp_path_factory.mktemp("forced"), batch_size=5)


@pytest.fixture(scope="session")
def batch1(pipeline: Pipeline, sweep: Sweep, tmp_path_factory: pytest.TempPathFactory) -> Rerun:
    """Chạy lại `REPEAT` với `--force` và batch size 1."""
    return _rerun(pipeline, sweep, tmp_path_factory.mktemp("batch1"), batch_size=1)


@pytest.fixture(scope="session")
def batch(pipeline: Pipeline) -> Batch:
    """Cả 5 ảnh fixture trong một batch letterbox (kèm ground truth và ignore region)."""
    return next(pipeline.loader().batches(5))


@pytest.fixture(scope="session")
def mask(batch: Batch) -> np.ndarray:
    return letterbox_mask(batch.infos)


@pytest.fixture(scope="session")
def golden() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(GOLDEN.read_text())
    return data


@pytest.fixture
def git_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_COMMIT", COMMIT)
    monkeypatch.delenv("DOCKER_IMAGE_DIGEST", raising=False)
