"""mAP trên ảnh sạch bằng `torchmetrics.MeanAveragePrecision` (backend `pycocotools`).

Giới hạn số detection mỗi ảnh khi tính mAP bằng `max_det` của inference (không dùng mặc định 100
của COCO), để mAP phản ánh đúng những gì NMS giữ lại.

`pycocotools` tính mAP@0.5:0.95 trong `summarize` với `maxDets=100` viết cứng (cocoeval.py,
`stats[0] = _summarize(1)`), nên với giới hạn khác 100 nó trả -1; `map_per_class` của torchmetrics
cũng đi qua đường này. Vì vậy AP được tính từ tensor `precision` (`extended_summary=True`) theo
đúng công thức COCO: trung bình precision hợp lệ (> -1) tại vùng diện tích `all` và giới hạn
detection cuối cùng. Với `max_det = 100`, kết quả trùng với `map`, `map_50`, `map_per_class`
của torchmetrics (xem test).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Sequence
from typing import Any

import numpy as np
import torch
from numpy.typing import NDArray
from torchmetrics.detection import MeanAveragePrecision

from advertest_contracts.models import ClassEvalMetrics, EvalMetrics
from ml_core.metrics.filters import Prediction, filter_classes, filter_ignored

AREA_ALL = 0  # chỉ số vùng diện tích "all" trong tensor precision của COCO
IOU_50 = 0  # chỉ số ngưỡng IoU 0.5 trong iou_thresholds mặc định [0.5, 0.55, ..., 0.95]


def max_detection_thresholds(max_det: int) -> list[int]:
    """Ba mức giới hạn (pycocotools dùng đúng 3 mức), mức cuối là `max_det`."""
    return [1, min(10, max_det), max_det]


def _average_precision(precision: NDArray[np.float64]) -> float | None:
    valid = precision[precision > -1]
    return float(valid.mean()) if valid.size else None


class CleanMetric:
    """Tích lũy theo batch; `compute()` trả `EvalMetrics` của contract.

    Mọi label là chỉ số class trong model. Chỉ class đích của mapping được tính; `per_class`
    luôn có đủ mọi class đích (AP `null` khi class không có ground truth trong slice).
    """

    def __init__(self, class_names: Sequence[str], target_classes: Collection[str], max_det: int):
        unknown = set(target_classes) - set(class_names)
        if unknown:
            raise ValueError(f"Class đích không có trong model: {sorted(unknown)}")
        self.class_names = list(class_names)
        self.target_labels = sorted(self.class_names.index(c) for c in set(target_classes))
        self._map = MeanAveragePrecision(
            box_format="xyxy",
            iou_type="bbox",
            class_metrics=True,
            backend="pycocotools",
            max_detection_thresholds=max_detection_thresholds(max_det),
            extended_summary=True,
        )
        self._map.warn_on_many_detections = False
        self._num_gt: Counter[int] = Counter()

    def update(
        self,
        preds: Sequence[Prediction],
        targets: Sequence[dict[str, NDArray[Any]]],
        ignore_boxes: Sequence[NDArray[Any]],
    ) -> None:
        """Một batch: prediction thô, ground truth (`boxes`, `labels`), ignore region mỗi ảnh."""
        if not len(preds) == len(targets) == len(ignore_boxes):
            raise ValueError("preds, targets, ignore_boxes phải cùng số ảnh")
        preds_t, targets_t = [], []
        for pred, target, ignore in zip(preds, targets, ignore_boxes, strict=True):
            kept = filter_ignored(filter_classes(pred, self.target_labels), ignore)
            preds_t.append(
                {
                    "boxes": torch.as_tensor(kept["boxes"], dtype=torch.float32).reshape(-1, 4),
                    "labels": torch.as_tensor(kept["labels"], dtype=torch.int64),
                    "scores": torch.as_tensor(kept["scores"], dtype=torch.float32),
                }
            )
            labels = np.asarray(target["labels"], dtype=np.int64)
            outside = set(labels.tolist()) - set(self.target_labels)
            if outside:
                raise ValueError(f"Ground truth có class không phải class đích: {sorted(outside)}")
            targets_t.append(
                {
                    "boxes": torch.as_tensor(target["boxes"], dtype=torch.float32).reshape(-1, 4),
                    "labels": torch.as_tensor(labels, dtype=torch.int64),
                }
            )
            self._num_gt.update(labels.tolist())
        self._map.update(preds_t, targets_t)

    def compute(self) -> EvalMetrics:
        if sum(self._num_gt.values()) == 0:
            raise ValueError("Slice không có ground truth nào; không tính được mAP")
        result = self._map.compute()
        # precision: (IoU, recall, class, vùng diện tích, giới hạn detection)
        precision = result["precision"].numpy()[:, :, :, AREA_ALL, -1]
        classes = [int(c) for c in result["classes"].reshape(-1).tolist()]
        per_class: dict[str, ClassEvalMetrics] = {}
        for label in self.target_labels:
            num_gt = self._num_gt[label]
            ap50 = ap = None
            if num_gt > 0:
                k = classes.index(label)
                ap50 = _average_precision(precision[IOU_50, :, k])
                ap = _average_precision(precision[:, :, k])
            per_class[self.class_names[label]] = ClassEvalMetrics(
                ap50=ap50, ap50_95=ap, num_gt=num_gt
            )
        map50 = _average_precision(precision[IOU_50])
        map50_95 = _average_precision(precision)
        return EvalMetrics(
            map50=map50 if map50 is not None else 0.0,
            map50_95=map50_95 if map50_95 is not None else 0.0,
            per_class=per_class,
        )
