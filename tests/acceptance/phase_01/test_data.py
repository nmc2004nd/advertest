"""Nghiệm thu Phase 1, mục Dữ liệu (validation.md)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from advertest_contracts.hashing import sha256_of
from advertest_contracts.ids import content_id
from advertest_contracts.models import (
    ClassMapping,
    DatasetManifest,
    ModelCard,
    SliceFilter,
    SliceSpec,
)
from ml_core.data.kitti import import_kitti, parse_label_line
from ml_core.data.mapping import apply_mapping, build_mapping
from ml_core.data.slice import create_slice, preset_filter
from ml_core.store import LocalStore, resolve_id

from .conftest import KITTI_ROOT, Pipeline, run_cli

LINE = "Cyclist 0.81 1 2.77 1187.47 162.53 1241.00 305.70 1.60 0.88 1.93 7.87 1.48 8.18 -2.76"


def _label(
    category: str, box: tuple[float, float, float, float], trunc: float = 0.0, occ: int = 0
) -> str:
    left, top, right, bottom = box
    bbox = f"{left:.2f} {top:.2f} {right:.2f} {bottom:.2f}"
    return f"{category} {trunc:.2f} {occ} 0.00 {bbox} 1.5 1.6 3.7 1.0 1.5 20.0 0.1"


def _make_kitti(root: Path, labels: dict[str, list[str]]) -> Path:
    (root / "image_2").mkdir(parents=True)
    (root / "label_2").mkdir(parents=True)
    for i, (image_id, lines) in enumerate(sorted(labels.items())):
        Image.new("RGB", (300, 100), (i * 40 % 256, 90, 160)).save(
            root / "image_2" / f"{image_id}.png"
        )
        (root / "label_2" / f"{image_id}.txt").write_text("\n".join(lines) + "\n")
    return root


def _card(pipeline: Pipeline) -> ModelCard:
    return ModelCard.model_validate(pipeline.model)


def test_parser_reads_bbox_class_truncated_occluded() -> None:
    obj = parse_label_line(LINE)
    assert obj.category == "Cyclist"
    assert obj.truncated == pytest.approx(0.81)
    assert obj.occluded == 1
    assert obj.bbox == pytest.approx((1187.47, 162.53, 1241.00, 305.70))


def test_dont_care_is_ignore_region_not_annotation() -> None:
    manifest = import_kitti(KITTI_ROOT)
    assert all(a.category != "DontCare" for a in manifest.annotations)
    assert manifest.ignore_regions and all(r.source == "dont_care" for r in manifest.ignore_regions)


def test_kitti_coco_mapping(tmp_path: Path, pipeline: Pipeline) -> None:
    manifest = import_kitti(
        _make_kitti(
            tmp_path / "kitti",
            {
                "000001": [
                    _label("Van", (0, 0, 60, 90)),
                    _label("Person_sitting", (100, 0, 140, 90)),
                    _label("Cyclist", (200, 0, 260, 90)),
                ]
            },
        )
    )
    mapping = build_mapping(sha256_of(manifest), _card(pipeline), "kitti-coco")
    img = apply_mapping(manifest, mapping)["000001"]
    assert img.classes == ["car", "person"]
    assert img.ignore_sources == ["unmapped:Cyclist"]


def test_import_twice_same_hash(pipeline: Pipeline) -> None:
    again = json.loads(
        run_cli(pipeline.store_dir, "dataset", "import-kitti", "--root", str(KITTI_ROOT))
    )
    assert again["dataset_version_sha256"] == pipeline.dataset_sha256


def test_editing_one_label_line_changes_hash(tmp_path: Path) -> None:
    copy = tmp_path / "kitti"
    shutil.copytree(KITTI_ROOT, copy)
    before = sha256_of(import_kitti(copy))
    label = sorted((copy / "label_2").glob("*.txt"))[0]
    lines = label.read_text().splitlines()
    fields = lines[0].split()
    fields[4] = f"{float(fields[4]) + 1:.2f}"
    label.write_text("\n".join([" ".join(fields), *lines[1:]]) + "\n")
    assert sha256_of(import_kitti(copy)) != before


def test_slice_seed_determinism(pipeline: Pipeline) -> None:
    manifest = import_kitti(KITTI_ROOT)
    a = create_slice(manifest, size=3, seed=42)
    assert create_slice(manifest, size=3, seed=42).image_ids_sha256 == a.image_ids_sha256
    others = {create_slice(manifest, size=3, seed=s).image_ids_sha256 for s in range(1, 20)}
    assert others - {a.image_ids_sha256}


def test_every_default_slice_image_has_mapped_object(pipeline: Pipeline) -> None:
    manifest = import_kitti(KITTI_ROOT)
    mapped = apply_mapping(manifest, ClassMapping.model_validate(pipeline.mapping))
    assert pipeline.slice["image_ids"]
    assert all(mapped[i].classes for i in pipeline.slice["image_ids"])


def test_ids_are_uuid5_of_hashes(pipeline: Pipeline) -> None:
    assert pipeline.dataset_id == str(content_id(pipeline.dataset_sha256))
    assert pipeline.slice["id"] == str(content_id(pipeline.slice["slice_sha256"]))
    assert pipeline.mapping["id"] == str(content_id(pipeline.mapping["mapping_sha256"]))
    store = LocalStore(pipeline.store_dir)
    for kind, obj, sha in (
        ("slice", pipeline.slice, "slice_sha256"),
        ("mapping", pipeline.mapping, "mapping_sha256"),
    ):
        assert resolve_id(store, kind, content_id(obj[sha])) == obj[sha]


def test_same_image_ids_other_dataset_other_slice() -> None:
    manifest = import_kitti(KITTI_ROOT)
    other = manifest.model_copy(
        update={"source": manifest.source.model_copy(update={"split": "x"})}
    )
    a, b = create_slice(manifest, size=3, seed=0), create_slice(other, size=3, seed=0)
    assert a.image_ids == b.image_ids
    assert a.slice_sha256 != b.slice_sha256 and a.id != b.id


def test_import_fixture_manifest_valid(pipeline: Pipeline) -> None:
    store = LocalStore(pipeline.store_dir)
    raw = store.get(f"datasets/{pipeline.dataset_sha256}/manifest.json")
    manifest = DatasetManifest.model_validate_json(raw)
    assert len(manifest.images) == 5 and sha256_of(manifest) == pipeline.dataset_sha256


def test_moderate_difficulty_thresholds(tmp_path: Path, pipeline: Pipeline) -> None:
    manifest = import_kitti(
        _make_kitti(
            tmp_path / "kitti",
            {
                "000001": [
                    _label("Car", (0, 0, 40, 20)),  # cao 20 px
                    _label("Car", (50, 0, 90, 60), occ=2),
                    _label("Car", (100, 0, 140, 60), trunc=0.5),
                    _label("Car", (150, 0, 190, 30), trunc=0.2, occ=1),  # giữ
                ]
            },
        )
    )
    mapping = build_mapping(sha256_of(manifest), _card(pipeline), "kitti-coco")
    img = apply_mapping(manifest, mapping)["000001"]
    assert img.ignore_sources == ["difficulty:Car"] * 3
    assert img.classes == ["car"] and img.boxes.tolist() == [[150, 0, 190, 30]]


def test_image_with_only_hard_objects_not_in_default_slice(tmp_path: Path) -> None:
    manifest = import_kitti(
        _make_kitti(
            tmp_path / "kitti",
            {
                "000001": [_label("Car", (0, 0, 40, 20)), _label("Pedestrian", (50, 0, 60, 24))],
                "000002": [_label("Car", (0, 0, 40, 60))],
            },
        )
    )
    spec = create_slice(manifest, size=1, seed=0)
    assert spec.image_ids == ["000002"]
    with pytest.raises(ValueError):
        create_slice(manifest, size=2, seed=0)


def test_slice_without_model_and_threshold_changes_hash(pipeline: Pipeline) -> None:
    # slice create chạy được chỉ với --dataset (không có model hay mapping).
    out = run_cli(
        pipeline.store_dir, "slice", "create", "--dataset", pipeline.dataset_sha256, "--size", "3"
    )
    base = SliceSpec.model_validate_json(out)
    f = preset_filter("kitti-coco")
    assert f.difficulty is not None
    stricter = SliceFilter(
        classes=f.classes,
        difficulty=f.difficulty.model_copy(update={"max_occluded": 0}),
        min_objects=1,
    )
    manifest = import_kitti(KITTI_ROOT)
    other = create_slice(manifest, size=3, seed=42, slice_filter=stricter)
    assert other.slice_sha256 != base.slice_sha256


def test_stored_slice_and_mapping_validate(pipeline: Pipeline) -> None:
    store = LocalStore(pipeline.store_dir)
    stored: dict[str, Any] = {
        "slice": store.get(f"slices/{pipeline.slice['slice_sha256']}.json"),
        "mapping": store.get(f"mappings/{pipeline.mapping['mapping_sha256']}.json"),
    }
    SliceSpec.model_validate_json(stored["slice"])
    ClassMapping.model_validate_json(stored["mapping"])
