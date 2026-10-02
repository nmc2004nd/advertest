"""validation.md Phase 8, Protocol (`test_protocols.py`)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine

from advertest_contracts.hashing import sha256_of

from .conftest import (
    LEVELS,
    P5,
    Flow,
    audit_count,
    error,
    max_drop,
    ok,
    post,
    protocol_body,
    required_grid,
    unique,
)

pytestmark = pytest.mark.db
OPENAPI = Path(__file__).resolve().parents[3] / "contracts" / "openapi.json"


def test_reviewer_creates_active_v1_with_audit(api: Any, app_engine: Engine) -> None:
    _, _, reviewer = api.user("reviewer")
    created = ok(
        post(reviewer, "/protocols", {"name": unique("p"), "body": protocol_body()})
    ).json()
    assert (created["status"], created["version"]) == ("active", 1)
    assert created["body_sha256"] == sha256_of(created["body"])
    assert audit_count(app_engine, "protocol.created", created["id"]) == 1


@pytest.mark.parametrize("role", ["engineer", "admin"])
def test_engineer_or_admin_cannot_create(api: Any, role: str) -> None:
    client = api.admin() if role == "admin" else api.user(role)[2]
    response = post(client, "/protocols", {"name": unique("p"), "body": protocol_body()})
    assert response.status_code == 403


def test_new_version_keeps_old_and_retires_it(api: Any, app_engine: Engine) -> None:
    _, _, reviewer = api.user("reviewer")
    v1 = ok(post(reviewer, "/protocols", {"name": unique("p"), "body": protocol_body()})).json()
    body2 = protocol_body(pass_criteria=[max_drop("fgsm", 4.0, threshold=0.8)])
    v2 = ok(post(reviewer, f"/protocols/{v1['id']}/versions", {"body": body2})).json()
    assert v2["id"] != v1["id"] and (v2["name"], v2["version"]) == (v1["name"], 2)
    assert v2["status"] == "active"
    old = reviewer.get(f"/protocols/{v1['id']}").json()
    assert old["status"] == "retired"
    assert old["body"] == v1["body"] and old["body_sha256"] == v1["body_sha256"]
    assert sha256_of(old["body"]) == v1["body_sha256"]
    assert audit_count(app_engine, "protocol.versioned", v2["id"]) == 1
    # Chỉ tạo version từ bản mới nhất.
    stale = post(reviewer, f"/protocols/{v1['id']}/versions", {"body": protocol_body()})
    assert error(stale)[:2] == (409, "conflict")


def test_no_endpoint_edits_a_version() -> None:
    """OpenAPI không có PUT/PATCH/DELETE nào trên protocol; POST chỉ để tạo, tạo version và ngừng
    dùng."""
    paths: dict[str, dict[str, Any]] = json.loads(OPENAPI.read_text())["paths"]
    for path, methods in paths.items():
        if not path.startswith("/protocols"):
            continue
        assert not {"put", "patch", "delete"} & set(methods), path
        if "post" in methods:
            assert path in {
                "/protocols",
                "/protocols/{protocol_id}/versions",
                "/protocols/{protocol_id}/retire",
            }, path


@pytest.mark.parametrize(
    "body",
    [
        # Tiêu chí tham chiếu attack không có trong required_attacks.
        protocol_body(pass_criteria=[max_drop("pgd_linf", 4.0)]),
        # min_breaking_point với attack quét lưới.
        protocol_body(
            pass_criteria=[{**max_drop("fgsm", 4.0), "kind": "min_breaking_point"}],
        ),
        # Patch ở chế độ tìm ngưỡng.
        protocol_body(
            required_attacks=[
                {
                    "attack_spec_name": "adv_patch",
                    "spec_sha256": required_grid("adv_patch", [1.0])["spec_sha256"],
                    "mode": "search",
                    "search": {
                        "threshold_kind": "relative_drop",
                        "threshold": 0.2,
                        "class_filter": None,
                        "lo": 0.0,
                        "hi": 1.0,
                        "max_tol": 0.1,
                        "min_bootstrap_samples": 200,
                    },
                }
            ],
            pass_criteria=[
                {
                    "kind": "min_breaking_point",
                    "attack_spec_name": "adv_patch",
                    "level": 0.5,
                    "threshold_kind": "relative_drop",
                    "threshold": 0.2,
                    "class_filter": None,
                }
            ],
        ),
    ],
    ids=["criterion-unknown-attack", "breaking-point-on-grid", "patch-search"],
)
def test_invalid_protocol_bodies(api: Any, body: dict[str, Any]) -> None:
    _, _, reviewer = api.user("reviewer")
    response = post(reviewer, "/protocols", {"name": unique("p"), "body": body})
    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "attack",
    [
        {**required_grid("fgsm", [2.0, 4.0]), "attack_spec_name": "khong_ton_tai"},
        {**required_grid("fgsm", [2.0, 4.0]), "spec_sha256": "0" * 64},
    ],
    ids=["unknown-spec", "wrong-sha"],
)
def test_unknown_spec_or_wrong_sha(api: Any, attack: dict[str, Any]) -> None:
    _, _, reviewer = api.user("reviewer")
    body = protocol_body(
        required_attacks=[attack],
        pass_criteria=[max_drop(attack["attack_spec_name"], 4.0)],
    )
    response = post(reviewer, "/protocols", {"name": unique("p"), "body": body})
    assert response.status_code == 422, response.text


def test_retired_protocol_not_selectable_but_old_experiment_submits(flow: Flow) -> None:
    old = flow.experiment()
    ok(post(flow.reviewer, f"/protocols/{flow.protocol['id']}/retire"))
    listed = {p["id"] for p in flow.owner.get("/protocols").json()}
    assert flow.protocol["id"] not in listed
    # Experiment mới đủ attack bắt buộc nhưng gắn protocol đã ngừng dùng → không tạo được.
    body = flow.api.body(flow.target, [P5.attack("fgsm", LEVELS)], protocol_id=flow.protocol["id"])
    assert post(flow.owner, "/experiments", body).status_code == 422
    # Experiment cũ gắn protocol đã ngừng dùng vẫn gửi duyệt được.
    assert flow.submit(old).status_code == 200
