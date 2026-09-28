"""`advertest eval`: đo mAP của model trên slice (ảnh sạch), xuất `CleanEvalResult`.

Luồng (plan.md Phase 1 task 27): khóa cache → có thì đọc prediction thô, không nạp model; chưa có
thì chạy predict theo batch và lưu prediction thô → lọc class và ignore region → tính metric →
`CleanEvalResult`.

Ground truth và ignore region được tính từ manifest (kích thước ảnh đã có trong manifest) nên khi
cache hit không phải đọc lại ảnh; kết quả trùng với `SliceLoader` (xem test).
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np
import torch
from numpy.typing import NDArray

from advertest_contracts.models import CleanEvalResult, InferenceParams
from ml_core.cli.cache import (
    Prediction,
    load_predictions,
    prediction_cache_key,
    save_predictions,
)
from ml_core.data.loader import SliceLoader
from ml_core.data.mapping import apply_mapping
from ml_core.metrics.clean import CleanMetric
from ml_core.metrics.result import build_clean_eval_result
from ml_core.models.estimator import build_estimator
from ml_core.models.register import lib_versions, weights_key
from ml_core.models.wrapper import DEFAULT_INFERENCE_PARAMS, load_detection_model
from ml_core.preprocess import boxes_to_letterbox, letterbox_info
from ml_core.store import ArtifactStore

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BATCH_SIZE = 8
_GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")


class OutOfMemoryError(RuntimeError):
    """Hết VRAM khi chạy predict; thông báo gợi ý giảm batch size."""


@dataclass
class EvalRun:
    result: CleanEvalResult
    warnings: list[str] = field(default_factory=list)


def default_device() -> str:
    return "cuda:0" if torch.cuda.is_available() else "cpu"


def describe_device(device: str) -> str:
    """Ví dụ `cuda:0 (NVIDIA GeForce RTX 3050)` hoặc `cpu`."""
    torch_device = torch.device(device)
    if torch_device.type != "cuda":
        return torch_device.type
    index = torch_device.index if torch_device.index is not None else torch.cuda.current_device()
    return f"cuda:{index} ({torch.cuda.get_device_name(index)})"


def current_git_commit() -> tuple[str, list[str]]:
    """Commit của mã đang chạy: biến `GIT_COMMIT` nếu có, không thì `git rev-parse HEAD`.

    Trả thêm cảnh báo nếu working tree có thay đổi chưa commit.
    """
    env = os.environ.get("GIT_COMMIT", "").strip()
    if env:
        if not _GIT_COMMIT.fullmatch(env):
            raise ValueError(f"GIT_COMMIT không phải commit hash 40 ký tự: {env!r}")
        return env, []

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()

    try:
        commit = git("rev-parse", "HEAD")
        dirty = git("status", "--porcelain", "--untracked-files=no")
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("Không xác định được git commit; đặt biến GIT_COMMIT") from exc
    warnings = ["Working tree có thay đổi chưa commit; git_commit không mô tả đủ mã đã chạy"]
    return commit, warnings if dirty else []


def ground_truth(
    loader: SliceLoader,
) -> tuple[dict[str, dict[str, NDArray[Any]]], dict[str, NDArray[np.float32]]]:
    """Ground truth (box letterbox, label là chỉ số class trong model) và ignore region theo ảnh."""
    mapped = apply_mapping(loader.manifest, loader.mapping)
    sizes = {img.image_id: (img.width, img.height) for img in loader.manifest.images}
    index = {name: i for i, name in enumerate(loader.card.class_names)}
    targets: dict[str, dict[str, NDArray[Any]]] = {}
    ignores: dict[str, NDArray[np.float32]] = {}
    for image_id in loader.slice.image_ids:
        info = letterbox_info(*sizes[image_id])
        img = mapped[image_id]
        targets[image_id] = {
            "boxes": boxes_to_letterbox(img.boxes, info).astype(np.float32),
            "labels": np.asarray([index[c] for c in img.classes], dtype=np.int64),
        }
        ignores[image_id] = boxes_to_letterbox(img.ignore_boxes, info).astype(np.float32)
    return targets, ignores


def predict_slice(loader: SliceLoader, estimator: Any, batch_size: int) -> dict[str, Prediction]:
    predictions: dict[str, Prediction] = {}
    try:
        for batch in loader.batches(batch_size):
            preds = estimator.predict(batch.images, batch_size=batch_size)
            predictions.update(zip(batch.image_ids, preds, strict=True))
    except torch.cuda.OutOfMemoryError as exc:
        raise OutOfMemoryError(
            f"Hết VRAM với batch size {batch_size}; thử lại với --batch-size "
            f"{max(1, batch_size // 2)}"
        ) from exc
    return predictions


def load_model_from_store(store: ArtifactStore, weights_sha256: str) -> Any:
    """Nạp weights đã đăng ký (`models/<sha>/weights.pt`) từ store."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "weights.pt"
        path.write_bytes(store.get(weights_key(weights_sha256)))
        return load_detection_model(path)


def run_eval(
    store: ArtifactStore,
    model_id: UUID,
    slice_id: UUID,
    mapping_id: UUID,
    device: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
    params: InferenceParams = DEFAULT_INFERENCE_PARAMS,
) -> EvalRun:
    if batch_size < 1:
        raise ValueError("batch_size phải ≥ 1")
    start = time.perf_counter()
    git_commit, warnings = current_git_commit()
    loader = SliceLoader.from_ids(store, slice_id, mapping_id)
    card = loader.card
    if card.id != model_id:
        raise ValueError(f"Mapping {mapping_id} thuộc model {card.id}, không phải {model_id}")

    key = prediction_cache_key(card.weights_sha256, loader.slice, params)
    cached = load_predictions(store, key)
    if cached is None:
        estimator = build_estimator(
            load_model_from_store(store, card.weights_sha256), params, device
        )
        predictions = predict_slice(loader, estimator, batch_size)
        save_predictions(store, key, predictions)
    else:
        predictions = cached

    targets, ignores = ground_truth(loader)
    target_classes = {t for t in loader.mapping.classes.values() if t is not None}
    metric = CleanMetric(card.class_names, target_classes, max_det=params.max_det)
    ids = loader.slice.image_ids
    missing = [i for i in ids if i not in predictions]
    if missing:
        raise ValueError(f"Cache thiếu prediction của {len(missing)} ảnh, ví dụ {missing[:3]}")
    metric.update(
        [predictions[i] for i in ids], [targets[i] for i in ids], [ignores[i] for i in ids]
    )

    result = build_clean_eval_result(
        metrics=metric.compute(),
        card=card,
        slice_spec=loader.slice,
        mapping=loader.mapping,
        inference_params=params,
        cache_key=key,
        cache_hit=cached is not None,
        total_s=time.perf_counter() - start,
        device=describe_device(device),
        lib_versions=lib_versions(),
        git_commit=git_commit,
    )
    return EvalRun(result=result, warnings=warnings)
