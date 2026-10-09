"""Logic của adapter ONNX trên session giả (gói `onnx` để sinh model không có trong lock); đường
chạy `onnxruntime` thật trên `yolov8n.onnx` nằm ở test nghiệm thu Phase R2."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import torch
from numpy.typing import NDArray

from ml_core.models import onnx_model
from ml_core.models.adapter import NoGradients, OnnxAdapter, open_adapter
from ml_core.models.onnx_model import OnnxLayout, bsl_postprocess, inspect
from ml_core.models.tests.conftest import LOW_PARAMS, make_card
from ml_core.models.wrapper import yolo_postprocess


@dataclass
class Arg:
    name: str
    shape: Sequence[Any]


class FakeSession:
    def __init__(
        self,
        inputs: list[Arg],
        outputs: list[Arg],
        results: dict[str, NDArray[Any]],
        *,
        batched: bool = True,
    ) -> None:
        self.inputs, self.outputs, self.results = inputs, outputs, results
        self.batched = batched  # false: trả đúng `results`, không có chiều batch
        self.batches: list[int] = []

    def get_inputs(self) -> list[Arg]:
        return self.inputs

    def get_outputs(self) -> list[Arg]:
        return self.outputs

    def run(self, output_names: list[str] | None, input_feed: dict[str, Any]) -> list[Any]:
        (x,) = input_feed.values()
        assert x.dtype == np.float32
        self.batches.append(len(x))
        names = output_names or [o.name for o in self.outputs]
        if not self.batched:
            return [self.results[n] for n in names]
        return [np.repeat(self.results[n], len(x), axis=0) for n in names]


IMAGES = ("images", [1, 3, 640, 640])


def _yolo_raw(classes: int = 2, n: int = 50) -> NDArray[np.float32]:
    rng = np.random.default_rng(0)
    raw = np.zeros((1, 4 + classes, n), np.float32)
    raw[0, 0:2] = rng.uniform(50, 590, (2, n))  # tâm
    raw[0, 2:4] = rng.uniform(10, 120, (2, n))  # rộng, cao
    raw[0, 4:] = rng.uniform(0, 1, (classes, n))
    return raw


def _yolo_session(raw: NDArray[np.float32], batch: Any = 1) -> FakeSession:
    return FakeSession(
        [Arg("images", [batch, 3, 640, 640])],
        [Arg("output0", list(raw.shape))],
        {"output0": raw},
    )


def test_inspect_yolo_layout() -> None:
    model = inspect(_yolo_session(_yolo_raw(classes=2)), 640)
    assert model.layout is OnnxLayout.YOLO
    assert model.num_classes == 2 and model.batch == 1 and model.input_name == "images"


def test_inspect_boxes_scores_labels_layout() -> None:
    session = FakeSession(
        [Arg(*IMAGES)],
        [Arg("labels", [1, "k"]), Arg("boxes", [1, "k", 4]), Arg("scores", [1, "k"])],
        {},
    )
    model = inspect(session, 640)
    assert model.layout is OnnxLayout.BOXES_SCORES_LABELS and model.num_classes is None


@pytest.mark.parametrize(
    ("inputs", "outputs", "match"),
    [
        ([Arg(*IMAGES), Arg("extra", [1])], [Arg("output0", [1, 6, 8])], "đúng 1 input"),
        ([Arg("images", [1, 3, 640])], [Arg("output0", [1, 6, 8])], r"\(N, 3, H, W\)"),
        ([Arg("images", [1, 3, 320, 320])], [Arg("output0", [1, 6, 8])], "khác"),
        ([Arg(*IMAGES)], [Arg("output0", [1, 4, 8])], "không có class"),
        ([Arg(*IMAGES)], [Arg("a", [1, 6, 8]), Arg("b", [1, 8])], "layout"),
        ([Arg(*IMAGES)], [Arg("logits", [1, 1000])], "layout"),
    ],
)
def test_inspect_rejects(inputs: list[Arg], outputs: list[Arg], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        inspect(FakeSession(inputs, outputs, {}), 640)


def test_dynamic_dims_accepted() -> None:
    session = FakeSession(
        [Arg("images", ["n", 3, "h", "w"])], [Arg("output0", ["n", "c", "a"])], {}
    )
    model = inspect(session, 640)
    assert model.batch is None and model.num_classes is None


def test_yolo_predict_matches_shared_postprocess() -> None:
    raw = _yolo_raw()
    session = _yolo_session(raw)
    images = np.zeros((3, 3, 640, 640), np.float32)
    preds = inspect(session, 640).predict(images, LOW_PARAMS, batch_size=8)
    assert session.batches == [1, 1, 1]  # batch tĩnh 1: chạy từng ảnh
    (want,) = yolo_postprocess(torch.from_numpy(raw), LOW_PARAMS, 640, 640)
    assert len(preds) == 3 and len(want["boxes"]) > 0
    for pred in preds:
        for key in ("boxes", "labels", "scores"):
            np.testing.assert_array_equal(pred[key], want[key].numpy())


def test_dynamic_batch_uses_batch_size() -> None:
    session = _yolo_session(_yolo_raw(), batch="n")
    images = np.zeros((5, 3, 640, 640), np.float32)
    assert len(inspect(session, 640).predict(images, LOW_PARAMS, batch_size=2)) == 5
    assert session.batches == [2, 2, 1]


def test_bsl_postprocess_filters_sorts_and_clips() -> None:
    boxes = np.array([[-5, 10, 50, 60], [0, 0, 700, 30], [1, 1, 2, 2], [5, 5, 9, 9]], np.float32)
    scores = np.array([0.5, 0.9, 1e-5, 0.7], np.float32)
    labels = np.array([1, 2, 0, 1], np.int32)
    params = LOW_PARAMS.model_copy(update={"max_det": 2})
    pred = bsl_postprocess(boxes, scores, labels, params, 640, 640)
    np.testing.assert_array_equal(pred["scores"], np.array([0.9, 0.7], np.float32))
    np.testing.assert_array_equal(pred["labels"], np.array([2, 1]))
    assert pred["labels"].dtype == np.int64
    np.testing.assert_array_equal(pred["boxes"], np.array([[0, 0, 640, 30], [5, 5, 9, 9]]))


def test_bsl_postprocess_length_mismatch() -> None:
    with pytest.raises(ValueError, match="lệch"):
        bsl_postprocess(np.zeros((2, 4)), np.zeros(3), np.zeros(2), LOW_PARAMS, 640, 640)


def test_bsl_predict_without_batch_dim() -> None:
    session = FakeSession(
        [Arg("images", [1, 3, 640, 640])],
        [Arg("boxes", ["k", 4]), Arg("scores", ["k"]), Arg("labels", ["k"])],
        {
            "boxes": np.array([[1, 2, 30, 40]], np.float32),
            "scores": np.array([0.8], np.float32),
            "labels": np.array([3], np.int64),
        },
        batched=False,
    )
    (pred,) = inspect(session, 640).predict(np.zeros((1, 3, 640, 640), np.float32), LOW_PARAMS, 1)
    np.testing.assert_array_equal(pred["labels"], [3])


def test_adapter_without_gradients(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, images: NDArray[np.float32]
) -> None:
    weights = tmp_path / "m.onnx"
    weights.write_bytes(b"onnx")
    opened: list[Any] = []

    def fake_open(source: Path | bytes, device: str) -> FakeSession:
        opened.append(source)
        return _yolo_session(_yolo_raw(classes=2))

    monkeypatch.setattr(onnx_model, "open_session", fake_open)
    card = make_card(weights, "onnx", "fake yolo", ["a", "b"])
    adapter = open_adapter(card, weights, LOW_PARAMS, "cpu")
    assert isinstance(adapter, OnnxAdapter)
    assert adapter.capabilities.gradients is False
    with pytest.raises(NoGradients):
        adapter.estimator()
    assert opened == []  # nạp lười
    assert len(adapter.predict(images)) == len(images)
    adapter.predict(images)
    assert opened == [weights]
