import json
from pathlib import Path

import pytest

from advertest_contracts.hashing import sha256_of
from advertest_contracts.ids import content_id
from advertest_contracts.models import DatasetManifest
from ml_core.data.dataset import dataset_roots, load_manifest, save_dataset
from ml_core.data.kitti import (
    KITTI_CLASSES,
    KittiLabelError,
    import_kitti,
    parse_label_line,
)
from ml_core.data.tests.kitti_factory import label_line, make_kitti
from ml_core.store import LocalStore, resolve_id

FIXTURE_LINE = (
    "Cyclist 0.81 1 2.77 1187.47 162.53 1241.00 305.70 1.60 0.88 1.93 7.87 1.48 8.18 -2.76"
)


def test_parse_label_line() -> None:
    obj = parse_label_line(FIXTURE_LINE)
    assert obj.category == "Cyclist"
    assert obj.truncated == pytest.approx(0.81)
    assert obj.occluded == 1
    assert obj.bbox == pytest.approx((1187.47, 162.53, 1241.00, 305.70))


@pytest.mark.parametrize("line", ["Car 0.0 0", "Bus " + FIXTURE_LINE[8:], "Car x 0 0 1 2 3 4"])
def test_parse_label_line_rejects(line: str) -> None:
    with pytest.raises(KittiLabelError):
        parse_label_line(line)


@pytest.fixture
def kitti_root(tmp_path: Path) -> Path:
    return make_kitti(
        tmp_path / "kitti",
        {
            "000001": [
                label_line("Car", (10, 5, 40, 35)),
                label_line("DontCare", (50, 10, 60, 20)),
                label_line("Van", (60, 5, 90, 38), truncated=0.1, occluded=1),
            ],
            "000002": [label_line("Pedestrian", (5, 2, 15, 39))],
        },
    )


def test_import_kitti(kitti_root: Path) -> None:
    manifest = import_kitti(kitti_root, split="training")
    assert [img.image_id for img in manifest.images] == ["000001", "000002"]
    assert manifest.images[0].file_name == "image_2/000001.png"
    assert (manifest.images[0].width, manifest.images[0].height) == (124, 40)
    assert [a.category for a in manifest.annotations] == ["Car", "Van", "Pedestrian"]
    assert manifest.annotations[1].attributes == {"truncated": 0.1, "occluded": 1}
    assert manifest.categories == list(KITTI_CLASSES)
    assert manifest.source.split == "training"


def test_dont_care_becomes_ignore_region(kitti_root: Path) -> None:
    manifest = import_kitti(kitti_root)
    assert all(a.category != "DontCare" for a in manifest.annotations)
    assert [(r.image_id, r.source) for r in manifest.ignore_regions] == [("000001", "dont_care")]
    assert manifest.ignore_regions[0].bbox == pytest.approx((50, 10, 60, 20))


def test_import_is_deterministic(kitti_root: Path) -> None:
    assert sha256_of(import_kitti(kitti_root)) == sha256_of(import_kitti(kitti_root))


def test_label_change_changes_hash(kitti_root: Path) -> None:
    before = sha256_of(import_kitti(kitti_root))
    label = kitti_root / "label_2" / "000002.txt"
    label.write_text(label_line("Pedestrian", (5, 2, 16, 39)) + "\n")
    assert sha256_of(import_kitti(kitti_root)) != before


def test_image_change_changes_hash(kitti_root: Path) -> None:
    before = sha256_of(import_kitti(kitti_root))
    make_kitti(kitti_root, {"000002": [label_line("Pedestrian", (5, 2, 15, 39))]}, size=(124, 41))
    assert sha256_of(import_kitti(kitti_root)) != before


def test_missing_label_file(kitti_root: Path) -> None:
    (kitti_root / "label_2" / "000002.txt").unlink()
    with pytest.raises(FileNotFoundError):
        import_kitti(kitti_root)


def test_save_and_load_dataset(kitti_root: Path, tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store")
    manifest = import_kitti(kitti_root)
    sha = save_dataset(store, manifest, kitti_root)
    assert sha == sha256_of(manifest)
    assert load_manifest(store, sha) == manifest
    assert resolve_id(store, "dataset", content_id(sha)) == sha
    assert dataset_roots(store, sha) == [kitti_root.resolve()]
    # Import lại cùng dữ liệu, cùng thư mục: không lỗi, không thêm nguồn.
    assert save_dataset(store, import_kitti(kitti_root), kitti_root) == sha
    assert len(dataset_roots(store, sha)) == 1


def test_committed_fixture_manifest_is_valid() -> None:
    path = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "manifest.json"
    manifest = DatasetManifest.model_validate(json.loads(path.read_text()))
    assert manifest.categories == list(KITTI_CLASSES)
