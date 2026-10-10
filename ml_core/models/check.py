"""Kiểm tra model đăng ký qua web cho job `model_check` (requirements.md Phase R2, mục Model qua
web).

Các bước, dừng ở bước đầu tiên fail (`passed = false` kèm `details`):
1. sha256 của file bằng `card.weights_sha256`;
2. nạp model (safetensors hoặc ONNX; pickle bị từ chối khi đọc, không chạy code);
3. số class của model bằng `len(card.class_names)` (torchvision: lớp phân loại cuối; ONNX layout
   YOLO: `4 + C`; layout boxes/scores/labels: label trả về phải < số class);
4. inference trên ảnh fixture: box (K, 4) hữu hạn, label trong `[0, số class)`.
5. Chỉ torchvision: bài kiểm tra gradient (`run_gradient_check`). Kết quả không đạt **không** làm
   kiểm tra fail: model vẫn `ready`, `supports_gradients = gradient_check.passed` (người duyệt chốt
   2026-10-09, như đăng ký CLI ở Phase 1).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import numpy as np
from numpy.typing import NDArray

from advertest_contracts.models import GradientCheck, InferenceParams, ModelCard, ModelCheckResult
from ml_core.models.adapter import OnnxAdapter, Prediction, TorchvisionAdapter, open_adapter
from ml_core.models.gradient_check import run_gradient_check
from ml_core.models.register import load_check_images
from ml_core.models.wrapper import DEFAULT_INFERENCE_PARAMS

# Số ảnh fixture dùng khi không truyền `images` (FCOS trên CPU khoảng 1 giây mỗi ảnh).
CHECK_IMAGES = 2


class _CheckFailed(Exception):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate(predictions: list[Prediction], count: int, num_classes: int) -> None:
    if len(predictions) != count:
        raise _CheckFailed(f"Inference trả {len(predictions)} kết quả cho {count} ảnh")
    for i, pred in enumerate(predictions):
        boxes, labels = np.asarray(pred["boxes"]), np.asarray(pred["labels"])
        if boxes.ndim != 2 or boxes.shape[1] != 4 or not np.all(np.isfinite(boxes)):
            raise _CheckFailed(f"Ảnh {i}: box không có dạng (K, 4) hữu hạn ({boxes.shape})")
        if len(labels) != len(boxes) or len(np.asarray(pred["scores"])) != len(boxes):
            raise _CheckFailed(f"Ảnh {i}: số box, label, score lệch nhau")
        if len(labels) and (labels.min() < 0 or labels.max() >= num_classes):
            raise _CheckFailed(
                f"Ảnh {i}: label {int(labels.max())} ngoài {num_classes} class của model card"
            )


def check_model(
    card: ModelCard,
    weights_path: Path,
    *,
    worker_target_id: UUID,
    device: str = "cpu",
    params: InferenceParams = DEFAULT_INFERENCE_PARAMS,
    images: NDArray[np.float32] | None = None,
) -> ModelCheckResult:
    """Kiểm tra model torchvision hoặc onnx; lỗi của model trả về trong kết quả, không ném ra.

    `images`: ảnh letterbox (N, 3, S, S) float32 [0, 1]; mặc định `CHECK_IMAGES` ảnh fixture KITTI.
    """
    if card.framework not in ("torchvision", "onnx"):
        raise ValueError(f"check_model chỉ cho model torchvision hoặc onnx, nhận {card.framework}")
    if images is None:
        images = load_check_images()[:CHECK_IMAGES]
    num_classes = len(card.class_names)
    gradient_check: GradientCheck | None = None
    details: str | None = None
    try:
        sha = _sha256(weights_path)
        if sha != card.weights_sha256:
            raise _CheckFailed(f"sha256 của file ({sha}) khác model card ({card.weights_sha256})")

        adapter = open_adapter(card, weights_path, params, device)
        try:
            if isinstance(adapter, TorchvisionAdapter):
                adapter.detector()  # đã kiểm số class với weights
            elif isinstance(adapter, OnnxAdapter):
                found = adapter.model().num_classes
                if found is not None and found != num_classes:
                    raise _CheckFailed(f"Model có {found} class, model card khai báo {num_classes}")
        except _CheckFailed:
            raise
        except Exception as exc:
            raise _CheckFailed(f"Nạp model thất bại: {type(exc).__name__}: {exc}") from exc

        try:
            predictions = adapter.predict(images, batch_size=1)
        except Exception as exc:
            raise _CheckFailed(f"Inference thất bại: {type(exc).__name__}: {exc}") from exc
        _validate(predictions, len(images), num_classes)

        if isinstance(adapter, TorchvisionAdapter):
            try:
                gradient_check = run_gradient_check(
                    adapter.detector(), images, params.operating_conf
                )
            except Exception as exc:
                gradient_check = GradientCheck(
                    passed=False,
                    checked_at=datetime.now(UTC),
                    details=f"Lỗi khi kiểm gradient: {type(exc).__name__}: {exc}",
                )
    except _CheckFailed as exc:
        details = str(exc)

    return ModelCheckResult(
        passed=details is None,
        details=details,
        gradient_check=gradient_check,
        checked_at=datetime.now(UTC),
        worker_target_id=worker_target_id,
    )
