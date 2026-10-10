"""Tính thử nhanh (`advertest_worker.quick_try`): ghép object, làm mờ, chạy mọi level."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from advertest_contracts.models import AttackSpec
from advertest_worker.quick_try import Box, blurred_png, match_objects, run_quick_try
from attacks.builders import DEFAULT_REGISTRY
from ml_core.models.adapter import Capabilities
from ml_core.models.wrapper import DEFAULT_INFERENCE_PARAMS

MOCKS = Path(__file__).resolve().parents[3] / "contracts" / "mocks"


def _spec(name: str) -> AttackSpec:
    return AttackSpec.model_validate_json((MOCKS / "attack_spec" / f"{name}.json").read_text())


def test_match_kept_lost_new_by_iou_and_class() -> None:
    clean = [
        Box((0, 0, 100, 100), "person", 0.9),
        Box((200, 200, 300, 300), "car", 0.8),
        Box((400, 400, 500, 500), "car", 0.7),
    ]
    attacked = [
        Box((5, 5, 105, 105), "person", 0.6),  # IoU ≈ 0.82 → kept
        Box((200, 200, 300, 300), "truck", 0.9),  # khác class → car lost, truck new
        Box((440, 440, 540, 540), "car", 0.5),  # IoU ≈ 0.22 → lost + new
    ]
    objects = match_objects(clean, attacked)
    assert [(o.class_name, o.status.value) for o in objects] == [
        ("person", "kept"),
        ("car", "lost"),
        ("car", "lost"),
        ("truck", "new"),
        ("car", "new"),
    ]
    assert objects[0].clean_score == 0.9 and objects[0].attacked_score == 0.6
    assert objects[0].bbox == (0, 0, 100, 100)
    assert objects[3].clean_score is None and objects[3].bbox == (200, 200, 300, 300)


def test_match_is_greedy_by_highest_iou() -> None:
    clean = [Box((0, 0, 100, 100), "car", 0.9), Box((10, 0, 110, 100), "car", 0.9)]
    attacked = [Box((10, 0, 110, 100), "car", 0.5)]
    objects = match_objects(clean, attacked)
    assert [o.status.value for o in objects] == ["lost", "kept"]


def test_blur_only_inside_rule_v1_region() -> None:
    rng = np.random.default_rng(0)
    image = rng.random((3, 128, 128), dtype=np.float32)
    data = blurred_png(image, [Box((0, 0, 64, 96), "person", 0.9)])
    served = np.asarray(Image.open(io.BytesIO(data)), dtype=np.float32)
    original = np.round(image.transpose(1, 2, 0) * 255)
    diff = np.abs(served - original).mean(axis=2)
    assert diff[:32, :64].mean() > 10  # đầu người: 1/3 phía trên của box
    assert diff[32:, :].max() == 0 and diff[:, 64:].max() == 0


class _Adapter:
    """Ảnh sạch có một người; ảnh bị tấn công (đã khác ảnh sạch) mất người, thêm một xe."""

    card: Any = None
    capabilities = Capabilities(gradients=False)

    def __init__(self) -> None:
        self.clean: np.ndarray[Any, Any] | None = None

    def class_names(self) -> list[str]:
        return ["person", "car"]

    def predict(self, images: Any, batch_size: int | None = None) -> list[dict[str, Any]]:
        if self.clean is None:
            self.clean = images.copy()
            return [_pred([[100, 200, 200, 400]], [0], [0.9])]
        assert not np.array_equal(images, self.clean)
        return [_pred([[300, 300, 400, 380], [0, 0, 5, 5]], [1, 1], [0.7, 0.1])]

    def estimator(self) -> Any:
        raise AssertionError("fog không cần gradient")


def _pred(boxes: list[list[float]], labels: list[int], scores: list[float]) -> dict[str, Any]:
    return {"boxes": np.array(boxes), "labels": np.array(labels), "scores": np.array(scores)}


def test_run_quick_try_all_levels() -> None:
    buffer = io.BytesIO()
    Image.fromarray(np.full((240, 320, 3), 120, dtype=np.uint8)).save(buffer, format="PNG")
    adapter = _Adapter()
    out = run_quick_try(
        buffer.getvalue(), adapter, _spec("fog"), [1.0, 3.0], DEFAULT_INFERENCE_PARAMS,
        DEFAULT_REGISTRY,
    )  # fmt: skip
    assert [lv.level for lv in out.levels] == [1.0, 3.0]
    for level in out.levels:
        assert [(o.class_name, o.status.value) for o in level.objects] == [
            ("person", "lost"),
            ("car", "new"),  # box score 0.1 < operating_conf bị bỏ
        ]
    assert len(out.level_pngs) == 2
    for data in [out.clean_png, *out.level_pngs]:
        assert Image.open(io.BytesIO(data)).size == (640, 640)


def test_run_quick_try_rejects_patch_and_missing_gradients() -> None:
    with pytest.raises(ValueError, match="patch"):
        run_quick_try(b"", _Adapter(), _spec("adv_patch"), [0.1], DEFAULT_INFERENCE_PARAMS,
                      DEFAULT_REGISTRY)  # fmt: skip
    with pytest.raises(ValueError, match="gradient"):
        run_quick_try(b"", _Adapter(), _spec("pgd_linf"), [1.0], DEFAULT_INFERENCE_PARAMS,
                      DEFAULT_REGISTRY)  # fmt: skip
