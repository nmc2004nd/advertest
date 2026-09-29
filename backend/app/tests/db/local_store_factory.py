"""LocalStore tổng hợp cho test backend: YOLOv8n ngẫu nhiên, KITTI 4 ảnh, slice 2 ảnh."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import torch
from ultralytics.models import YOLO
from ultralytics.nn.tasks import DetectionModel

from advertest_contracts.hashing import sha256_of
from advertest_contracts.models import (
    ClassMapping,
    DatasetManifest,
    GradientCheck,
    ModelCard,
    SliceSpec,
)
from ml_core.data.dataset import save_dataset
from ml_core.data.kitti import import_kitti
from ml_core.data.mapping import build_mapping, save_mapping
from ml_core.data.slice import create_slice, save_slice
from ml_core.data.tests.kitti_factory import label_line, make_kitti
from ml_core.models import register as register_module
from ml_core.models.register import register_model
from ml_core.store import LocalStore


@dataclass(frozen=True)
class LocalData:
    store: LocalStore
    card: ModelCard
    manifest: DatasetManifest
    slice: SliceSpec
    mapping: ClassMapping


def build_local_store(tmp: Path, image_size: tuple[int, int] = (160, 40)) -> LocalData:
    torch.manual_seed(0)
    yolo = YOLO("yolov8n.yaml")
    model = yolo.model
    assert isinstance(model, DetectionModel)
    model.names = {i: {0: "person", 2: "car", 7: "truck"}.get(i, f"class{i}") for i in range(80)}
    weights = tmp / "yolov8n-random.pt"
    yolo.save(weights)
    kitti = make_kitti(
        tmp / "kitti",
        {
            "000001": [label_line("Car", (10, 2, 40, 38))],
            "000002": [label_line("Pedestrian", (5, 2, 15, 39))],
            "000003": [label_line("Truck", (50, 0, 120, 39))],
            "000004": [label_line("Car", (0, 0, 9, 20))],
        },
        size=image_size,
    )
    store = LocalStore(tmp / "store")
    manifest = import_kitti(kitti)
    save_dataset(store, manifest, kitti)
    check = GradientCheck(passed=True, checked_at=datetime(2026, 9, 29, tzinfo=UTC))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(register_module, "run_gradient_check", lambda *a, **k: check)
        card = register_model(
            store, weights, "yolov8n-random", np.zeros((1, 3, 640, 640), np.float32)
        )
    slice_spec = create_slice(manifest, size=2, seed=0)
    save_slice(store, slice_spec)
    mapping = build_mapping(sha256_of(manifest), card, "kitti-coco")
    save_mapping(store, mapping)
    return LocalData(store, card, manifest, slice_spec, mapping)
