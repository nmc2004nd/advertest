import pytest

from advertest_contracts.hashing import sha256_of
from advertest_contracts.ids import content_id
from advertest_contracts.models import (
    ClassEvalMetrics,
    CleanEvalResult,
    EvalMetrics,
    InferenceParams,
    ModelCard,
)
from ml_core.data.mapping import build_mapping
from ml_core.data.slice import create_slice
from ml_core.data.tests.test_mapping_slice import fixture_manifest, model_card
from ml_core.metrics.result import build_clean_eval_result
from ml_core.models.register import lib_versions

PARAMS = InferenceParams(conf=0.001, iou=0.7, max_det=300, operating_conf=0.25, input_size=640)
METRICS = EvalMetrics(
    map50=0.6,
    map50_95=0.4,
    per_class={
        "car": ClassEvalMetrics(ap50=0.7, ap50_95=0.5, num_gt=14),
        "person": ClassEvalMetrics(ap50=0.5, ap50_95=0.3, num_gt=6),
        "truck": ClassEvalMetrics(ap50=0.4, ap50_95=0.2, num_gt=1),
    },
)


def _build(card: ModelCard | None = None) -> CleanEvalResult:
    manifest = fixture_manifest()
    return build_clean_eval_result(
        metrics=METRICS,
        card=card or model_card(),
        slice_spec=create_slice(manifest, size=5, seed=42),
        mapping=build_mapping(sha256_of(manifest), model_card(), "kitti-coco"),
        inference_params=PARAMS,
        cache_key="c" * 64,
        cache_hit=False,
        total_s=1.5,
        device="cpu",
        lib_versions=lib_versions(),
        git_commit="0" * 40,
    )


def test_build_valid_result() -> None:
    result = _build()
    CleanEvalResult.model_validate_json(result.model_dump_json())
    assert result.num_images == 5
    assert result.timing.sec_per_image == pytest.approx(0.3)
    assert result.inference_params.max_det == 300
    assert result.inference_params.operating_conf == 0.25
    assert result.model.weights_sha256 == model_card().weights_sha256
    assert result.slice.dataset_version_sha256 == sha256_of(fixture_manifest())


def test_rejects_mapping_of_other_model() -> None:
    sha = "d" * 64
    other = model_card().model_copy(update={"id": content_id(sha), "weights_sha256": sha})
    with pytest.raises(ValueError, match="Mapping không thuộc model"):
        _build(card=other)
