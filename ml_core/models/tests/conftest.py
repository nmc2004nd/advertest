"""Model YOLOv8n khởi tạo ngẫu nhiên (không cần mạng hay fixture) và ảnh tổng hợp.

Weights ngẫu nhiên cho score rất thấp (khoảng 1e-4), nên test dùng `LOW_PARAMS` để có box.
Test trên weights và ảnh fixture thật nằm ở test nghiệm thu (tests/acceptance/phase_01/).
"""

from pathlib import Path

import numpy as np
import pytest
import torch
from numpy.typing import NDArray
from ultralytics.models import YOLO

from advertest_contracts.models import InferenceParams

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
