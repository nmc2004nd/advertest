import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from advertest_contracts.hashing import sha256_of
from advertest_contracts.models import ModelCard
from ml_core.data.dataset import save_dataset
from ml_core.data.kitti import import_kitti
from ml_core.data.loader import ImageNotFoundError, SliceLoader
from ml_core.data.mapping import build_mapping, save_mapping
from ml_core.data.slice import create_slice, save_slice
from ml_core.data.tests.kitti_factory import HEIGHT, WIDTH, label_line, make_kitti
from ml_core.data.tests.test_mapping_slice import WEIGHTS_SHA, model_card
from ml_core.preprocess import boxes_to_letterbox, letterbox
from ml_core.store import LocalStore, register_id


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return make_kitti(
        tmp_path / "kitti",
        {
            "000001": [
                label_line("Van", (10, 2, 40, 38)),
                label_line("Cyclist", (40, 0, 60, 35)),
                label_line("DontCare", (60, 0, 70, 10)),
            ],
            "000002": [label_line("Pedestrian", (5, 2, 15, 39))],
            "000003": [label_line("Truck", (50, 0, 120, 39))],
        },
    )


@pytest.fixture
def store(tmp_path: Path, root: Path) -> LocalStore:
    store = LocalStore(tmp_path / "store")
    save_dataset(store, import_kitti(root), root)
    card = model_card()
    store.put(f"models/{WEIGHTS_SHA}/card.json", card.model_dump_json().encode())
    register_id(store, "model", WEIGHTS_SHA)
    return store


def _setup(store: LocalStore, root: Path, size: int = 3) -> SliceLoader:
    manifest = import_kitti(root)
    spec = create_slice(manifest, size=size, seed=0)
    save_slice(store, spec)
    mapping = build_mapping(sha256_of(manifest), model_card(), "kitti-coco")
    save_mapping(store, mapping)
    return SliceLoader.from_ids(store, spec.id, mapping.id)


def test_batches_shape_dtype_range(store: LocalStore, root: Path) -> None:
    loader = _setup(store, root)
    assert len(loader) == 3
    batches = list(loader.batches(batch_size=2))
    assert [len(b.image_ids) for b in batches] == [2, 1]
    b = batches[0]
    assert b.images.shape == (2, 3, 640, 640)
    assert b.images.dtype == np.float32
    assert b.images.min() >= 0.0 and b.images.max() <= 1.0
    assert b.image_ids == ["000001", "000002"]


def test_targets_in_letterbox_space_with_model_indices(store: LocalStore, root: Path) -> None:
    loader = _setup(store, root)
    batch = next(loader.batches(batch_size=3))
    card: ModelCard = model_card()
    _, info = letterbox(Image.new("RGB", (WIDTH, HEIGHT)))
    t = batch.targets[0]
    assert t["boxes"].dtype == np.float32 and t["labels"].dtype == np.int64
    np.testing.assert_allclose(t["boxes"], boxes_to_letterbox([[10, 2, 40, 38]], info), rtol=1e-6)
    assert t["labels"].tolist() == [card.class_names.index("car")]  # Van → car
    assert batch.targets[1]["labels"].tolist() == [card.class_names.index("person")]
    assert batch.targets[2]["labels"].tolist() == [card.class_names.index("truck")]
    assert batch.infos[0].orig_size == (WIDTH, HEIGHT)


def test_ignore_regions(store: LocalStore, root: Path) -> None:
    batch = next(_setup(store, root).batches(batch_size=1))
    ignore = batch.ignore[0]
    assert ignore["sources"] == ["dont_care", "unmapped:Cyclist"]
    assert ignore["boxes"].shape == (2, 4) and ignore["boxes"].max() <= 640


def test_image_changed_after_import_is_rejected(store: LocalStore, root: Path) -> None:
    loader = _setup(store, root)
    Image.new("RGB", (WIDTH, HEIGHT), (1, 2, 3)).save(root / "image_2" / "000001.png")
    with pytest.raises(ImageNotFoundError, match="sha256"):
        loader.load("000001")


def test_image_found_in_second_source(store: LocalStore, root: Path, tmp_path: Path) -> None:
    copy = tmp_path / "copy"
    shutil.copytree(root, copy)
    save_dataset(store, import_kitti(copy), copy)
    loader = _setup(store, root)
    shutil.rmtree(root)
    assert loader.load("000002")[0].shape == (3, 640, 640)


def test_mapping_from_other_dataset_rejected(store: LocalStore, root: Path) -> None:
    manifest = import_kitti(root)
    spec = create_slice(manifest, size=3, seed=0)
    other = manifest.model_copy(
        update={"source": manifest.source.model_copy(update={"split": "other"})}
    )
    mapping = build_mapping(sha256_of(other), model_card(), "kitti-coco")
    with pytest.raises(ValueError, match="dataset version"):
        SliceLoader(store, spec, mapping, model_card())
