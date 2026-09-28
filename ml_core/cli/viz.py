"""`advertest viz`: vẽ ground truth, prediction và ignore region lên ảnh letterbox, xuất PNG.

Dùng để kiểm tra bằng mắt rằng box khớp sau letterbox (validation.md Phase 1, manual check).
- ground truth: xanh lá; prediction: đỏ, kèm tên class và score; ignore region: xám.
- Chỉ vẽ prediction thuộc class đích của mapping và có score ≥ `operating_conf`; vẽ ở
  `conf = 0.001` thì ảnh kín box.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw

from advertest_contracts.models import InferenceParams
from ml_core.cli.evaluate import load_model_from_store
from ml_core.data.loader import SliceLoader
from ml_core.metrics.filters import filter_classes
from ml_core.models.estimator import build_estimator
from ml_core.models.wrapper import DEFAULT_INFERENCE_PARAMS
from ml_core.store import ArtifactStore

GT_COLOR = (0, 200, 0)
PRED_COLOR = (230, 0, 0)
IGNORE_COLOR = (150, 150, 150)
LINE_WIDTH = 2


def _boxes(boxes: NDArray[Any]) -> list[tuple[float, float, float, float]]:
    return [
        (float(a), float(b), float(c), float(d)) for a, b, c, d in np.asarray(boxes).reshape(-1, 4)
    ]


def render(
    image: NDArray[np.float32],
    gt_boxes: NDArray[Any],
    ignore_boxes: NDArray[Any],
    pred_boxes: NDArray[Any],
    pred_texts: list[str],
) -> Image.Image:
    """`image`: (3, H, W) float32 [0, 1]; mọi box xyxy pixel trong không gian letterbox."""
    pixels = (np.clip(image.transpose(1, 2, 0), 0, 1) * 255).round().astype(np.uint8)
    canvas = Image.fromarray(pixels)
    draw = ImageDraw.Draw(canvas)
    for box in _boxes(ignore_boxes):
        draw.rectangle(box, outline=IGNORE_COLOR, width=LINE_WIDTH)
    for box in _boxes(gt_boxes):
        draw.rectangle(box, outline=GT_COLOR, width=LINE_WIDTH)
    for box, text in zip(_boxes(pred_boxes), pred_texts, strict=True):
        draw.rectangle(box, outline=PRED_COLOR, width=LINE_WIDTH)
        draw.text((box[0] + 2, max(0.0, box[1] - 11)), text, fill=PRED_COLOR)
    return canvas


def run_viz(
    store: ArtifactStore,
    model_id: UUID,
    slice_id: UUID,
    mapping_id: UUID,
    n: int,
    out_dir: Path,
    device: str,
    params: InferenceParams = DEFAULT_INFERENCE_PARAMS,
) -> list[Path]:
    """Vẽ `n` ảnh đầu của slice (theo thứ tự image ID); trả danh sách file PNG."""
    if n < 1:
        raise ValueError("n phải ≥ 1")
    loader = SliceLoader.from_ids(store, slice_id, mapping_id)
    card = loader.card
    if card.id != model_id:
        raise ValueError(f"Mapping {mapping_id} thuộc model {card.id}, không phải {model_id}")
    estimator = build_estimator(load_model_from_store(store, card.weights_sha256), params, device)
    targets = {t for t in loader.mapping.classes.values() if t is not None}
    target_labels = [card.class_names.index(t) for t in sorted(targets)]

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for image_id in loader.slice.image_ids[:n]:
        image, target, ignore, _ = loader.load(image_id)
        pred = filter_classes(estimator.predict(image[None], batch_size=1)[0], target_labels)
        keep = pred["scores"] >= params.operating_conf
        texts = [
            f"{card.class_names[int(label)]} {score:.2f}"
            for label, score in zip(pred["labels"][keep], pred["scores"][keep], strict=True)
        ]
        canvas = render(image, target["boxes"], ignore["boxes"], pred["boxes"][keep], texts)
        path = out_dir / f"{image_id}.png"
        canvas.save(path)
        written.append(path)
    return written
