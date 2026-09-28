"""Đăng ký model: hash weights, bài kiểm tra gradient, ghi `ModelCard` vào store.

Bố cục trong store: `models/<weights_sha>/weights.pt` (bản sao weights, để `eval --model <id>`
nạp lại), `models/<weights_sha>/card.json`, chỉ mục `index/model/<id>`.
Store là bất biến: đăng ký lại cùng weights trả card đã có (giữ tên của lần đầu), không chạy lại
bài kiểm tra.
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import art
import numpy as np
import torch
import torchmetrics
import ultralytics
from numpy.typing import NDArray
from PIL import Image
from ultralytics.nn.tasks import DetectionModel

from advertest_contracts.ids import content_id
from advertest_contracts.models import InferenceParams, LibVersions, ModelCard
from ml_core.fixtures import FIXTURES_DIR
from ml_core.models.estimator import build_estimator
from ml_core.models.gradient_check import run_gradient_check
from ml_core.models.wrapper import DEFAULT_INFERENCE_PARAMS, class_names, load_detection_model
from ml_core.preprocess import INPUT_SIZE, letterbox
from ml_core.store import ArtifactStore, register_id

CHECK_IMAGES_DIR = FIXTURES_DIR / "kitti" / "image_2"


def weights_key(weights_sha256: str) -> str:
    return f"models/{weights_sha256}/weights.pt"


def card_key(weights_sha256: str) -> str:
    return f"models/{weights_sha256}/card.json"


def lib_versions() -> LibVersions:
    return LibVersions(
        torch=torch.__version__,
        art=art.__version__,
        ultralytics=ultralytics.__version__,
        torchmetrics=torchmetrics.__version__,
        numpy=np.__version__,
    )


def load_check_images(directory: Path = CHECK_IMAGES_DIR) -> NDArray[np.float32]:
    """Ảnh fixture đã letterbox, (N, 3, 640, 640) float32 [0, 1]."""
    paths = sorted(directory.glob("*.png"))
    if not paths:
        raise FileNotFoundError(f"Không có ảnh fixture trong {directory}; chạy `make fixtures`.")
    return np.stack([letterbox(Image.open(p))[0] for p in paths])


def _architecture(model: DetectionModel, weights: Path) -> str:
    """Ví dụ `yolov8n`: từ `train_args.model` của checkpoint, hoặc `yaml_file` của model."""
    source = getattr(model, "yaml", {}).get("yaml_file")
    ckpt = torch.load(weights, map_location="cpu", weights_only=False)
    train_args = ckpt.get("train_args") if isinstance(ckpt, dict) else None
    if isinstance(train_args, dict) and train_args.get("model"):
        source = train_args["model"]
    return Path(str(source)).stem if source else "unknown"


def load_card(store: ArtifactStore, weights_sha256: str) -> ModelCard:
    return ModelCard.model_validate_json(store.get(card_key(weights_sha256)))


def register_model(
    store: ArtifactStore,
    weights: Path,
    name: str,
    images: NDArray[np.float32],
    device: str = "cpu",
    params: InferenceParams = DEFAULT_INFERENCE_PARAMS,
) -> ModelCard:
    data = weights.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    if store.exists(card_key(sha)):
        return load_card(store, sha)

    # Nạp từ bản sao đã hash để chắc chắn model được kiểm tra đúng là weights được lưu.
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "weights.pt"
        copy.write_bytes(data)
        model = load_detection_model(copy)
        architecture = _architecture(model, copy)

    # Lỗi khi chạy bài kiểm tra (không phải kết quả "không đạt") được báo ra và không ghi card:
    # store là bất biến, nên ghi card lúc này sẽ khóa model ở trạng thái sai.
    estimator = build_estimator(model, params, device)
    check = run_gradient_check(estimator, images, params.operating_conf)

    card = ModelCard(
        id=content_id(sha),
        name=name,
        framework="ultralytics",
        architecture=architecture,
        weights_sha256=sha,
        class_names=class_names(model),
        input_size=INPUT_SIZE,
        supports_gradients=check.passed,
        gradient_check=check,
        lib_versions=lib_versions(),
    )
    store.put(weights_key(sha), data)
    store.put(card_key(sha), card.model_dump_json(indent=2).encode())
    register_id(store, "model", sha)
    return card
