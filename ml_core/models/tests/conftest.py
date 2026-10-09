"""Model YOLOv8n khởi tạo ngẫu nhiên (không cần mạng hay fixture) và ảnh tổng hợp.

Weights ngẫu nhiên cho score rất thấp (khoảng 1e-4), nên test dùng `LOW_PARAMS` để có box.
Test trên weights và ảnh fixture thật nằm ở test nghiệm thu (tests/acceptance/phase_01/).
"""

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import torch
from numpy.typing import NDArray
from safetensors.torch import save_file
from torchvision.models.detection import fcos_resnet50_fpn
from ultralytics.models import YOLO

from advertest_contracts.ids import content_id
from advertest_contracts.models import InferenceParams, ModelCard
from ml_core.models.register import lib_versions

LOW_PARAMS = InferenceParams(conf=1e-4, iou=0.7, max_det=300, operating_conf=1e-4, input_size=640)


@pytest.fixture(scope="session")
def random_weights(tmp_path_factory: pytest.TempPathFactory) -> Path:
    torch.manual_seed(0)
    path = tmp_path_factory.mktemp("weights") / "yolov8n-random.pt"
    YOLO("yolov8n.yaml").save(path)
    return path


@pytest.fixture(scope="session")
def images() -> NDArray[np.float32]:
    rng = np.random.default_rng(0)
    return rng.random((2, 3, 640, 640), dtype=np.float32)


# Phase R2: FCOS khởi tạo ngẫu nhiên (3 class, gồm nền) lưu dạng safetensors, và model card tương
# ứng. Fixture COCO thật nằm ở test nghiệm thu (tests/acceptance/phase_r2/).
FCOS_CLASSES = ["__background__", "car", "person"]


def make_card(
    weights: Path,
    framework: str,
    architecture: str,
    class_names: list[str],
    gradients: bool = False,
) -> ModelCard:
    sha = hashlib.sha256(weights.read_bytes()).hexdigest()
    check: dict[str, Any] = {"passed": gradients, "checked_at": "2026-10-09T00:00:00Z"}
    if not gradients:
        check["details"] = "Chưa kiểm"
    return ModelCard.model_validate(
        {
            "id": str(content_id(sha)),
            "name": weights.stem,
            "framework": framework,
            "architecture": architecture,
            "weights_sha256": sha,
            "class_names": class_names,
            "input_size": 640,
            "supports_gradients": gradients,
            "gradient_check": check,
            "lib_versions": lib_versions().model_dump(),
        }
    )


@pytest.fixture(scope="session")
def fcos_weights(tmp_path_factory: pytest.TempPathFactory) -> Path:
    torch.manual_seed(0)
    model = fcos_resnet50_fpn(weights=None, weights_backbone=None, num_classes=len(FCOS_CLASSES))
    path = tmp_path_factory.mktemp("weights") / "fcos-random.safetensors"
    save_file({k: v.contiguous() for k, v in model.state_dict().items()}, str(path))
    return path
