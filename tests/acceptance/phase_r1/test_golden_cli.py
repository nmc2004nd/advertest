"""Golden Phase R1, đường CLI (`advertest run`, `ml_core/runner`): 9 spec của catalog x 2 level
trên slice 5 ảnh fixture (seed 42), CPU, batch 5. Không cần DB."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from advertest_contracts.models import Manifest, RunResult
from attacks.registry import get_spec, load_catalog
from ml_core.cli import app
from ml_core.fixtures import FIXTURES_DIR
from ml_core.store import LocalStore

from .golden import (
    COMMIT,
    GOLDEN_DIR,
    LEVELS,
    case_entry,
    check_or_record,
    run_entry,
    snapshot,
)

KITTI_ROOT = FIXTURES_DIR / "kitti"
WEIGHTS = FIXTURES_DIR / "yolov8n.pt"
GOLDEN = GOLDEN_DIR / "phase_r1_cli.json"


def _cli(store_dir: Path, *args: str) -> str:
    result = CliRunner().invoke(app, ["--store-dir", str(store_dir), *args])
    assert result.exit_code == 0, result.output
    return result.stdout


def _entry(name: str, levels: list[float]) -> dict[str, Any]:
    spec = get_spec(load_catalog(), name=name)
    return {
        "attack_spec_id": str(spec.id),
        "spec_sha256": spec.spec_sha256,
        "mode": "grid",
        "grid": {"levels": levels},
        "seed": 0,
    }


def _cases(store: LocalStore, result: RunResult) -> list[dict[str, Any]]:
    if not result.failure_case_ids:
        return []
    assert result.manifest_uri is not None
    prefix = result.manifest_uri.rsplit("/", 1)[0] + "/cases/"
    records = [json.loads(store.get(k)) for k in store.list(prefix) if k.endswith("/record.json")]
    by_id = {r["id"]: r for r in records}
    return [case_entry(by_id[str(i)], rank) for rank, i in enumerate(result.failure_case_ids)]


def _capture(tmp: Path) -> dict[str, Any]:
    assert WEIGHTS.is_file() and KITTI_ROOT.is_dir(), "Thiếu fixture: chạy `make fixtures`"
    store_dir = tmp / "store"

    def cli(*args: str) -> Any:
        return json.loads(_cli(store_dir, *args))

    sha = cli("dataset", "import-kitti", "--root", str(KITTI_ROOT))["dataset_version_sha256"]
    model = cli("model", "register", "--weights", str(WEIGHTS), "--name", "yolov8n-coco")
    slice_spec = cli("slice", "create", "--dataset", sha, "--size", "5", "--seed", "42")
    mapping = cli("mapping", "create", "--dataset", sha, "--model", model["id"])
    config = {
        "model_id": model["id"],
        "slice_id": slice_spec["id"],
        "mapping_id": mapping["id"],
        "attacks": [_entry(name, levels) for name, levels in LEVELS.items()],
        "device": "cpu",
        "batch_size": 5,
        "failure_cases_per_run": 3,
    }
    path = tmp / "golden.yaml"
    path.write_text(yaml.safe_dump(config))
    out = json.loads(_cli(store_dir, "run", "--config", str(path)))
    results = [RunResult.model_validate(r) for r in out]
    keys = [(name, float(level)) for name, levels in LEVELS.items() for level in levels]
    assert len(results) == len(keys)

    store = LocalStore(store_dir)
    runs: dict[str, dict[str, Any]] = {}
    for (name, level), result in zip(keys, results, strict=True):
        inputs = None
        if result.manifest_uri is not None:
            manifest = Manifest.model_validate_json(store.get(result.manifest_uri))
            inputs = manifest.fingerprint_inputs.model_dump(mode="json")
        runs[f"{name}@{level!r}"] = run_entry(
            status=result.status.value,
            reason=result.status_reason.code if result.status_reason else None,
            fingerprint=result.fingerprint,
            fingerprint_inputs=inputs,
            metrics=result.metrics.model_dump(mode="json") if result.metrics else None,
            cases=_cases(store, result),
        )
    return snapshot(runs)


@pytest.mark.usefixtures("pinned_threads")
def test_cli_runner_matches_golden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_COMMIT", COMMIT)
    monkeypatch.delenv("DOCKER_IMAGE_DIGEST", raising=False)
    check_or_record(_capture(tmp_path), GOLDEN)
