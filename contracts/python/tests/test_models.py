import copy
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from advertest_contracts.hashing import sha256_of
from advertest_contracts.ids import content_id
from advertest_contracts.models import (
    AttackConfig,
    AttackSpec,
    ClassMapping,
    CleanEvalResult,
    DatasetManifest,
    ErrorResponse,
    ExperimentConfig,
    FailureCaseRecord,
    HealthResponse,
    IgnoreRegion,
    Manifest,
    ModelCard,
    ProtocolBody,
    RunResult,
    SearchResult,
    SliceSpec,
    compute_failure_case_id,
    compute_mapping_sha256,
    compute_slice_sha256,
    compute_spec_sha256,
)

SHA = "a" * 64


def _spec(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": str(uuid4()),
        "name": "pgd_linf",
        "version": 1,
        "kind": "attack",
        "access": "white_box",
        "art_class": "ProjectedGradientDescent",
        "primary_param": {
            "name": "eps",
            "type": "continuous",
            "min": 0,
            "max": 32,
            "unit": "1/255",
        },
        "fixed_params": {"norm": "inf", "max_iter": 10},
        "cost_model": {"passes_per_image": 10},
        "requires_gradients": True,
    }
    data.update(overrides)
    data["spec_sha256"] = compute_spec_sha256(data)
    return data


def test_attack_spec_valid() -> None:
    AttackSpec.model_validate(_spec())


def test_attack_spec_hash_ignores_id() -> None:
    assert _spec()["spec_sha256"] == _spec()["spec_sha256"]


def test_attack_spec_rejects_wrong_hash() -> None:
    data = _spec()
    data["version"] = 2
    with pytest.raises(ValidationError, match="spec_sha256"):
        AttackSpec.model_validate(data)


@pytest.mark.parametrize(
    "overrides",
    [
        {"art_class": None},
        {"kind": "corruption"},
        {"cost_model": {"passes_per_image": 1, "cpu_only": True}},
        {"cost_model": {}},
        {"primary_param": {"name": "s", "type": "discrete", "min": 1, "max": 5, "unit": "level"}},
        {
            "primary_param": {
                "name": "s",
                "type": "discrete",
                "min": 1,
                "max": 5,
                "values": [6],
                "unit": "l",
            }
        },
        {"primary_param": {"name": "e", "type": "continuous", "min": 3, "max": 3, "unit": "1/255"}},
    ],
)
def test_attack_spec_rejects_inconsistent_fields(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        AttackSpec.model_validate(_spec(**overrides))


def _config(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "attack_spec_id": str(uuid4()),
        "spec_sha256": SHA,
        "mode": "grid",
        "grid": {"levels": [2, 4, 8]},
        "seed": 0,
    }
    data.update(overrides)
    return data


SEARCH = {
    "threshold_kind": "relative_drop",
    "threshold": 0.2,
    "lo": 0,
    "hi": 32,
    "tol": 0.5,
    "coarse_n": 5,
    "subset_size": 100,
}


def test_attack_config_modes() -> None:
    AttackConfig.model_validate(_config())
    AttackConfig.model_validate(_config(mode="search", grid=None, search=SEARCH))


@pytest.mark.parametrize(
    "overrides",
    [
        {"grid": None},
        {"mode": "search"},
        {"mode": "search", "grid": None},
        {"search": SEARCH},
        {"mode": "search", "grid": None, "search": {**SEARCH, "lo": 32, "hi": 0}},
    ],
)
def test_attack_config_mode_requires_matching_block(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        AttackConfig.model_validate(_config(**overrides))


def test_experiment_config_needs_attack_and_positive_limit() -> None:
    base = {
        "protocol_id": str(uuid4()),
        "model_version_id": str(uuid4()),
        "slice_id": str(uuid4()),
        "class_mapping_id": str(uuid4()),
        "compute_target_id": str(uuid4()),
        "attacks": [_config()],
        "limit": {"kind": "budget", "value": "12.50"},
    }
    ExperimentConfig.model_validate(base)
    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate({**base, "attacks": []})
    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate({**base, "limit": {"kind": "time", "value": 0}})


METRICS = {
    "clean": {"map50": 0.6, "map50_95": 0.4},
    "attacked": {"map50": 0.3, "map50_95": 0.2},
    "relative_drop": 0.5,
    "absolute_drop": 0.3,
    "attack_success_rate": 0.45,
}


def _run(status: str, code: str | None = None, **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "run_id": str(uuid4()),
        "experiment_id": str(uuid4()),
        "fingerprint": SHA,
        "attack_spec_id": str(uuid4()),
        "level": 4,
        "status": status,
        "status_reason": None if code is None else {"code": code, "message": "lý do"},
        "progress": {"images_done": 0, "images_total": 300},
        "gpu_seconds": 0,
        "failure_case_ids": [],
    }
    if status == "completed":
        data.update(metrics=METRICS, manifest_uri="s3://artifacts/x/manifest.json")
    data.update(overrides)
    return data


@pytest.mark.parametrize(
    ("status", "code"),
    [
        ("queued", None),
        ("running", None),
        ("completed", None),
        ("failed", "error"),
        ("skipped", "cached"),
        ("skipped", "incompatible"),
        ("stopped_limit", "budget"),
        ("stopped_limit", "time"),
        ("cancelled", "cancelled"),
    ],
)
def test_run_result_valid_status_reason(status: str, code: str | None) -> None:
    RunResult.model_validate(_run(status, code))


@pytest.mark.parametrize("status", ["failed", "skipped", "stopped_limit", "cancelled"])
def test_run_result_abnormal_status_requires_reason(status: str) -> None:
    with pytest.raises(ValidationError, match="status_reason"):
        RunResult.model_validate(_run(status))


@pytest.mark.parametrize(
    ("status", "code"),
    [
        ("queued", "error"),
        ("skipped", "budget"),
        ("stopped_limit", "cached"),
        ("failed", "cancelled"),
    ],
)
def test_run_result_rejects_mismatched_reason(status: str, code: str) -> None:
    with pytest.raises(ValidationError):
        RunResult.model_validate(_run(status, code))


def test_run_result_completed_needs_metrics_and_manifest() -> None:
    with pytest.raises(ValidationError):
        RunResult.model_validate(_run("completed", metrics=None))
    with pytest.raises(ValidationError):
        RunResult.model_validate(_run("completed", manifest_uri=None))


def test_run_result_metrics_allow_null_rates() -> None:
    metrics = {
        **METRICS,
        "clean": {"map50": 0.0, "map50_95": 0.0},
        "attacked": {"map50": 0.0, "map50_95": 0.0},
        "relative_drop": None,
        "absolute_drop": 0.0,
        "attack_success_rate": None,
    }
    run = RunResult.model_validate(_run("completed", metrics=metrics))
    assert run.metrics is not None and run.metrics.attack_success_rate is None
    with pytest.raises(ValidationError):
        RunResult.model_validate(_run("completed", metrics={**METRICS, "attack_success_rate": 1.5}))


def test_run_result_progress_and_cost() -> None:
    with pytest.raises(ValidationError):
        RunResult.model_validate(_run("running", progress={"images_done": 5, "images_total": 4}))
    with pytest.raises(ValidationError):
        RunResult.model_validate(_run("running", cost={"amount": "1.2", "currency": "usd"}))
    run = RunResult.model_validate(_run("running", cost={"amount": "1.20", "currency": "USD"}))
    assert run.model_dump(mode="json")["cost"]["amount"] == "1.20"


def test_run_result_cached_from_run_id_only_for_cached_skip() -> None:
    origin = str(uuid4())
    run = RunResult.model_validate(
        _run("skipped", "cached", cached_from_run_id=origin, metrics=METRICS)
    )
    assert str(run.cached_from_run_id) == origin
    assert RunResult.model_validate(_run("skipped", "cached")).cached_from_run_id is None
    for status, code in [("skipped", "incompatible"), ("completed", None), ("failed", "error")]:
        with pytest.raises(ValidationError, match="cached_from_run_id"):
            RunResult.model_validate(_run(status, code, cached_from_run_id=origin))


def test_run_result_partial_metrics_only_when_stopped_limit() -> None:
    partial = {**METRICS, "partial": True}
    run = RunResult.model_validate(_run("stopped_limit", "time", metrics=partial))
    assert run.metrics is not None and run.metrics.partial
    completed = RunResult.model_validate(_run("completed"))
    assert completed.metrics is not None and completed.metrics.partial is False
    with pytest.raises(ValidationError, match="partial"):
        RunResult.model_validate(_run("completed", metrics=partial))
    with pytest.raises(ValidationError, match="partial"):
        RunResult.model_validate(_run("stopped_limit", "time", metrics=METRICS))
    # Run chưa chạy ảnh nào khi chạm giới hạn: không có metric.
    RunResult.model_validate(_run("stopped_limit", "time"))


def _manifest(**env: Any) -> dict[str, Any]:
    inputs = {
        "config_sha256": SHA,
        "weights_sha256": SHA,
        "dataset_version_sha256": SHA,
        "slice_id": "00000000-0000-5000-8000-000000000001",
        "slice_sha256": SHA,
        "attack_spec_sha256": SHA,
        "params": {"eps": 4},
        "seed": 42,
        "git_commit": "0" * 40,
        "git_dirty": False,
        "lib_versions": {
            "torch": "2.14.0",
            "art": "1.20.1",
            "ultralytics": "8.4.163",
            "torchmetrics": "1.9.0",
            "numpy": "2.4.6",
        },
        "docker_image_digest": "none",
    }
    environment = {
        "compute_target_id": None,
        "gpu_model": None,
        "cuda_version": None,
        "driver_version": None,
        **env,
    }
    return {
        "run_id": str(uuid4()),
        "fingerprint": sha256_of(inputs),
        "fingerprint_inputs": inputs,
        "environment": environment,
        "created_at": "2026-09-28T01:02:03Z",
    }


def test_fingerprint_ignores_environment() -> None:
    a = Manifest.model_validate(_manifest())
    b = Manifest.model_validate(_manifest(gpu_model="RTX 3050", compute_target_id=str(uuid4())))
    assert a.fingerprint == b.fingerprint


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("config_sha256", "b" * 64),
        ("weights_sha256", "b" * 64),
        ("dataset_version_sha256", "b" * 64),
        ("slice_id", "00000000-0000-5000-8000-000000000002"),
        ("slice_sha256", "b" * 64),
        ("attack_spec_sha256", "b" * 64),
        ("params", {"eps": 8}),
        ("seed", 43),
        ("git_commit", "1" * 40),
        ("git_dirty", True),
        (
            "lib_versions",
            {
                "torch": "2.13.0",
                "art": "1.20.1",
                "ultralytics": "8.4.163",
                "torchmetrics": "1.9.0",
                "numpy": "2.4.6",
            },
        ),
        ("docker_image_digest", "sha256:" + "c" * 64),
    ],
)
def test_fingerprint_changes_with_every_input(field: str, value: Any) -> None:
    base = _manifest()
    changed = copy.deepcopy(base["fingerprint_inputs"])
    changed[field] = value
    assert sha256_of(changed) != base["fingerprint"]


def test_manifest_rejects_wrong_fingerprint_and_non_utc() -> None:
    with pytest.raises(ValidationError, match="fingerprint"):
        Manifest.model_validate({**_manifest(), "fingerprint": "b" * 64})
    with pytest.raises(ValidationError, match="UTC"):
        Manifest.model_validate({**_manifest(), "created_at": "2026-09-28T08:02:03+07:00"})


def _search(status: str, **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "experiment_id": str(uuid4()),
        "attack_spec_id": str(uuid4()),
        "status": status,
        "threshold_kind": "relative_drop",
        "threshold": 0.2,
        "breaking_point": 6.5 if status == "found" else None,
        "bracket": [6, 7],
        "near_threshold": False,
        "trajectory": [
            {"order": 0, "level": 8, "scope": "subset", "drop": 0.3, "run_id": str(uuid4())}
        ],
    }
    data.update(overrides)
    return data


@pytest.mark.parametrize(
    "status", ["found", "not_reached", "below_min", "stopped_limit", "non_monotonic"]
)
def test_search_result_statuses(status: str) -> None:
    SearchResult.model_validate(_search(status))


@pytest.mark.parametrize(
    "overrides",
    [
        {"breaking_point": None},
        {"bracket": [7, 6]},
        {"confidence_interval": [7, 6]},
    ],
)
def test_search_result_rejects_inconsistent(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        SearchResult.model_validate(_search("found", **overrides))
    with pytest.raises(ValidationError):
        SearchResult.model_validate(_search("not_reached", breaking_point=6.5))


def test_protocol_body() -> None:
    body: dict[str, Any] = {
        "required_attacks": [
            {
                "attack_spec_id": str(uuid4()),
                "spec_sha256": SHA,
                "mode": "grid",
                "grid": {"levels": [4, 8]},
            }
        ],
        "min_slice_size": 300,
        "pass_criteria": [{"threshold_kind": "relative_drop", "threshold": 0.2}],
        "review_severity_threshold": "major",
    }
    ProtocolBody.model_validate(body)
    bad = copy.deepcopy(body)
    bad["required_attacks"][0]["mode"] = "search"
    with pytest.raises(ValidationError):
        ProtocolBody.model_validate(bad)


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        RunResult.model_validate({**_run("queued"), "unexpected": 1})


def test_health_status_must_match_dependencies() -> None:
    ok = {"ok": True, "detail": None}
    down = {"ok": False, "detail": "timeout"}
    base = {"version": "0.0.0", "git_commit": "unknown", "postgres": ok}
    HealthResponse.model_validate({**base, "status": "ok", "minio": ok})
    HealthResponse.model_validate({**base, "status": "degraded", "minio": down})
    with pytest.raises(ValidationError):
        HealthResponse.model_validate({**base, "status": "ok", "minio": down})
    with pytest.raises(ValidationError):
        HealthResponse.model_validate({**base, "status": "degraded", "minio": ok})
    with pytest.raises(ValidationError):
        HealthResponse.model_validate({**base, "status": "ok", "minio": ok, "git_commit": "abc"})


def test_error_response_only_known_codes() -> None:
    ErrorResponse.model_validate({"error": {"code": "not_implemented", "message": "x"}})
    with pytest.raises(ValidationError):
        ErrorResponse.model_validate({"error": {"code": "teapot", "message": "x"}})


def _dataset_manifest() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[2] / "mocks/dataset_manifest/kitti_small.json"
    data: dict[str, Any] = json.loads(path.read_text())
    return data


def test_dataset_manifest_mock_valid() -> None:
    DatasetManifest.model_validate(_dataset_manifest())


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["images"].append(copy.deepcopy(d["images"][0])),  # image_id trùng
        lambda d: d["images"].reverse(),  # không sắp theo image_id
        lambda d: d["annotations"].reverse(),  # annotations không sắp
        lambda d: d["annotations"][0].update(image_id="999999"),  # ảnh không tồn tại
        lambda d: d["annotations"][0].update(category="DontCare"),  # category lạ
        lambda d: d["annotations"][0].update(bbox=[10, 10, 5, 20]),  # x2 < x1
        lambda d: d["annotations"][0].update(bbox=[0, 0, 1300, 20]),  # vượt khung ảnh
        lambda d: d["ignore_regions"][0].update(source="foo:Car"),  # nguồn không hợp lệ
        lambda d: d["categories"].append("Car"),  # categories trùng
        lambda d: d["source"].update(format="voc"),
    ],
)
def test_dataset_manifest_rejects_inconsistent(mutate: Any) -> None:
    data = _dataset_manifest()
    mutate(data)
    with pytest.raises(ValidationError):
        DatasetManifest.model_validate(data)


@pytest.mark.parametrize("source", ["dont_care", "unmapped:Cyclist", "difficulty:Car"])
def test_ignore_region_accepts_sources(source: str) -> None:
    IgnoreRegion(image_id="000001", bbox=(0, 0, 10, 10), source=source)


def test_dataset_manifest_hash_unchanged_by_ignore_source_pattern() -> None:
    manifest = json.loads(
        (Path(__file__).resolve().parents[3] / "tests/fixtures/manifest.json").read_text()
    )
    assert sha256_of(DatasetManifest.model_validate(manifest)) == (
        "9f5b413eb8a78a6a4b216011c2cf26e5b877728f7a160bbb80964a917d976069"
    )


# ---------------------------------------------------------------- Phase 1

LIBS = {
    "torch": "2.14.0",
    "art": "1.20.1",
    "ultralytics": "8.4.163",
    "torchmetrics": "1.9.0",
    "numpy": "2.4.6",
}
DIFFICULTY = {"min_height_px": 25, "max_occluded": 1, "max_truncated": 0.3}


def _model_card(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": str(content_id(SHA)),
        "name": "yolov8n-coco",
        "framework": "ultralytics",
        "architecture": "yolov8n",
        "weights_sha256": SHA,
        "class_names": ["person", "bicycle", "car"],
        "input_size": 640,
        "supports_gradients": True,
        "gradient_check": {"passed": True, "checked_at": "2026-09-28T00:00:00Z", "details": None},
        "lib_versions": LIBS,
    }
    data.update(overrides)
    return data


def test_model_card_valid() -> None:
    ModelCard.model_validate(_model_card())


def test_model_card_failed_gradient_check_valid() -> None:
    ModelCard.model_validate(
        _model_card(
            supports_gradients=False,
            gradient_check={
                "passed": False,
                "checked_at": "2026-09-28T00:00:00Z",
                "details": "gradient = 0",
            },
        )
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"id": str(uuid4())},  # id không phải content_id
        {"supports_gradients": False},  # lệch gradient_check.passed
        {
            "supports_gradients": False,
            "gradient_check": {
                "passed": False,
                "checked_at": "2026-09-28T00:00:00Z",
                "details": None,
            },
        },  # fail mà không có lý do
        {
            "gradient_check": {"passed": True, "checked_at": "2026-09-28T07:00:00+07:00"}
        },  # không phải UTC
        {"class_names": ["car", "car"]},
        {"framework": "onnx"},
        {
            "lib_versions": {"torch": "2.14.0", "art": "1.20.1", "ultralytics": "8.4.163"}
        },  # thiếu khóa
    ],
)
def test_model_card_rejects(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ModelCard.model_validate(_model_card(**overrides))


def _mapping(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "dataset_version_sha256": SHA,
        "model_id": str(content_id(SHA)),
        "preset": "kitti-coco",
        "classes": {"Car": "car", "Van": "car", "Cyclist": None},
        "difficulty": DIFFICULTY,
    }
    data.update(overrides)
    data["mapping_sha256"] = compute_mapping_sha256(data)
    data["id"] = str(content_id(data["mapping_sha256"]))
    return data


def test_class_mapping_valid() -> None:
    ClassMapping.model_validate(_mapping())


def test_class_mapping_hash_covers_difficulty() -> None:
    changed = _mapping(difficulty={**DIFFICULTY, "min_height_px": 40})
    assert changed["mapping_sha256"] != _mapping()["mapping_sha256"]
    assert _mapping(difficulty=None)["mapping_sha256"] != _mapping()["mapping_sha256"]


def test_class_mapping_rejects_wrong_hash_and_id() -> None:
    data = _mapping()
    data["classes"] = {"Car": "car"}
    with pytest.raises(ValidationError):
        ClassMapping.model_validate(data)
    data = _mapping()
    data["id"] = str(uuid4())
    with pytest.raises(ValidationError):
        ClassMapping.model_validate(data)


def _slice(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "dataset_version_sha256": SHA,
        "filter": {"classes": ["Car", "Pedestrian"], "difficulty": DIFFICULTY, "min_objects": 1},
        "seed": 42,
        "size": 2,
        "image_ids": ["000001", "000002"],
    }
    data.update(overrides)
    data["image_ids_sha256"] = sha256_of(data["image_ids"])
    data["slice_sha256"] = compute_slice_sha256(data)
    data["id"] = str(content_id(data["slice_sha256"]))
    return data


def test_slice_spec_valid() -> None:
    SliceSpec.model_validate(_slice())


def test_slice_hash_depends_on_dataset_and_filter() -> None:
    base = _slice()
    other_dataset = _slice(dataset_version_sha256="b" * 64)
    assert other_dataset["image_ids_sha256"] == base["image_ids_sha256"]
    assert other_dataset["slice_sha256"] != base["slice_sha256"]
    assert other_dataset["id"] != base["id"]
    stricter = _slice(
        filter={"classes": ["Car", "Pedestrian"], "difficulty": {**DIFFICULTY, "max_occluded": 0}}
    )
    assert stricter["slice_sha256"] != base["slice_sha256"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"image_ids": ["000002", "000001"]},  # không sắp xếp
        {"image_ids": ["000001", "000001"]},  # trùng
        {"size": 3},  # len != size
        {"filter": {"classes": ["Pedestrian", "Car"], "difficulty": None}},  # classes không sắp
        {"filter": {"classes": ["Car"], "difficulty": None, "min_objects": 0}},
    ],
)
def test_slice_spec_rejects(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        SliceSpec.model_validate(_slice(**overrides))


def test_slice_spec_rejects_wrong_hashes() -> None:
    for field in ("image_ids_sha256", "slice_sha256"):
        data = _slice()
        data[field] = "c" * 64
        with pytest.raises(ValidationError):
            SliceSpec.model_validate(data)


def _eval(**overrides: Any) -> dict[str, Any]:
    sl = _slice()
    mp = _mapping()
    data: dict[str, Any] = {
        "model": {"id": str(content_id(SHA)), "weights_sha256": SHA},
        "slice": {
            "id": sl["id"],
            "slice_sha256": sl["slice_sha256"],
            "image_ids_sha256": sl["image_ids_sha256"],
            "dataset_version_sha256": SHA,
        },
        "class_mapping": {"id": mp["id"], "mapping_sha256": mp["mapping_sha256"]},
        "inference_params": {
            "conf": 0.001,
            "iou": 0.7,
            "max_det": 300,
            "operating_conf": 0.25,
            "input_size": 640,
        },
        "metrics": {
            "map50": 0.6,
            "map50_95": 0.4,
            "per_class": {
                "car": {"ap50": 0.7, "ap50_95": 0.5, "num_gt": 14},
                "truck": {"ap50": None, "ap50_95": None, "num_gt": 0},
            },
        },
        "num_images": 2,
        "cache": {"key": SHA, "hit": False},
        "timing": {"total_s": 1.5, "sec_per_image": 0.75},
        "device": "cpu",
        "lib_versions": LIBS,
        "git_commit": "0" * 40,
    }
    data.update(overrides)
    return data


def test_clean_eval_result_valid() -> None:
    CleanEvalResult.model_validate(_eval())


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["model"].update(id=str(uuid4())),
        lambda d: d["slice"].update(id=str(uuid4())),
        lambda d: d["class_mapping"].update(id=str(uuid4())),
        lambda d: d["metrics"]["per_class"]["truck"].update(num_gt=1),  # AP null nhưng có GT
        lambda d: d["metrics"]["per_class"]["car"].update(ap50=None),
        lambda d: d["metrics"]["per_class"]["car"].update(ap50=-1),  # giá trị -1 của torchmetrics
        lambda d: d["metrics"].update(map50=1.2),
        lambda d: d["inference_params"].update(max_det=0),
        lambda d: d.update(git_commit="unknown"),
    ],
)
def test_clean_eval_result_rejects(mutate: Any) -> None:
    data = copy.deepcopy(_eval())
    mutate(data)
    with pytest.raises(ValidationError):
        CleanEvalResult.model_validate(data)


CASE_RUN_ID = UUID("acd64412-55de-5ac6-b8d0-8ca96f218a64")


def _case(**overrides: Any) -> dict[str, Any]:
    fingerprint, image_id = "a" * 64, "000057"
    data: dict[str, Any] = {
        "id": str(compute_failure_case_id(fingerprint, CASE_RUN_ID, image_id)),
        "run_id": str(CASE_RUN_ID),
        "fingerprint": fingerprint,
        "image_id": image_id,
        "lost_objects": 2,
        "new_false_positives": 1,
        "severity_score": 2.5,
        "detections": {
            "ground_truth": [{"bbox": [1, 2, 30, 40], "class_name": "car", "score": None}],
            "clean": [{"bbox": [1, 2, 31, 41], "class_name": "car", "score": 0.9}],
            "attacked": [],
            "ignore_regions": [{"bbox": [0, 0, 5, 5], "source": "dont_care"}],
        },
        "artifacts": {
            "clean_png": "runs/x/cases/000057/clean.png",
            "adversarial_png": "runs/x/cases/000057/adversarial.png",
            "perturbation_png": "runs/x/cases/000057/perturbation.png",
        },
    }
    data.update(overrides)
    return data


def test_failure_case_valid_and_id_is_deterministic() -> None:
    case = FailureCaseRecord.model_validate(_case())
    assert case.id == compute_failure_case_id("a" * 64, CASE_RUN_ID, "000057")
    assert case.id != compute_failure_case_id("a" * 64, CASE_RUN_ID, "000058")
    assert case.id != compute_failure_case_id("b" * 64, CASE_RUN_ID, "000057")
    # Cùng fingerprint, khác run (Phase 3): id khác nhau.
    assert case.id != compute_failure_case_id("a" * 64, uuid4(), "000057")
    assert case.artifacts.clean_thumb is None and case.artifacts.adversarial_thumb is None


def test_failure_case_id_must_match_run_id() -> None:
    with pytest.raises(ValidationError, match="compute_failure_case_id"):
        FailureCaseRecord.model_validate(_case(run_id=str(uuid4())))


def test_failure_case_rejects_wrong_id_and_severity() -> None:
    with pytest.raises(ValidationError, match="compute_failure_case_id"):
        FailureCaseRecord.model_validate(_case(id=str(uuid4())))
    with pytest.raises(ValidationError, match="severity_score"):
        FailureCaseRecord.model_validate(_case(severity_score=3.0))
    with pytest.raises(ValidationError):
        FailureCaseRecord.model_validate(
            _case(lost_objects=0, new_false_positives=0, severity_score=0.0)
        )


def test_failure_case_score_rules() -> None:
    base = _case()
    gt_with_score = copy.deepcopy(base)
    gt_with_score["detections"]["ground_truth"][0]["score"] = 0.5
    with pytest.raises(ValidationError, match="ground_truth"):
        FailureCaseRecord.model_validate(gt_with_score)
    pred_without_score = copy.deepcopy(base)
    pred_without_score["detections"]["attacked"] = [
        {"bbox": [1, 2, 3, 4], "class_name": "car", "score": None}
    ]
    with pytest.raises(ValidationError, match="prediction"):
        FailureCaseRecord.model_validate(pred_without_score)
    bad_source = copy.deepcopy(base)
    bad_source["detections"]["ignore_regions"][0]["source"] = "foo"
    with pytest.raises(ValidationError):
        FailureCaseRecord.model_validate(bad_source)
