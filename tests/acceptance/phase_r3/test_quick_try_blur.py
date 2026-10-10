"""validation.md Phase R3, Group 3 — Làm mờ rộng hơn cho thử nhanh (`test_quick_try_blur.py`).
Không cần DB.

`advertest_worker.quick_try.run_quick_try` với model giả (kiểm soát detection và score) và
perturbation đồng nhất (ảnh tấn công y hệt ảnh sạch, để mọi khác biệt là do làm mờ):
- vùng `rule_v1` của detection score trong [`QUICK_TRY_BLUR_MIN_SCORE` = 0.05, `operating_conf`)
  bị làm mờ trên ảnh sạch và mọi level, nhưng không có trong bảng object;
- detection chỉ có ở một level vẫn bị làm mờ ở mọi ảnh của lượt;
- detection score < 0.05 không bị làm mờ;
- ảnh của lượt dùng chung một tập vùng làm mờ.
"""

from __future__ import annotations

import io
from typing import Any

import numpy as np
from PIL import Image

from advertest_contracts.models import AttackSpec
from ml_core.models.adapter import Capabilities
from ml_core.models.wrapper import DEFAULT_INFERENCE_PARAMS

from .conftest import spec_of

LEVELS = [1.0, 2.0, 3.0]
NAMES = ["person", "car"]
# Box xyxy (ảnh 640x640 nên letterbox giữ nguyên tọa độ); vùng làm mờ người là 1/3 trên của box.
FAINT_PERSON = (40.0, 40.0, 100.0, 220.0)  # score 0.1 trên mọi ảnh
LEVEL_PERSON = (240.0, 40.0, 300.0, 220.0)  # score 0.12, chỉ ở level thứ 2
NOISE_PERSON = (440.0, 40.0, 500.0, 220.0)  # score 0.03: không làm mờ
CAR = (100.0, 400.0, 400.0, 560.0)  # score 0.9: có trong bảng object


def _pred(*items: tuple[tuple[float, ...], int, float]) -> dict[str, Any]:
    return {
        "boxes": np.array([b for b, _, _ in items], dtype=np.float32).reshape(-1, 4),
        "labels": np.array([c for _, c, _ in items], dtype=np.int64),
        "scores": np.array([s for _, _, s in items], dtype=np.float32),
    }


class _Adapter:
    capabilities = Capabilities(gradients=False)

    def __init__(self) -> None:
        self.calls = 0

    def class_names(self) -> list[str]:
        return NAMES

    def estimator(self) -> None:
        return None

    def predict(self, images: Any, batch_size: int | None = None) -> list[dict[str, Any]]:
        call, self.calls = self.calls, self.calls + 1
        items = [(FAINT_PERSON, 0, 0.1), (NOISE_PERSON, 0, 0.03), (CAR, 1, 0.9)]
        if call == 2:  # lần 0 là ảnh sạch; lần 2 là level thứ 2
            items.append((LEVEL_PERSON, 0, 0.12))
        return [_pred(*items)]


class _Identity:
    def apply(self, images: Any, targets: Any, level: float, seed: int, mask: Any) -> Any:
        return images.copy()


class _Registry:
    def build(self, spec: AttackSpec, ctx: Any) -> _Identity:
        return _Identity()


def _image() -> bytes:
    rng = np.random.default_rng(0)
    pixels = rng.integers(0, 256, size=(640, 640, 3), dtype=np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, format="PNG")
    return buffer.getvalue()


def _decode(png: bytes) -> np.ndarray:
    with Image.open(io.BytesIO(png)) as image:
        return np.asarray(image.convert("RGB"), dtype=np.int16)


def _top_third(box: tuple[float, ...]) -> tuple[slice, slice]:
    x1, y1, x2, y2 = (int(v) for v in box)
    return slice(y1 + 4, y1 + (y2 - y1) // 3 - 4), slice(x1 + 4, x2 - 4)


def test_blur_union_low_score_all_images() -> None:
    from advertest_worker.quick_try import (  # type: ignore[attr-defined,unused-ignore]
        QUICK_TRY_BLUR_MIN_SCORE,  # Group 3
        run_quick_try,
    )

    assert QUICK_TRY_BLUR_MIN_SCORE == 0.05
    params = DEFAULT_INFERENCE_PARAMS
    assert params.operating_conf > 0.12  # người mờ nằm dưới ngưỡng của bảng object
    source = _image()
    original = _decode(source)
    adapter: Any = _Adapter()
    registry: Any = _Registry()
    output = run_quick_try(source, adapter, spec_of("fog"), LEVELS, params, registry)
    images = [_decode(output.clean_png), *(_decode(png) for png in output.level_pngs)]
    assert len(images) == 1 + len(LEVELS)

    for image in images:
        for box in (FAINT_PERSON, LEVEL_PERSON):
            region = _top_third(box)
            assert np.abs(image[region] - original[region]).mean() > 1.0, box
        region = _top_third(NOISE_PERSON)
        np.testing.assert_array_equal(image[region], original[region])
        np.testing.assert_array_equal(image, images[0])  # cùng tập vùng làm mờ

    for level in output.levels:
        assert [(o.class_name, o.status) for o in level.objects] == [("car", "kept")]
