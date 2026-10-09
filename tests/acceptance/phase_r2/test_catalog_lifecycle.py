"""validation.md Phase R2, Group 4 — Vòng đời catalog attack (`test_catalog_lifecycle.py`, `db`).

- `draft → checking → pending_approval → active`; version cũ chuyển `retired` cùng giao dịch;
  `check_failed` chạy lại được; reject đưa về `draft`.
- Người tạo tự approve → 403; engineer approve → 403; reviewer khác người tạo → 200.
- Adapter không có trong registry hoặc `fixed_params` sai → 422; trùng `spec_sha256` → 409; version
  nhảy cóc → 422.
- Sửa metadata không đổi `spec_sha256`/version, có audit log.
- Experiment hoặc protocol dùng spec không `active` → 422; experiment cũ chốt spec `retired` vẫn
  đọc và chạy được.

Job `spec_check` được giả lập qua API nội bộ của worker (`ToolWorker` trong conftest); worker
công cụ thật ở `test_tool_worker.py` (Group 5).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from advertest_contracts.models import AttackSpecAdminView, AttackSpecView

from .conftest import (
    P5,
    ToolWorker,
    audit_entries,
    error,
    max_drop,
    ok,
    post,
    spec_check_report,
    spec_of,
    unique,
)

pytestmark = pytest.mark.db

MOCKS = Path(__file__).resolve().parents[3] / "contracts" / "mocks"
SNOW_LIGHT: dict[str, Any] = json.loads(
    (MOCKS / "attack_spec_create" / "snow_light.json").read_text()
)


def create_body(name: str, version: int = 1, **changes: Any) -> dict[str, Any]:
    body = {**SNOW_LIGHT["body"], "name": name, "version": version, **changes}
    return {"body": body, "metadata": SNOW_LIGHT["metadata"]}


# Version kế tiếp: dải severity hẹp hơn (nội dung khác nên hash khác).
NARROW = {"primary_param": {**SNOW_LIGHT["body"]["primary_param"], "max": 2, "values": [1, 2]}}


@pytest.fixture
def people(api: Any) -> dict[str, Any]:
    creator_id, _, creator = api.user("admin", "reviewer")  # có cả quyền duyệt
    _, _, admin = api.user("admin")
    reviewer_id, _, reviewer = api.user("reviewer")
    _, _, engineer = api.user("engineer")
    return {
        "creator": creator, "creator_id": str(creator_id), "admin": admin,
        "reviewer": reviewer, "reviewer_id": str(reviewer_id), "engineer": engineer,
    }  # fmt: skip


def _create(client: TestClient, body: dict[str, Any]) -> AttackSpecAdminView:
    response = post(client, "/admin/attack-specs", body)
    assert response.status_code == 201, response.text
    return AttackSpecAdminView.model_validate(response.json())


def _admin_view(client: TestClient, spec_id: str) -> AttackSpecAdminView:
    cursor = None
    while True:
        params = {"limit": 200, **({"cursor": cursor} if cursor else {})}
        page = client.get("/admin/attack-specs", params=params).json()
        for item in page["items"]:
            if item["id"] == spec_id:
                return AttackSpecAdminView.model_validate(item)
        cursor = page["next_cursor"]
        if cursor is None:
            raise AssertionError(f"Không thấy spec {spec_id}")


def _check(worker: ToolWorker, api: Any, spec_id: str, *, passed: bool) -> None:
    lease = worker.lease()
    assert lease is not None and lease["kind"] == "spec_check"
    bundle = worker.bundle(lease["job_id"])
    assert bundle["payload"]["kind"] == "spec_check"
    assert bundle["payload"]["spec"]["id"] == spec_id
    report = spec_check_report(
        spec_id, worker.target_id, passed=passed, now=api.clock().isoformat()
    )
    response = worker.result(lease["job_id"], {"lease_id": lease["lease_id"], "report": report})
    assert response.status_code == 204, response.text


def _active_ids(client: TestClient) -> set[str]:
    response = client.get("/attack-specs")
    assert response.status_code == 200, response.text
    return {str(AttackSpecView.model_validate(s).id) for s in response.json()}


def test_lifecycle_to_active_and_retire_previous(
    api: Any, people: dict[str, Any], tool_worker: ToolWorker
) -> None:
    name = unique("snow_light")
    created = _create(people["creator"], create_body(name))
    spec_id = str(created.id)
    assert created.status == "checking" and created.check is None
    assert created.created_by is not None and str(created.created_by.id) == people["creator_id"]
    assert created.metadata is not None and created.metadata.display_name == "Tuyết nhẹ"
    assert len(audit_entries(api.engine, "attack_spec.created", spec_id)) == 1

    _check(tool_worker, api, spec_id, passed=True)
    pending = _admin_view(people["admin"], spec_id)
    assert pending.status == "pending_approval" and pending.check is not None
    assert pending.check.passed
    assert spec_id not in _active_ids(people["engineer"])
    pending_list = people["reviewer"].get("/attack-specs/pending")
    assert pending_list.status_code == 200
    assert spec_id in {s["id"] for s in pending_list.json()}

    approve = f"/attack-specs/{spec_id}/approve"
    assert error(post(people["engineer"], approve))[:2] == (403, "forbidden")
    assert error(post(people["creator"], approve))[:2] == (403, "forbidden")  # nguyên tắc 1
    response = post(people["reviewer"], approve)
    assert response.status_code == 200, response.text
    active = AttackSpecAdminView.model_validate(response.json())
    assert active.status == "active" and active.is_active
    assert active.approved_by is not None and str(active.approved_by.id) == people["reviewer_id"]
    listed = {s["id"]: s for s in people["engineer"].get("/attack-specs").json()}
    assert listed[spec_id]["metadata"]["display_name"] == "Tuyết nhẹ"
    assert len(audit_entries(api.engine, "attack_spec.approved", spec_id)) == 1

    # Version 2 cùng name: duyệt xong thì version 1 chuyển retired trong cùng giao dịch.
    v2 = _create(people["admin"], create_body(name, 2, **NARROW))
    _check(tool_worker, api, str(v2.id), passed=True)
    ok(post(people["reviewer"], f"/attack-specs/{v2.id}/approve"))
    assert _admin_view(people["admin"], spec_id).status == "retired"
    assert _admin_view(people["admin"], str(v2.id)).status == "active"
    ids = _active_ids(people["engineer"])
    assert str(v2.id) in ids and spec_id not in ids


def test_check_failed_can_rerun_and_reject_returns_to_draft(
    api: Any, people: dict[str, Any], tool_worker: ToolWorker
) -> None:
    created = _create(people["admin"], create_body(unique("snow_light")))
    spec_id = str(created.id)
    _check(tool_worker, api, spec_id, passed=False)
    failed = _admin_view(people["admin"], spec_id)
    assert failed.status == "check_failed" and failed.check is not None
    assert not failed.check.passed
    assert error(post(people["reviewer"], f"/attack-specs/{spec_id}/approve"))[:2] == (
        409, "conflict",
    )  # fmt: skip

    rerun = post(people["admin"], f"/admin/attack-specs/{spec_id}/check")
    assert rerun.status_code == 200, rerun.text
    assert rerun.json()["status"] == "checking"
    _check(tool_worker, api, spec_id, passed=True)
    assert _admin_view(people["admin"], spec_id).status == "pending_approval"

    reject = post(people["reviewer"], f"/attack-specs/{spec_id}/reject", {"reason": "Nhãn sai."})
    assert reject.status_code == 200, reject.text
    assert reject.json()["status"] == "draft"
    # Không chạy lại được từ trạng thái khác check_failed.
    assert error(post(people["admin"], f"/admin/attack-specs/{spec_id}/check"))[:2] == (
        409, "conflict",
    )  # fmt: skip


@pytest.mark.parametrize(
    ("changes", "status"),
    [
        ({"adapter": "corruption.khong_co"}, 422),
        ({"fixed_params": {"corruption": "gaussian_noise", "applied_to": "image_region"}}, 422),
        ({"fixed_params": {"corruption": "snow", "khong_co": True}}, 422),
    ],
)
def test_invalid_spec_rejected(
    people: dict[str, Any], changes: dict[str, Any], status: int
) -> None:
    response = post(people["admin"], "/admin/attack-specs", create_body(unique("bad"), **changes))
    assert response.status_code == status, response.text


def test_duplicate_hash_and_version_jump(people: dict[str, Any]) -> None:
    fog = spec_of("fog").model_dump(mode="json", exclude={"id", "spec_sha256"})
    body = {"body": fog, "metadata": SNOW_LIGHT["metadata"]}
    assert error(post(people["admin"], "/admin/attack-specs", body))[:2] == (409, "conflict")

    jump = {**fog, "version": 3, **NARROW}
    status, _, _ = error(post(people["admin"], "/admin/attack-specs", {**body, "body": jump}))
    assert status == 422
    fresh = create_body(unique("new"), version=2)
    assert error(post(people["admin"], "/admin/attack-specs", fresh))[0] == 422


def test_metadata_patch_keeps_hash(api: Any, people: dict[str, Any]) -> None:
    fog = spec_of("fog")
    meta = {
        "display_name": "Sương mù",
        "description": "Sương mù tổng hợp.",
        "realism": "high",
        "level_labels": {"1": "rất nhẹ", "5": "rất dày"},
    }
    response = people["admin"].patch(
        f"/admin/attack-specs/{fog.id}/metadata", json=meta, headers=P5.csrf(people["admin"])
    )
    assert response.status_code == 200, response.text
    view = AttackSpecAdminView.model_validate(response.json())
    assert (view.spec_sha256, view.version) == (fog.spec_sha256, fog.version)
    assert view.metadata is not None and view.metadata.label_for(5) == "rất dày"
    assert len(audit_entries(api.engine, "attack_spec.metadata_updated", fog.id)) >= 1
    listed = {s["id"]: s for s in people["engineer"].get("/attack-specs").json()}
    assert listed[str(fog.id)]["metadata"]["display_name"] == "Sương mù"
    assert listed[str(fog.id)]["spec_sha256"] == fog.spec_sha256


def test_non_active_spec_rejected_retired_still_runs(
    api: Any, people: dict[str, Any], tool_worker: ToolWorker
) -> None:
    name = unique("snow_light")
    v1 = _create(people["admin"], create_body(name))
    _check(tool_worker, api, str(v1.id), passed=True)

    _, _, engineer = api.user("engineer")
    target = api.target()
    attack = {
        "attack_spec_id": str(v1.id), "spec_sha256": v1.spec_sha256, "mode": "grid",
        "grid": {"levels": [1.0]}, "seed": 0,
    }  # fmt: skip
    # pending_approval: không dùng được trong experiment hay protocol.
    assert error(post(engineer, "/experiments", api.body(target, [attack])))[0] == 422
    required = {"attack_spec_name": name, "spec_sha256": v1.spec_sha256, "mode": "grid",
                "grid": {"levels": [1.0]}}  # fmt: skip
    status, _, _ = error(
        post(people["reviewer"], "/protocols", {
            "name": unique("p"),
            "body": {"description": "Spec chưa active.", "required_attacks": [required],
                     "min_slice_size": 5, "pass_criteria": [max_drop(name, 1.0)]},
        })
    )  # fmt: skip
    assert status == 422

    ok(post(people["reviewer"], f"/attack-specs/{v1.id}/approve"))
    old = ok(post(engineer, "/experiments", api.body(target, [attack]))).json()["id"]
    v2 = _create(people["admin"], create_body(name, 2, **NARROW))
    _check(tool_worker, api, str(v2.id), passed=True)
    ok(post(people["reviewer"], f"/attack-specs/{v2.id}/approve"))
    assert _admin_view(people["admin"], str(v1.id)).status == "retired"

    assert error(post(engineer, "/experiments", api.body(target, [attack])))[0] == 422
    assert engineer.get(f"/experiments/{old}").status_code == 200
    api.work(target, old)
    runs = engineer.get(f"/experiments/{old}/runs").json()
    assert [r["status"] for r in runs] == ["completed"]
    clone = engineer.get(f"/experiments/{old}/clone")
    assert clone.status_code == 200
    (cloned,) = clone.json()["config"]["attacks"]
    assert cloned["attack_spec_id"] == str(v2.id)  # nhân bản lên version đang active
