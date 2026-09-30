"""Nghiệm thu Phase 0, mục Contract (validation.md)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from advertest_contracts import enums
from advertest_contracts.enums import RunStatus, SearchStatus
from advertest_contracts.hashing import canonical_json, compute_fingerprint
from advertest_contracts.models import (
    AttackConfig,
    AttackSpec,
    Manifest,
    RunResult,
    SearchResult,
    compute_spec_sha256,
)
from advertest_contracts.registry import SCHEMAS

# Bảng "Enum dùng chung" trong requirements.md Phase 0.
ENUMS = {
    "Role": {"engineer", "reviewer", "admin"},
    "UserStatus": {"pending", "active", "rejected", "disabled"},
    "RunStatus": {
        "queued", "running", "completed", "failed", "skipped", "stopped_limit", "cancelled",
    },
    "ExperimentStatus": {
        "draft", "queued", "running", "completed", "submitted_for_review", "in_review",
        "approved", "changes_requested", "rejected", "cancelled",
    },
    "SearchStatus": {"found", "not_reached", "below_min", "stopped_limit", "non_monotonic"},
    "StopReason": {"budget", "time"},
    "SkipReason": {"cached", "incompatible", "early_stop"},  # Phase 6: early_stop
    "ComputeKind": {"local", "rented"},
    "BillingMode": {"none", "hourly"},
    "LimitKind": {"budget", "time"},
    "AttackKind": {"attack", "corruption", "occlusion"},
    "AttackAccess": {"white_box", "black_box", "not_applicable"},  # Phase 6: not_applicable
    "RunMode": {"grid", "search"},
    "ThresholdKind": {"relative_drop", "absolute_drop", "attack_success_rate"},
    "ReviewDecision": {"approve", "changes_requested", "reject"},
    "CaseSeverity": {"critical", "major", "minor", "acceptable"},
    # Phase 3: mã lỗi của API worker, enum ProtocolStatus (requirements.md Phase 3).
    # Phase 4: mã xác thực và phân quyền (requirements.md Phase 4, enum ErrorCode).
    "ErrorCode": {
        "not_implemented", "unauthenticated", "forbidden", "not_found", "conflict",
        "invalid_request", "invalid_credentials", "account_pending", "account_rejected",
        "account_disabled", "rate_limited", "csrf_failed", "validation_error",
        # Phase 5 (requirements.md Phase 5, ErrorCode bổ sung; internal_error: plan.md task 1a).
        "not_supported_yet", "queue_limit_reached", "internal_error",
    },
    "ProtocolStatus": {"active", "retired", "dev"},
    # Phase 5: cách hiển thị ảnh failure case.
    "DisplayMode": {"normal", "hidden_unanonymized", "dev_unblurred"},
    # Phase 6: giai đoạn của run patch, nội dung ảnh thứ ba của failure case.
    "RunPhase": {"training", "evaluating"},
    "PerturbationImageKind": {"amplified_noise", "difference", "patch_location"},
}  # fmt: skip


def _mocks(repo: Path, schema: str | None = None) -> list[Path]:
    root = repo / "contracts" / "mocks"
    return sorted((root / schema if schema else root).rglob("*.json"))


@pytest.mark.parametrize("name", sorted(ENUMS))
def test_enum_values_match_requirements(name: str) -> None:
    assert {m.value for m in getattr(enums, name)} == ENUMS[name]


def test_every_mock_validates(repo: Path) -> None:
    files = _mocks(repo)
    assert files, "contracts/mocks rỗng"
    for path in files:
        SCHEMAS[path.parent.name].model_validate_json(path.read_text())


def test_run_result_mocks_cover_every_status(repo: Path) -> None:
    statuses = {
        RunResult.model_validate_json(p.read_text()).status for p in _mocks(repo, "run_result")
    }
    assert statuses == set(RunStatus)


def test_search_result_mocks_cover_every_status(repo: Path) -> None:
    statuses = {
        SearchResult.model_validate_json(p.read_text()).status
        for p in _mocks(repo, "search_result")
    }
    assert statuses == set(SearchStatus)


@pytest.mark.parametrize("status", ["failed", "skipped", "stopped_limit", "cancelled"])
def test_abnormal_run_status_requires_reason(repo: Path, status: str) -> None:
    data = json.loads((repo / "contracts/mocks/run_result/queued.json").read_text())
    data["status"] = status
    data["status_reason"] = None
    with pytest.raises(ValidationError):
        RunResult.model_validate(data)


def test_attack_config_mode_requires_matching_block(repo: Path) -> None:
    grid = json.loads((repo / "contracts/mocks/attack_config/grid.json").read_text())
    search = json.loads((repo / "contracts/mocks/attack_config/search.json").read_text())
    with pytest.raises(ValidationError):
        AttackConfig.model_validate({**grid, "grid": None})
    with pytest.raises(ValidationError):
        AttackConfig.model_validate({**search, "search": None})


def test_canonical_json_ignores_key_order() -> None:
    a = {"b": [1, {"y": 2, "x": 1}], "a": "é"}
    b = {"a": "é", "b": [1, {"x": 1, "y": 2}]}
    assert canonical_json(a) == canonical_json(b)


def _manifest(repo: Path) -> dict[str, Any]:
    return json.loads((repo / "contracts/mocks/manifest/gpu_local.json").read_text())


def test_fingerprint_ignores_environment(repo: Path) -> None:
    base = _manifest(repo)
    changed = copy.deepcopy(base)
    changed["environment"] = {
        "compute_target_id": str(uuid4()), "gpu_model": "Other GPU",
        "cuda_version": "13.0", "driver_version": "999",
    }  # fmt: skip
    a, b = Manifest.model_validate(base), Manifest.model_validate(changed)
    assert compute_fingerprint(a.fingerprint_inputs) == compute_fingerprint(b.fingerprint_inputs)
    assert a.fingerprint == b.fingerprint


def test_fingerprint_changes_with_every_input(repo: Path) -> None:
    inputs = _manifest(repo)["fingerprint_inputs"]
    original = compute_fingerprint(inputs)
    replacements: dict[str, Any] = {
        "config_sha256": "b" * 64,
        "weights_sha256": "b" * 64,
        "dataset_version_sha256": "b" * 64,
        "slice_id": str(uuid4()),
        "slice_sha256": "b" * 64,
        "attack_spec_sha256": "b" * 64,
        "params": {"eps": 8},
        "seed": inputs["seed"] + 1,
        "git_commit": "1" * 40,
        "git_dirty": not inputs["git_dirty"],
        "lib_versions": {**inputs["lib_versions"], "torch": "0.0.1"},
        "docker_image_digest": "none",
    }
    assert set(replacements) == set(inputs), "Test phải phủ mọi trường của fingerprint_inputs"
    for field, value in replacements.items():
        assert compute_fingerprint({**inputs, field: value}) != original, field


def test_seed_catalog_validates_and_hash_matches(repo: Path) -> None:
    specs = json.loads((repo / "contracts/seeds/attack_specs.json").read_text())
    assert specs
    for item in specs:
        spec = AttackSpec.model_validate(item)
        assert spec.spec_sha256 == compute_spec_sha256(spec)
