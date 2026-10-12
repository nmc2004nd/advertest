"""Đề xuất contract 002, Phase R3 — Xóa, lưu trữ model và tạo class mapping qua web (marker `db`).

- `POST /class-mappings`: class gốc thuộc dataset, class đích thuộc model (422); preset suy ra
  khi trùng `kitti-coco`; trùng hash → 409; chỉ người đăng ký model hoặc admin (403).
- `DELETE /models/{id}`: model chưa dùng → 204, xóa cả mapping, weights, audit `model.deleted`;
  model đang `checking` hoặc đã có lượt thử nhanh / experiment → 409.
- `POST /models/{id}/archive` và `/restore`: đổi `archived_at`; model lưu trữ không nhận mapping
  mới (409).
- Ai thấy model nào (người dùng chốt 2026-10-12): admin, reviewer thấy mọi model; engineer thấy
  model mình đăng ký và model do admin đăng ký. Model không thấy được: `GET /models/{id}` → 404,
  dùng để ước lượng hay tạo experiment → 422 ở `model_version_id`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from advertest_contracts.enums import ToolJobKind, ToolJobStatus
from advertest_contracts.models import ClassMappingSummary, ModelSummary
from backend.app.db import models as m
from backend.app.storage import weights_key

from .conftest import (
    ONNX_WEIGHTS,
    P5,
    ToolWorker,
    audit_entries,
    csrf,
    error,
    finish_model_check,
    post,
    register_onnx,
)

pytestmark = pytest.mark.db

KITTI_COCO = {
    "Car": "car",
    "Van": "car",
    "Truck": "truck",
    "Pedestrian": "person",
    "Person_sitting": "person",
    "Cyclist": None,
    "Tram": None,
    "Misc": None,
}
MODERATE = {"min_height_px": 25, "max_occluded": 1, "max_truncated": 0.3}


@pytest.fixture
def admin(api: Any) -> TestClient:
    _, _, client = api.user("admin")
    admin: TestClient = client
    return admin


def _registered(client: TestClient) -> ModelSummary:
    response = register_onnx(client, content=ONNX_WEIGHTS.read_bytes() + uuid4().bytes)
    assert response.status_code == 201, response.text
    return ModelSummary.model_validate(response.json())


def _ready(api: Any, client: TestClient, worker: ToolWorker) -> ModelSummary:
    model = _registered(client)
    finish_model_check(worker, api, str(model.id), passed=True)
    return model


def _dataset_version(api: Any) -> UUID:
    with Session(api.engine) as session:
        version_id: UUID = session.scalars(
            select(m.DatasetVersion.id).where(m.DatasetVersion.dataset_id == api.world.dataset_id)
        ).first()
    return version_id


def _mapping(client: TestClient, api: Any, model_id: UUID, **changes: Any) -> Any:
    body = {
        "dataset_version_id": str(_dataset_version(api)),
        "model_version_id": str(model_id),
        "classes": KITTI_COCO,
        "difficulty": MODERATE,
        **changes,
    }
    return post(client, "/class-mappings", body)


def _delete(client: TestClient, model_id: UUID) -> Any:
    return client.delete(f"/models/{model_id}", headers=csrf(client))


def _use_in_quick_try(api: Any, model_id: UUID, owner_id: UUID) -> None:
    """Một lượt thử nhanh đã xong của model (như sau khi người dùng thử nhanh)."""
    now = datetime.now(UTC)
    with Session(api.engine) as session, session.begin():
        spec_id = session.scalars(select(m.AttackSpecRow.id)).first()
        job = m.ToolJob(
            kind=ToolJobKind.QUICK_TRY, payload={}, status=ToolJobStatus.COMPLETED, created_at=now
        )
        session.add(job)
        session.flush()
        session.add(
            m.QuickTry(
                owner_id=owner_id,
                tool_job_id=job.id,
                model_version_id=model_id,
                attack_spec_id=spec_id,
                preset="standard",
                input_uri="s3://artifacts/quick-tries/x/original.png",
                created_at=now,
                expires_at=now + timedelta(hours=1),
            )
        )


def test_create_mapping_detects_preset(api: Any, admin: TestClient) -> None:
    model = _registered(admin)  # mapping tạo được ngay khi model còn `checking`
    response = _mapping(admin, api, model.id)
    assert response.status_code == 201, response.text
    created = ClassMappingSummary.model_validate(response.json())
    assert created.preset == "kitti-coco" and created.model_version_id == model.id
    listed = admin.get("/class-mappings", params={"model": str(model.id)}).json()
    assert [row["id"] for row in listed] == [str(created.id)]
    assert len(audit_entries(api.engine, "class_mapping.created", created.id)) == 1

    assert error(_mapping(admin, api, model.id))[:2] == (409, "conflict")  # trùng hash
    custom = _mapping(admin, api, model.id, classes={**KITTI_COCO, "Cyclist": "bicycle"})
    assert custom.status_code == 201, custom.text
    assert custom.json()["preset"] is None


def test_create_mapping_rejects_unknown_classes(api: Any, admin: TestClient) -> None:
    model = _registered(admin)
    assert _mapping(admin, api, model.id, classes={"Car": "xe hơi"}).status_code == 422
    assert _mapping(admin, api, model.id, classes={"Boat": "car"}).status_code == 422
    assert _mapping(admin, api, model.id, classes={"Car": None}).status_code == 422


@pytest.mark.parametrize("role", ["engineer", "reviewer"])
def test_mapping_and_delete_need_owner(api: Any, admin: TestClient, role: str) -> None:
    model = _registered(admin)  # model của admin
    _, _, client = api.user(role)
    assert error(_mapping(client, api, model.id))[:2] == (403, "forbidden")
    assert error(_delete(client, model.id))[:2] == (403, "forbidden")
    assert error(post(client, f"/models/{model.id}/archive"))[:2] == (403, "forbidden")


def test_delete_unused_model(api: Any, tool_worker: ToolWorker) -> None:
    engineer_id, _, engineer = api.user("engineer")
    model = _registered(engineer)
    assert model.owner_id == engineer_id and model.owner_name  # giao diện ẩn nút với người khác
    assert error(_delete(engineer, model.id))[:2] == (409, "conflict")  # đang checking
    finish_model_check(tool_worker, api, str(model.id), passed=True)
    assert _mapping(engineer, api, model.id).status_code == 201

    response = _delete(engineer, model.id)
    assert response.status_code == 204, response.text
    assert engineer.get(f"/models/{model.id}").status_code == 404
    assert engineer.get("/class-mappings", params={"model": str(model.id)}).json() == []
    assert not api.buckets.models.exists(weights_key(model.weights_sha256))
    assert len(audit_entries(api.engine, "model.deleted", model.id)) == 1
    assert _delete(engineer, model.id).status_code == 404


def test_used_model_is_archived_not_deleted(
    api: Any, admin: TestClient, tool_worker: ToolWorker
) -> None:
    user_id, _, engineer = api.user("engineer")
    model = _ready(api, engineer, tool_worker)
    _use_in_quick_try(api, model.id, user_id)
    assert error(_delete(engineer, model.id))[:2] == (409, "conflict")

    response = post(engineer, f"/models/{model.id}/archive")
    assert response.status_code == 200, response.text
    assert ModelSummary.model_validate(response.json()).archived_at is not None
    assert error(post(engineer, f"/models/{model.id}/archive"))[:2] == (409, "conflict")
    assert error(_mapping(engineer, api, model.id))[:2] == (409, "conflict")
    assert len(audit_entries(api.engine, "model.archived", model.id)) == 1

    # Admin thao tác được model của người khác.
    restored = post(admin, f"/models/{model.id}/restore")
    assert restored.status_code == 200, restored.text
    assert ModelSummary.model_validate(restored.json()).archived_at is None
    assert error(post(engineer, f"/models/{model.id}/restore"))[:2] == (409, "conflict")
    assert _mapping(engineer, api, model.id).status_code == 201


def test_engineer_sees_own_and_admin_models(api: Any, admin: TestClient) -> None:
    _, _, alice = api.user("engineer")
    _, _, bob = api.user("engineer")
    _, _, reviewer = api.user("reviewer")
    alices = _registered(alice)
    admins = _registered(admin)

    def ids(client: TestClient) -> set[str]:
        response = client.get("/models")
        assert response.status_code == 200, response.text
        return {row["id"] for row in response.json()}

    assert {str(alices.id), str(admins.id), api.world.model_id} <= ids(alice)
    bob_sees = ids(bob)
    assert str(alices.id) not in bob_sees  # model của engineer khác
    assert {str(admins.id), api.world.model_id} <= bob_sees  # model admin dùng chung
    assert bob.get(f"/models/{alices.id}").status_code == 404
    assert bob.get(f"/models/{admins.id}").status_code == 200
    for client in (reviewer, admin):
        assert {str(alices.id), str(admins.id)} <= ids(client)

    # Không dùng được model không thấy: ước lượng trả 422 ở model_version_id.
    target = api.target()
    body = api.body(target, [P5.attack("fgsm", [2.0])], model_version_id=str(alices.id))
    status, _, paths = error(post(bob, "/experiments/estimate", body))
    assert status == 422 and "model_version_id" in paths
