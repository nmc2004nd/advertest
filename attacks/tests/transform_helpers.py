"""Ảnh letterbox giả lập cho test corruption và occlusion (không phụ thuộc ml_core)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from advertest_contracts.models import AttackSpec

SEEDS = Path(__file__).resolve().parents[2] / "contracts" / "seeds" / "attack_specs.json"
SIZE = 640
PAD = 114.0 / 255.0
# Vùng ảnh thật của KITTI 1242x375 sau letterbox 640: 193 hàng ở giữa.
REAL_TOP, REAL_BOTTOM = 223, 416


def spec(name: str) -> AttackSpec:
    items = json.loads(SEEDS.read_text())
    return AttackSpec.model_validate(next(item for item in items if item["name"] == name))


def letterbox_batch(n: int, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """(images, mask): ảnh float32 (N, 3, 640, 640), cảnh trơn + nhiễu trong vùng thật, pad 114."""
    rng = np.random.default_rng(seed)
    images = np.full((n, 3, SIZE, SIZE), PAD, dtype=np.float32)
    mask = np.zeros((n, 1, SIZE, SIZE), dtype=np.float32)
    height = REAL_BOTTOM - REAL_TOP
    yy, xx = np.mgrid[0:height, 0:SIZE]
    for i in range(n):
        base = 0.2 + 0.6 * (xx / SIZE) * (0.5 + 0.5 * np.sin(yy / 17.0 + i))
        scene = np.stack([base, base[::-1], 1 - base]) + rng.normal(0, 0.03, (3, height, SIZE))
        images[i, :, REAL_TOP:REAL_BOTTOM] = np.clip(scene, 0, 1)
        mask[i, :, REAL_TOP:REAL_BOTTOM] = 1.0
    return images, mask


def targets(n: int, boxes: list[list[list[float]]] | None = None) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for i in range(n):
        box = np.asarray(boxes[i] if boxes else np.zeros((0, 4)), dtype=np.float32).reshape(-1, 4)
        result.append(
            {
                "image_id": f"{i:06d}",
                "boxes": box,
                "labels": np.zeros(len(box), dtype=np.int64),
            }
        )
    return result
