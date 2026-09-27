"""Nghiệm thu Phase 0, mục Fixture (validation.md).

Test manifest.json viết khi có label gốc KITTI (Group 6, task 31).
"""

from __future__ import annotations

import time
from typing import Any

import cv2
import numpy as np
import numpy.typing as npt
import torch
from ultralytics import YOLO
from ultralytics.data.augment import LetterBox

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
