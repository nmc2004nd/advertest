"""Vùng làm mờ và bản ghi `anonymization` cho failure case (plan task 23).

Dùng prediction thô (mọi class của model, chưa lọc class đích): người hay xe không thuộc class
đích vẫn phải được làm mờ.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

from advertest_contracts.models import CaseAnonymization
from ml_core.privacy import METHOD, VERSION
from ml_core.privacy.regions import Box, Detection, rule_v1_regions


def _detections(
    boxes: Any, labels: Any, scores: Any | None, class_names: Sequence[str]
) -> list[Detection]:
    box_array = np.asarray(boxes, dtype=np.float64).reshape(-1, 4)
    label_array = np.asarray(labels).reshape(-1)
    score_array = None if scores is None else np.asarray(scores, dtype=np.float64).reshape(-1)
    result = []
    for i, (box, label) in enumerate(zip(box_array, label_array, strict=True)):
        index = int(label)
        name = class_names[index] if 0 <= index < len(class_names) else ""
        score = None if score_array is None else float(score_array[i])
        result.append(Detection((box[0], box[1], box[2], box[3]), name, score))
    return result


def case_regions(
    *,
    ground_truth: dict[str, Any],
    clean: dict[str, Any],
    attacked: dict[str, Any],
    ignore_boxes: Any,
    class_names: Sequence[str],
    width: int,
    height: int,
) -> list[Box]:
    """Vùng `rule_v1` của một ảnh; `ground_truth`, `clean`, `attacked` là dict `boxes`, `labels`
    (và `scores` với prediction) theo quy ước ART, xyxy letterbox."""
    ignore = np.asarray(ignore_boxes, dtype=np.float64).reshape(-1, 4)
    return rule_v1_regions(
        ground_truth=_detections(ground_truth["boxes"], ground_truth["labels"], None, class_names),
        clean=_detections(clean["boxes"], clean["labels"], clean["scores"], class_names),
        attacked=_detections(
            attacked["boxes"], attacked["labels"], attacked["scores"], class_names
        ),
        ignore_boxes=[(b[0], b[1], b[2], b[3]) for b in ignore],
        width=width,
        height=height,
    )


def anonymization(regions_count: int) -> CaseAnonymization:
    return CaseAnonymization(
        applied=True, method=METHOD, version=VERSION, regions_count=regions_count
    )
