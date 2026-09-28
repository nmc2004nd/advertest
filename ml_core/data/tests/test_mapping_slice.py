import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pytest

from advertest_contracts.hashing import sha256_of
from advertest_contracts.ids import content_id
from advertest_contracts.models import (
    ClassMapping,
    DatasetManifest,
    GradientCheck,
    LibVersions,
    ModelCard,
    SliceFilter,
    SliceSpec,
)
from ml_core.data.kitti import import_kitti
from ml_core.data.mapping import (
    MappedImage,
    apply_mapping,
    build_mapping,
    load_mapping,
    save_mapping,
)
from ml_core.data.slice import create_slice, load_slice, preset_filter, save_slice
from ml_core.data.tests.kitti_factory import label_line, make_kitti
from ml_core.store import LocalStore, resolve_id

WEIGHTS_SHA = "b" * 64
FIXTURE_MANIFEST = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "manifest.json"


def model_card(class_names: list[str] | None = None) -> ModelCard:
    return ModelCard(
        id=content_id(WEIGHTS_SHA),
        name="test",
        framework="ultralytics",
        architecture="yolov8n",
        weights_sha256=WEIGHTS_SHA,
        class_names=class_names or ["person", "bicycle", "car", "motorcycle", "bus", "truck"],
        input_size=640,
        supports_gradients=True,
        gradient_check=GradientCheck(passed=True, checked_at=datetime.now(UTC)),
        lib_versions=LibVersions(torch="t", art="a", ultralytics="u", torchmetrics="m", numpy="n"),
    )


def fixture_manifest() -> DatasetManifest:
    return DatasetManifest.model_validate(json.loads(FIXTURE_MANIFEST.read_text()))


@pytest.fixture
def manifest(tmp_path: Path) -> DatasetManifest:
    root = make_kitti(
        tmp_path / "kitti",
        {
            # Ảnh có GT hợp lệ của mọi loại cần kiểm.
            "000001": [
                label_line("Van", (0, 0, 30, 35)),
                label_line("Person_sitting", (30, 0, 40, 35)),
                label_line("Cyclist", (40, 0, 60, 35)),
                label_line("DontCare", (60, 0, 70, 10)),
            ],
            # Ngưỡng độ khó: cao 20 px; occluded 2; truncated 0.5; cao 30, occ 1, trunc 0.2 (giữ).
            "000002": [
                label_line("Car", (0, 0, 10, 20)),
                label_line("Car", (10, 0, 20, 35), occluded=2),
                label_line("Car", (20, 0, 30, 35), truncated=0.5),
                label_line("Car", (30, 0, 40, 30), truncated=0.2, occluded=1),
            ],
            # Chỉ có object dưới mức Moderate.
            "000003": [label_line("Car", (0, 0, 10, 20)), label_line("Pedestrian", (0, 0, 5, 24))],
            # Chỉ có class không map.
            "000004": [label_line("Tram", (0, 0, 50, 39))],
            # Biên: cao đúng 25, occluded 1, truncated 0.30 (giữ).
            "000005": [label_line("Truck", (0, 0, 40, 25), truncated=0.30, occluded=1)],
        },
    )
    return import_kitti(root)


def mapped(manifest: DatasetManifest) -> dict[str, MappedImage]:
    mapping = build_mapping(sha256_of(manifest), model_card(), "kitti-coco")
    return apply_mapping(manifest, mapping)


def test_mapping_classes_and_unmapped(manifest: DatasetManifest) -> None:
    img = mapped(manifest)["000001"]
    assert img.classes == ["car", "person"]  # Van → car, Person_sitting → person
    assert img.ignore_sources == ["dont_care", "unmapped:Cyclist"]
    assert img.boxes.shape == (2, 4) and img.ignore_boxes.shape == (2, 4)


def test_difficulty_thresholds(manifest: DatasetManifest) -> None:
    img = mapped(manifest)["000002"]
    assert img.classes == ["car"]
    assert img.boxes.tolist() == [[30, 0, 40, 30]]
    assert img.ignore_sources == ["difficulty:Car"] * 3


def test_difficulty_threshold_boundary_is_kept(manifest: DatasetManifest) -> None:
    img = mapped(manifest)["000005"]
    assert img.classes == ["truck"] and img.ignore_sources == []


def test_unmapped_only_image(manifest: DatasetManifest) -> None:
    img = mapped(manifest)["000004"]
    assert img.classes == [] and img.ignore_sources == ["unmapped:Tram"]


def test_fixture_num_gt_after_mapping() -> None:
    manifest = fixture_manifest()
    result = apply_mapping(manifest, build_mapping(sha256_of(manifest), model_card(), "kitti-coco"))
    counts = Counter(c for img in result.values() for c in img.classes)
    assert counts == {"car": 14, "truck": 1, "person": 6}


def test_mapping_rejects_target_not_in_model(manifest: DatasetManifest) -> None:
    with pytest.raises(ValueError, match="truck"):
        build_mapping(sha256_of(manifest), model_card(["person", "car"]), "kitti-coco")


def test_mapping_rejects_unknown_preset(manifest: DatasetManifest) -> None:
    with pytest.raises(ValueError, match="Preset"):
        build_mapping(sha256_of(manifest), model_card(), "voc")


def test_mapping_id_is_deterministic(manifest: DatasetManifest) -> None:
    a = build_mapping(sha256_of(manifest), model_card(), "kitti-coco")
    b = build_mapping(sha256_of(manifest), model_card(), "kitti-coco")
    assert a.mapping_sha256 == b.mapping_sha256
    assert a.id == b.id == content_id(a.mapping_sha256)


def test_mapping_saved_and_valid(manifest: DatasetManifest, tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store")
    mapping = build_mapping(sha256_of(manifest), model_card(), "kitti-coco")
    save_mapping(store, mapping)
    raw = store.get(f"mappings/{mapping.mapping_sha256}.json")
    assert ClassMapping.model_validate_json(raw) == mapping
    assert load_mapping(store, mapping.mapping_sha256) == mapping
    assert resolve_id(store, "mapping", mapping.id) == mapping.mapping_sha256


def test_default_filter() -> None:
    f = preset_filter("kitti-coco")
    assert f.classes == ["Car", "Pedestrian", "Person_sitting", "Truck", "Van"]
    assert f.min_objects == 1 and f.difficulty is not None


def test_slice_default_filter_excludes_hard_and_unmapped_only(manifest: DatasetManifest) -> None:
    spec = create_slice(manifest, size=3, seed=0)
    assert spec.image_ids == ["000001", "000002", "000005"]


def test_every_slice_image_has_mapped_object(manifest: DatasetManifest) -> None:
    result = mapped(manifest)
    spec = create_slice(manifest, size=3, seed=1)
    assert all(result[i].classes for i in spec.image_ids)


def test_slice_too_large(manifest: DatasetManifest) -> None:
    with pytest.raises(ValueError, match="không đủ"):
        create_slice(manifest, size=4, seed=0)


def test_slice_seed_determinism() -> None:
    manifest = fixture_manifest()
    a = create_slice(manifest, size=3, seed=42)
    assert create_slice(manifest, size=3, seed=42).image_ids_sha256 == a.image_ids_sha256
    others = {create_slice(manifest, size=3, seed=s).image_ids_sha256 for s in range(1, 20)}
    assert others - {a.image_ids_sha256}  # có seed cho kết quả khác


def test_slice_ids_are_content_ids() -> None:
    spec = create_slice(fixture_manifest(), size=3, seed=42)
    assert spec.id == content_id(spec.slice_sha256)
    assert spec.image_ids_sha256 == sha256_of(spec.image_ids)
    assert spec.dataset_version_sha256 == sha256_of(fixture_manifest())


def test_same_ids_other_dataset_gives_other_slice(manifest: DatasetManifest) -> None:
    other = manifest.model_copy(
        update={"source": manifest.source.model_copy(update={"split": "other"})}
    )
    a, b = create_slice(manifest, size=3, seed=0), create_slice(other, size=3, seed=0)
    assert a.image_ids == b.image_ids
    assert a.slice_sha256 != b.slice_sha256 and a.id != b.id


def test_filter_threshold_changes_slice_hash(manifest: DatasetManifest) -> None:
    base = preset_filter("kitti-coco")
    assert base.difficulty is not None
    stricter = SliceFilter(
        classes=base.classes,
        difficulty=base.difficulty.model_copy(update={"min_height_px": 24}),
        min_objects=1,
    )
    a = create_slice(manifest, size=3, seed=0)
    b = create_slice(manifest, size=3, seed=0, slice_filter=stricter)
    assert a.slice_sha256 != b.slice_sha256


def test_slice_saved_and_valid(manifest: DatasetManifest, tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store")
    spec = create_slice(manifest, size=3, seed=0)
    save_slice(store, spec)
    assert SliceSpec.model_validate_json(store.get(f"slices/{spec.slice_sha256}.json")) == spec
    assert load_slice(store, spec.slice_sha256) == spec
    assert resolve_id(store, "slice", spec.id) == spec.slice_sha256
