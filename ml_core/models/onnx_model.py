"""Model cho adapter `onnx`: chỉ inference qua `onnxruntime` (requirements.md Phase R2, mục Model
qua web). Không có gradient (`ModelCard.supports_gradients` luôn false).

Đầu ra phải theo một trong hai layout, nhận ra khi mở session:
- `yolo`: một đầu ra (B, 4 + C, N) đã giải mã nhưng chưa NMS (box xywh tâm, pixel), như `output0`
  của Ultralytics; hậu xử lý bằng `yolo_postprocess`, dùng chung với adapter Ultralytics.
- `boxes_scores_labels`: ba đầu ra tên `boxes` (K, 4) xyxy pixel, `scores` (K,), `labels` (K,), có
  thể kèm chiều batch đầu; coi là đã NMS: chỉ lọc `scores ≥ conf`, giữ `max_det` box score cao nhất
  và cắt box về khung ảnh.

Ảnh vào (N, 3, S, S) float32 [0, 1] đi thẳng vào model (không normalize thêm). Session có batch
tĩnh khác N thì chạy từng ảnh.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import onnxruntime as ort
import torch
from numpy.typing import NDArray

from advertest_contracts.models import InferenceParams
from ml_core.models.wrapper import yolo_postprocess

Prediction = dict[str, NDArray[Any]]
BSL = ("boxes", "scores", "labels")


class OnnxLayout(StrEnum):
    YOLO = "yolo"
    BOXES_SCORES_LABELS = "boxes_scores_labels"


class _NodeArg(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def shape(self) -> Sequence[Any]: ...


class Session(Protocol):
    """Phần của `onnxruntime.InferenceSession` mà adapter dùng."""

    def get_inputs(self) -> Sequence[_NodeArg]: ...

    def get_outputs(self) -> Sequence[_NodeArg]: ...

    def run(self, output_names: list[str] | None, input_feed: dict[str, Any]) -> list[Any]: ...


def open_session(weights: Path | bytes, device: str = "cpu") -> ort.InferenceSession:
    """Session CPU; thêm CUDA khi `device` là cuda và onnxruntime có provider này."""
    providers = ["CPUExecutionProvider"]
    if torch.device(device).type == "cuda" and "CUDAExecutionProvider" in (
        ort.get_available_providers()
    ):
        providers.insert(0, "CUDAExecutionProvider")
    source = weights if isinstance(weights, bytes) else str(weights)
    return ort.InferenceSession(source, providers=providers)


def _static(dim: Any) -> int | None:
    return dim if isinstance(dim, int) else None


@dataclass(frozen=True)
class OnnxModel:
    session: Session
    layout: OnnxLayout
    input_name: str
    batch: int | None  # batch tĩnh của input; None khi động
    num_classes: int | None  # C của layout yolo khi tĩnh; layout boxes/scores/labels không biết

    def predict(
        self, images: NDArray[np.float32], params: InferenceParams, batch_size: int
    ) -> list[Prediction]:
        step = self.batch or max(batch_size, 1)
        out: list[Prediction] = []
        for start in range(0, len(images), step):
            chunk = np.ascontiguousarray(images[start : start + step], dtype=np.float32)
            out.extend(self._run(chunk, params))
        return out

    def _run(self, images: NDArray[np.float32], params: InferenceParams) -> list[Prediction]:
        height, width = images.shape[-2:]
        if self.layout is OnnxLayout.YOLO:
            (raw,) = self.session.run(None, {self.input_name: images})
            raw_tensor = torch.from_numpy(np.asarray(raw, dtype=np.float32))
            if self.num_classes is None and raw_tensor.shape[1] <= 4:
                raise ValueError(f"Đầu ra YOLO {tuple(raw_tensor.shape)} không có class")
            return [
                {k: v.numpy() for k, v in pred.items()}
                for pred in yolo_postprocess(raw_tensor, params, height, width)
            ]
        boxes, scores, labels = self.session.run(list(BSL), {self.input_name: images})
        if np.ndim(scores) == 1:  # không có chiều batch
            boxes, scores, labels = boxes[None], scores[None], labels[None]
        if len(scores) != len(images):
            raise ValueError(f"Đầu ra có {len(scores)} ảnh, đầu vào có {len(images)}")
        return [
            bsl_postprocess(b, s, lab, params, height, width)
            for b, s, lab in zip(boxes, scores, labels, strict=True)
        ]


def bsl_postprocess(
    boxes: NDArray[Any],
    scores: NDArray[Any],
    labels: NDArray[Any],
    params: InferenceParams,
    height: int,
    width: int,
) -> Prediction:
    """Prediction của một ảnh layout `boxes_scores_labels` (đã NMS)."""
    boxes = np.asarray(boxes, dtype=np.float32).reshape(-1, 4)
    scores = np.asarray(scores, dtype=np.float32).reshape(-1)
    labels = np.asarray(labels).reshape(-1).astype(np.int64)
    if not len(boxes) == len(scores) == len(labels):
        raise ValueError(
            f"boxes/scores/labels lệch số lượng: {len(boxes)}, {len(scores)}, {len(labels)}"
        )
    keep = np.flatnonzero(scores >= params.conf)
    keep = keep[np.argsort(-scores[keep], kind="stable")][: params.max_det]
    boxes = boxes[keep].copy()
    boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, width)
    boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, height)
    return {"boxes": boxes, "labels": labels[keep], "scores": scores[keep]}


def inspect(session: Session, input_size: int) -> OnnxModel:
    """Nhận layout và kiểm input; model không theo layout được hỗ trợ → `ValueError`."""
    inputs = session.get_inputs()
    if len(inputs) != 1:
        raise ValueError(f"Model ONNX phải có đúng 1 input, có {len(inputs)}")
    shape = list(inputs[0].shape)
    if len(shape) != 4:
        raise ValueError(f"Input ONNX phải có dạng (N, 3, H, W), có {shape}")
    for got, want in zip(shape[1:], (3, input_size, input_size), strict=True):
        if _static(got) is not None and got != want:
            raise ValueError(f"Input ONNX {shape} khác (N, 3, {input_size}, {input_size})")

    outputs = session.get_outputs()
    names = {o.name for o in outputs}
    if set(BSL) <= names:
        layout, num_classes = OnnxLayout.BOXES_SCORES_LABELS, None
    elif len(outputs) == 1 and len(outputs[0].shape) == 3:
        layout = OnnxLayout.YOLO
        channels = _static(outputs[0].shape[1])
        num_classes = channels - 4 if channels is not None else None
        if num_classes is not None and num_classes < 1:
            raise ValueError(f"Đầu ra YOLO {list(outputs[0].shape)} không có class")
    else:
        found = [(o.name, list(o.shape)) for o in outputs]
        raise ValueError(
            "Đầu ra ONNX không theo layout được hỗ trợ: một đầu ra (1, 4 + C, N) kiểu YOLO, "
            f"hoặc ba đầu ra boxes/scores/labels; có {found}"
        )
    return OnnxModel(session, layout, inputs[0].name, _static(shape[0]), num_classes)
