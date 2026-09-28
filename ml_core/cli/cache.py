"""Cache prediction thô trên ảnh sạch (requirements.md Phase 1, mục Cache).

Khóa = sha256 của `weights_sha256`, `image_ids_sha256`, `dataset_version_sha256`, cấu hình
letterbox (`LETTERBOX_CONFIG`), `inference_params`, phiên bản `torch` và `ultralytics`.
Mapping không thuộc khóa: cache lưu prediction **trước** khi lọc class và ignore region, nên đổi
mapping không phải chạy lại model. Lưu ở `cache/predictions/<key>.json`; store bất biến nên mỗi
khóa ghi một lần.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import numpy as np
import torch
import ultralytics
from numpy.typing import NDArray

from advertest_contracts.hashing import sha256_of
from advertest_contracts.models import InferenceParams, SliceSpec
from ml_core.preprocess import LETTERBOX_CONFIG
from ml_core.store import ArtifactStore

Prediction = dict[str, NDArray[Any]]  # {"boxes": (K, 4), "labels": (K,), "scores": (K,)}


def library_versions() -> dict[str, str]:
    return {"torch": torch.__version__, "ultralytics": ultralytics.__version__}


def prediction_cache_key(
    weights_sha256: str,
    slice_spec: SliceSpec,
    params: InferenceParams,
    versions: dict[str, str] | None = None,
) -> str:
    versions = versions or library_versions()
    return sha256_of(
        {
            "weights_sha256": weights_sha256,
            "image_ids_sha256": slice_spec.image_ids_sha256,
            "dataset_version_sha256": slice_spec.dataset_version_sha256,
            "letterbox": dict(LETTERBOX_CONFIG),
            "inference_params": params.model_dump(mode="json"),
            "torch": versions["torch"],
            "ultralytics": versions["ultralytics"],
        }
    )


def cache_key_path(key: str) -> str:
    return f"cache/predictions/{key}.json"


@dataclass(frozen=True)
class CachedPredictions:
    predictions: dict[str, Prediction]
    device: str  # thiết bị đã chạy model tạo ra prediction, ví dụ `cuda:0 (NVIDIA ...)`


def save_predictions(
    store: ArtifactStore, key: str, predictions: dict[str, Prediction], device: str
) -> None:
    """Prediction thô theo `image_id` (box xyxy letterbox, label là chỉ số class trong model),
    kèm thiết bị đã chạy model: khi cache hit, kết quả ghi thiết bị này chứ không phải thiết bị
    của lần chạy sau (mission.md nguyên tắc 3, 4)."""
    body = {
        image_id: {
            "boxes": np.asarray(p["boxes"], dtype=np.float32).reshape(-1, 4).tolist(),
            "labels": np.asarray(p["labels"], dtype=np.int64).tolist(),
            "scores": np.asarray(p["scores"], dtype=np.float32).tolist(),
        }
        for image_id, p in sorted(predictions.items())
    }
    data = {"key": key, "device": device, "predictions": body}
    store.put(cache_key_path(key), json.dumps(data, ensure_ascii=False).encode())


def load_predictions(store: ArtifactStore, key: str) -> CachedPredictions | None:
    """Prediction đã cache, hoặc `None` nếu chưa có khóa này."""
    path = cache_key_path(key)
    if not store.exists(path):
        return None
    data = json.loads(store.get(path))
    if data.get("key") != key:
        raise ValueError(f"File cache {path} không khớp khóa")
    predictions: dict[str, Prediction] = {
        image_id: {
            "boxes": np.asarray(p["boxes"], dtype=np.float32).reshape(-1, 4),
            "labels": np.asarray(p["labels"], dtype=np.int64),
            "scores": np.asarray(p["scores"], dtype=np.float32),
        }
        for image_id, p in data["predictions"].items()
    }
    return CachedPredictions(predictions=predictions, device=data["device"])
