from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from ml_core.models.estimator import build_estimator
from ml_core.models.tests.conftest import LOW_PARAMS
from ml_core.models.wrapper import load_detection_model


def test_predict_and_loss_gradient(random_weights: Path, images: NDArray[np.float32]) -> None:
    estimator = build_estimator(load_detection_model(random_weights), LOW_PARAMS)
    assert estimator.input_shape == (3, 640, 640)
    assert estimator.channels_first
    assert tuple(estimator.clip_values) == (0.0, 1.0)

    preds = estimator.predict(images)
    assert len(preds) == len(images)
    for p in preds:
        assert set(p) == {"boxes", "labels", "scores"}
        assert p["boxes"].ndim == 2 and p["boxes"].shape[1] == 4

    targets = [{"boxes": p["boxes"][:5], "labels": p["labels"][:5]} for p in preds]
    grad = estimator.loss_gradient(images, targets)
    assert grad.shape == images.shape
    assert np.all(np.isfinite(grad))
    assert np.any(grad != 0)
