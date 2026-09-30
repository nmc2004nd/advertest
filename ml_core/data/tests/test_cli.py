import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from advertest_contracts.ids import content_id
from advertest_contracts.models import ClassMapping, SliceSpec
from ml_core.cli import app
from ml_core.data.tests.kitti_factory import label_line, make_kitti
from ml_core.data.tests.test_mapping_slice import WEIGHTS_SHA, model_card
from ml_core.store import LocalStore, register_id, resolve_id

runner = CliRunner()


@pytest.fixture
def env(tmp_path: Path) -> tuple[Path, Path]:
    root = make_kitti(
        tmp_path / "kitti",
        {
            "000001": [label_line("Car", (10, 2, 40, 38))],
            "000002": [label_line("Pedestrian", (5, 2, 15, 39))],
            "000003": [label_line("Tram", (5, 2, 15, 39))],
        },
    )
    store_dir = tmp_path / "store"
    store = LocalStore(store_dir)
    store.put(f"models/{WEIGHTS_SHA}/card.json", model_card().model_dump_json().encode())
    register_id(store, "model", WEIGHTS_SHA)
    return root, store_dir


def _invoke(store_dir: Path, *args: str) -> str:
    result = runner.invoke(app, ["--store-dir", str(store_dir), *args])
    assert result.exit_code == 0, result.output
    return result.stdout


def test_full_flow(env: tuple[Path, Path]) -> None:
    root, store_dir = env
    imported = json.loads(_invoke(store_dir, "dataset", "import-kitti", "--root", str(root)))
    sha = imported["dataset_version_sha256"]
    assert imported["id"] == str(content_id(sha))
    assert imported["num_images"] == 3
    again = json.loads(_invoke(store_dir, "dataset", "import-kitti", "--root", str(root)))
    assert again["dataset_version_sha256"] == sha

    spec = SliceSpec.model_validate_json(
        _invoke(store_dir, "slice", "create", "--dataset", sha, "--size", "2", "--seed", "7")
    )
    assert spec.image_ids == ["000001", "000002"]
    store = LocalStore(store_dir)
    assert resolve_id(store, "slice", spec.id) == spec.slice_sha256
    # Phase 6 (plan task 20a): slice 1 ảnh, rồi slice không giao với nó (fixture có 2 ảnh hợp lệ).
    single = SliceSpec.model_validate_json(
        _invoke(store_dir, "slice", "create", "--dataset", sha, "--size", "1", "--seed", "1")
    )
    other = SliceSpec.model_validate_json(
        _invoke(
            store_dir, "slice", "create", "--dataset", sha, "--size", "1",
            "--exclude-slice", str(single.id),
        )
    )  # fmt: skip
    assert set(other.image_ids) | set(single.image_ids) == {"000001", "000002"}
    assert not set(other.image_ids) & set(single.image_ids)

    model_id = str(content_id(WEIGHTS_SHA))
    mapping = ClassMapping.model_validate_json(
        _invoke(store_dir, "mapping", "create", "--dataset", sha, "--model", model_id)
    )
    assert mapping.preset == "kitti-coco" and mapping.dataset_version_sha256 == sha
    assert resolve_id(store, "mapping", mapping.id) == mapping.mapping_sha256


@pytest.mark.parametrize(
    "args",
    [
        ["slice", "create", "--dataset", "c" * 64],
        ["slice", "create", "--dataset", "c" * 64, "--preset", "voc"],
        ["mapping", "create", "--dataset", "c" * 64, "--model", str(content_id(WEIGHTS_SHA))],
    ],
)
def test_errors_are_reported_cleanly(env: tuple[Path, Path], args: list[str]) -> None:
    _, store_dir = env
    result = runner.invoke(app, ["--store-dir", str(store_dir), *args])
    assert result.exit_code == 1
    assert result.stderr.startswith("Lỗi:")


def test_slice_too_large_reported(env: tuple[Path, Path]) -> None:
    root, store_dir = env
    sha = json.loads(_invoke(store_dir, "dataset", "import-kitti", "--root", str(root)))[
        "dataset_version_sha256"
    ]
    result = runner.invoke(
        app, ["--store-dir", str(store_dir), "slice", "create", "--dataset", sha, "--size", "3"]
    )
    assert result.exit_code == 1 and "không đủ" in result.stderr
