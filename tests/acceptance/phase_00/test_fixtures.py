"""Nghiệm thu Phase 0, mục Fixture (validation.md)."""

from __future__ import annotations

import time
from typing import Any

import cv2
import numpy as np
import numpy.typing as npt
import torch
from PIL import Image
from ultralytics import YOLO
from ultralytics.data.augment import LetterBox

from advertest_contracts.models import DatasetManifest
from ml_core.fixtures import FIXTURES_DIR, load_checksums, sha256_file

INPUT_SIZE = 640
TIME_LIMIT_S = 60


def test_every_fixture_present_with_matching_sha256() -> None:
    files = load_checksums()
    assert files
    for item in files:
        path = FIXTURES_DIR / item.path
        assert path.is_file(), f"Thiếu {item.path}: chạy `make fixtures`"
        assert sha256_file(path) == item.sha256, item.path


def _letterboxed_batch() -> npt.NDArray[np.float32]:
    """5 ảnh fixture theo quy ước tech-stack.md mục 2.1: (N, 3, 640, 640), float32, RGB, [0, 1]."""
    paths = sorted((FIXTURES_DIR / "kitti" / "image_2").glob("*.png"))
    assert len(paths) == 5, f"Cần đúng 5 ảnh KITTI trong fixture, có {len(paths)}"
    letterbox = LetterBox(new_shape=(INPUT_SIZE, INPUT_SIZE), auto=False, center=True)
    batch = []
    for path in paths:
        bgr = cv2.imread(str(path))
        assert bgr is not None, path
        boxed = letterbox(image=bgr)
        rgb = cv2.cvtColor(boxed, cv2.COLOR_BGR2RGB)
        batch.append(rgb.transpose(2, 0, 1).astype(np.float32) / 255.0)
    return np.stack(batch)


def test_smoke_yolov8n_cpu_on_fixture_images() -> None:
    images = _letterboxed_batch()
    assert images.shape == (5, 3, INPUT_SIZE, INPUT_SIZE)
    assert images.dtype == np.float32
    assert images.min() >= 0.0 and images.max() <= 1.0

    model = YOLO(str(FIXTURES_DIR / "yolov8n.pt"))
    start = time.perf_counter()
    # Tensor đã letterbox: Ultralytics không resize lại, box nằm trong không gian 640x640.
    results = model.predict(torch.from_numpy(images), device="cpu", verbose=False)
    elapsed = time.perf_counter() - start
    assert elapsed < TIME_LIMIT_S, f"Suy luận mất {elapsed:.1f} giây trên CPU"

    # Nhãn detector theo quy ước ART: list dict {"boxes", "labels", "scores"}.
    predictions: list[dict[str, Any]] = [
        {
            "boxes": r.boxes.xyxy.numpy(),
            "labels": r.boxes.cls.numpy().astype(np.int64),
            "scores": r.boxes.conf.numpy(),
        }
        for r in results
    ]
    assert len(predictions) == 5
    assert sum(len(p["boxes"]) for p in predictions) > 0, "Không detect được object nào"
    for p in predictions:
        boxes, labels, scores = p["boxes"], p["labels"], p["scores"]
        assert boxes.ndim == 2 and boxes.shape[1] == 4
        assert len(labels) == len(scores) == len(boxes)
        assert np.all(boxes >= 0) and np.all(boxes <= INPUT_SIZE)
        assert np.all(boxes[:, 2] >= boxes[:, 0]) and np.all(boxes[:, 3] >= boxes[:, 1])
        assert np.all((scores >= 0) & (scores <= 1))


def test_manifest_validates_and_matches_images_and_original_labels() -> None:
    manifest = DatasetManifest.model_validate_json((FIXTURES_DIR / "manifest.json").read_text())
    assert manifest.source.format == "kitti"
    assert len(manifest.images) == 5
    expected_anns: list[tuple[str, str, tuple[float, ...], float, int]] = []
    expected_ignores: list[tuple[str, tuple[float, ...]]] = []
    for image in manifest.images:
        path = FIXTURES_DIR / image.file_name
        assert sha256_file(path) == image.sha256, image.image_id
        assert Image.open(path).size == (image.width, image.height)
        # Đọc lại label gốc KITTI độc lập với cách manifest được tạo.
        label = FIXTURES_DIR / "kitti" / "label_2" / f"{image.image_id}.txt"
        for line in label.read_text().splitlines():
            f = line.split()
            bbox = tuple(float(v) for v in f[4:8])
            if f[0] == "DontCare":
                expected_ignores.append((image.image_id, bbox))
            else:
                expected_anns.append((image.image_id, f[0], bbox, float(f[1]), int(f[2])))
    actual_anns = [
        (a.image_id, a.category, a.bbox, a.attributes["truncated"], a.attributes["occluded"])
        for a in manifest.annotations
    ]
    assert actual_anns == expected_anns
    assert [(r.image_id, r.bbox) for r in manifest.ignore_regions] == expected_ignores
    assert all(r.source == "dont_care" for r in manifest.ignore_regions)


def test_fixture_covers_required_kitti_cases() -> None:
    """requirements.md Phase 0: đủ lớp yêu cầu, có DontCare và object dưới mức Moderate."""
    manifest = DatasetManifest.model_validate_json((FIXTURES_DIR / "manifest.json").read_text())
    categories = {a.category for a in manifest.annotations}
    assert {"Car", "Van", "Truck", "Pedestrian", "Cyclist"} <= categories
    assert manifest.ignore_regions, "Cần ít nhất một vùng DontCare"

    def below_moderate(a: Any) -> bool:
        height = a.bbox[3] - a.bbox[1]
        return bool(
            height < 25 or a.attributes["occluded"] >= 2 or a.attributes["truncated"] > 0.30
        )

    assert any(below_moderate(a) for a in manifest.annotations)
