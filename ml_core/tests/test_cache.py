from pathlib import Path
from typing import Any

import numpy as np
import pytest

from advertest_contracts.models import InferenceParams, SliceSpec
from ml_core.cli.cache import (
    library_versions,
    load_predictions,
    prediction_cache_key,
    save_predictions,
)
from ml_core.store import KeyConflictError, LocalStore

PARAMS = InferenceParams(conf=0.001, iou=0.7, max_det=300, operating_conf=0.25, input_size=640)
MOCK = (
    Path(__file__).resolve().parents[2]
    / "contracts"
    / "mocks"
    / "slice_spec"
    / "kitti_fixture.json"
)
W = "a" * 64


@pytest.fixture
def slice_spec() -> SliceSpec:
    return SliceSpec.model_validate_json(MOCK.read_text())


def test_key_is_deterministic(slice_spec: SliceSpec) -> None:
    assert prediction_cache_key(W, slice_spec, PARAMS) == prediction_cache_key(
        W, slice_spec, PARAMS
    )


@pytest.mark.parametrize(
    "change",
    [
        {"weights": "b" * 64},
        {"params": PARAMS.model_copy(update={"conf": 0.01})},
        {"params": PARAMS.model_copy(update={"iou": 0.6})},
        {"params": PARAMS.model_copy(update={"max_det": 100})},
        {"versions": {**library_versions(), "torch": "0.0.0"}},
        {"versions": {**library_versions(), "ultralytics": "0.0.0"}},
        {"slice": {"image_ids_sha256": "c" * 64}},
        {"slice": {"dataset_version_sha256": "d" * 64}},
    ],
)
def test_key_changes_with_each_component(slice_spec: SliceSpec, change: dict[str, Any]) -> None:
    base = prediction_cache_key(W, slice_spec, PARAMS, library_versions())
    other_slice = slice_spec.model_construct(
        **{**slice_spec.model_dump(), **change.get("slice", {})}
    )
    other = prediction_cache_key(
        change.get("weights", W),
        other_slice,
        change.get("params", PARAMS),
        change.get("versions", library_versions()),
    )
    assert other != base


def test_roundtrip_and_immutable(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    preds = {
        "000002": {"boxes": np.zeros((0, 4)), "labels": np.zeros(0), "scores": np.zeros(0)},
        "000001": {
            "boxes": np.array([[1.5, 2.25, 30.125, 40.0]], dtype=np.float32),
            "labels": np.array([2]),
            "scores": np.array([0.123456789], dtype=np.float32),
        },
    }
    assert load_predictions(store, "k" * 64) is None
    save_predictions(store, "k" * 64, preds)
    loaded = load_predictions(store, "k" * 64)
    assert loaded is not None and set(loaded) == {"000001", "000002"}
    np.testing.assert_array_equal(loaded["000001"]["boxes"], preds["000001"]["boxes"])
    assert loaded["000001"]["scores"][0] == np.float32(0.123456789)  # float32 khứ hồi chính xác
    assert loaded["000002"]["boxes"].shape == (0, 4)
    save_predictions(store, "k" * 64, preds)  # cùng nội dung: không lỗi
    with pytest.raises(KeyConflictError):
        save_predictions(store, "k" * 64, {"000001": preds["000002"]})
