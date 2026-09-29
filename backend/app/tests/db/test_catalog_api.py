"""API đọc tài nguyên cho wizard với Postgres thật (validation.md Phase 5, Đọc tài nguyên —
phần của Group 1: lọc, `online`, `queue_length`, 404)."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from advertest_contracts.enums import (
    AttackAccess,
    AttackKind,
    BillingMode,
    ComputeKind,
    ExperimentStatus,
    LimitKind,
    ProtocolStatus,
    Role,
)
from advertest_contracts.models import (
    AttackSpec,
    ClassMappingSummary,
    ComputeTargetPublic,
    DatasetSummary,
    DatasetVersionSummary,
    ErrorResponse,
    ModelSummary,
    ProtocolSummary,
    SliceSummary,
    compute_spec_sha256,
)
from backend.app.db import models as m

from .test_auth_api import Env, _login, _user, env  # fixture dùng chung
from .test_worker_services import T0

pytestmark = pytest.mark.db
__all__ = ["env"]
SEEDS = Path(__file__).resolve().parents[4] / "contracts" / "seeds" / "attack_specs.json"


def _sha() -> str:
    return uuid.uuid4().hex * 2


@dataclass(frozen=True)
class World:
    tag: str
    model_version: uuid.UUID
    other_model_version: uuid.UUID
    dataset: uuid.UUID
    dv_old: uuid.UUID
    dv_new: uuid.UUID
    slices_old: tuple[uuid.UUID, uuid.UUID]
    slice_new: uuid.UUID
    mapping_old: uuid.UUID
    mapping_new: uuid.UUID
    mapping_other_model: uuid.UUID
    spec_active: uuid.UUID
    spec_inactive: uuid.UUID
    protocols: dict[ProtocolStatus, uuid.UUID]
    targets: dict[str, uuid.UUID]


def _spec_row(tag: str, *, active: bool) -> m.AttackSpecRow:
    body = next(s for s in json.loads(SEEDS.read_text()) if s["name"] == "fgsm")
    body = {k: v for k, v in body.items() if k not in ("id", "spec_sha256")}
    body["name"] = f"fgsm_{tag}_{'on' if active else 'off'}"
    sha = compute_spec_sha256(body)
    return m.AttackSpecRow(
        name=body["name"], version=1, kind=AttackKind.ATTACK, access=AttackAccess.WHITE_BOX,
        spec=body, spec_sha256=sha, is_active=active,
    )  # fmt: skip


@pytest.fixture(scope="module")
def world(app_engine: Engine, owner_engine: Engine) -> World:
    tag = uuid.uuid4().hex[:8]
    with Session(owner_engine) as s, s.begin():
        user = m.User(email=f"cat-{tag}@x.test", full_name="U", password_hash="x")
        s.add(user)
        s.flush()
        model = m.Model(name=f"yolo-{tag}", created_by=user.id)
        other = m.Model(name=f"rcnn-{tag}", created_by=user.id)
        dataset = m.Dataset(name=f"kitti-{tag}", created_by=user.id, anonymized=False)
        s.add_all([model, other, dataset])
        s.flush()
        mv = m.ModelVersion(
            model_id=model.id, weights_sha256=_sha(), weights_uri="s3://m", framework="ultralytics",
            class_names=["person", "car"], input_size=640, supports_gradients=True,
        )  # fmt: skip
        mv_other = m.ModelVersion(
            model_id=other.id, weights_sha256=_sha(), weights_uri="s3://m", framework="torchvision",
            class_names=["car"], input_size=640,
        )  # fmt: skip
        dv_old = m.DatasetVersion(
            dataset_id=dataset.id, manifest_sha256=_sha(), manifest_uri="s3://d", num_images=10,
            class_names=["Car"], created_at=T0 - timedelta(days=2),
        )  # fmt: skip
        dv_new = m.DatasetVersion(
            dataset_id=dataset.id, manifest_sha256=_sha(), manifest_uri="s3://d", num_images=12,
            class_names=["Car", "Van"], created_at=T0 - timedelta(days=1),
        )  # fmt: skip
        s.add_all([mv, mv_other, dv_old, dv_new])
        s.flush()
        filt = {"classes": ["Car", "Van"], "difficulty": None, "min_objects": 1}
        slices = [
            m.Slice(dataset_version_id=dv.id, name=name, filter=filt, seed=7,
                    image_ids=ids, image_ids_sha256=_sha(), slice_sha256=_sha())
            for dv, name, ids in (
                (dv_old, f"b-{tag}", ["1", "2", "3"]),
                (dv_old, f"a-{tag}", ["1"]),
                (dv_new, f"c-{tag}", ["1", "2"]),
            )
        ]  # fmt: skip
        mapping_body = {"preset": "kitti-coco", "classes": {"Car": "car", "Van": None}}
        mappings = [
            m.ClassMapping(dataset_version_id=dv.id, model_version_id=model_version.id,
                           mapping=mapping_body, mapping_sha256=_sha())
            for dv, model_version in ((dv_old, mv), (dv_new, mv), (dv_old, mv_other))
        ]  # fmt: skip
        specs = [_spec_row(tag, active=True), _spec_row(tag, active=False)]
        protocols = {
            status: m.Protocol(name=f"p-{tag}-{status}", version=1, body={}, body_sha256=_sha(),
                               status=status, created_by=user.id)
            for status in ProtocolStatus
        }  # fmt: skip
        targets = {
            name: m.ComputeTarget(
                name=f"{name}-{tag}", kind=ComputeKind.LOCAL, billing_mode=BillingMode.NONE,
                gpu_model="RTX 3050" if name != "never" else None,
                last_heartbeat_at=None if heartbeat is None else T0 - timedelta(seconds=heartbeat),
            )
            for name, heartbeat in (("fresh", 59), ("edge", 60), ("stale", 61), ("never", None))
        }  # fmt: skip
        s.add_all([*slices, *mappings, *specs, *protocols.values(), *targets.values()])
        s.flush()
        # Hai experiment queued và một running trên "fresh": queue_length = 2.
        for status in (ExperimentStatus.QUEUED, ExperimentStatus.QUEUED, ExperimentStatus.RUNNING):
            s.add(
                m.Experiment(
                    created_by=user.id, protocol_id=protocols[ProtocolStatus.DEV].id,
                    model_version_id=mv.id, slice_id=slices[0].id,
                    class_mapping_id=mappings[0].id, compute_target_id=targets["fresh"].id,
                    config={}, config_sha256=_sha(), status=status, limit_kind=LimitKind.TIME,
                    limit_value=7200,
                )
            )  # fmt: skip
        s.flush()
        return World(
            tag=tag, model_version=mv.id, other_model_version=mv_other.id, dataset=dataset.id,
            dv_old=dv_old.id, dv_new=dv_new.id, slices_old=(slices[1].id, slices[0].id),
            slice_new=slices[2].id, mapping_old=mappings[0].id, mapping_new=mappings[1].id,
            mapping_other_model=mappings[2].id, spec_active=specs[0].id,
            spec_inactive=specs[1].id, protocols={k: v.id for k, v in protocols.items()},
            targets={k: v.id for k, v in targets.items()},
        )  # fmt: skip


@pytest.fixture
def client(env: Env) -> TestClient:
    _, email = _user(env.engine, roles=(Role.ENGINEER,))
    client = env.client()
    assert _login(client, email).status_code == 200
    return client


def _get(client: TestClient, path: str, schema: Any, **params: Any) -> Any:
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    return TypeAdapter(schema).validate_python(response.json())


def test_models_list_and_get(client: TestClient, world: World) -> None:
    models = _get(client, "/models", list[ModelSummary])
    mine = [x for x in models if x.id in (world.model_version, world.other_model_version)]
    assert [x.name for x in mine] == [f"rcnn-{world.tag}", f"yolo-{world.tag}"]  # theo tên
    one = _get(client, f"/models/{world.model_version}", ModelSummary)
    assert (one.name, one.framework, one.supports_gradients) == (
        f"yolo-{world.tag}", "ultralytics", True,
    )  # fmt: skip
    assert one.class_names == ["person", "car"]


def test_datasets_include_versions_newest_first(client: TestClient, world: World) -> None:
    datasets = _get(client, "/datasets", list[DatasetSummary])
    (mine,) = [d for d in datasets if d.id == world.dataset]
    assert mine.anonymized is False
    assert [v.id for v in mine.versions] == [world.dv_new, world.dv_old]
    version = _get(client, f"/dataset-versions/{world.dv_new}", DatasetVersionSummary)
    assert (version.num_images, version.class_names) == (12, ["Car", "Van"])


def test_slices_filtered_by_dataset_version(client: TestClient, world: World) -> None:
    slices = _get(client, "/slices", list[SliceSummary], dataset_version=str(world.dv_old))
    assert [x.id for x in slices] == list(world.slices_old)  # theo tên: a-, b-
    assert {x.dataset_version_id for x in slices} == {world.dv_old}
    assert [x.size for x in slices] == [1, 3]
    assert slices[0].classes == ["Car", "Van"] and slices[0].seed == 7
    everything = {x.id for x in _get(client, "/slices", list[SliceSummary])}
    assert {*world.slices_old, world.slice_new} <= everything


def test_class_mappings_filtered_by_dataset_version_and_model(
    client: TestClient, world: World
) -> None:
    def ids(**params: str) -> set[uuid.UUID]:
        return {x.id for x in _get(client, "/class-mappings", list[ClassMappingSummary], **params)}

    assert ids(dataset_version=str(world.dv_old), model=str(world.model_version)) == {
        world.mapping_old
    }
    assert ids(dataset_version=str(world.dv_old)) == {world.mapping_old, world.mapping_other_model}
    assert {world.mapping_old, world.mapping_new} <= ids(model=str(world.model_version))
    (one,) = _get(
        client, "/class-mappings", list[ClassMappingSummary], dataset_version=str(world.dv_new)
    )
    assert (one.preset, one.classes) == ("kitti-coco", {"Car": "car", "Van": None})


def test_attack_specs_only_active(client: TestClient, world: World) -> None:
    ids = {x.id for x in _get(client, "/attack-specs", list[AttackSpec])}
    assert world.spec_active in ids
    assert world.spec_inactive not in ids


def test_protocols_exclude_retired(client: TestClient, world: World) -> None:
    ids = {x.id for x in _get(client, "/protocols", list[ProtocolSummary])}
    assert world.protocols[ProtocolStatus.ACTIVE] in ids
    assert world.protocols[ProtocolStatus.DEV] in ids
    assert world.protocols[ProtocolStatus.RETIRED] not in ids
    assert "2edcdef5-0d3a-5d5f-98ac-b02637fa6718" in {str(i) for i in ids}  # dev-open


def test_compute_targets_online_window_and_queue_length(
    env: Env, client: TestClient, world: World
) -> None:
    env.clock.now = T0
    targets = {x.id: x for x in _get(client, "/compute-targets", list[ComputeTargetPublic])}
    mine = {name: targets[target_id] for name, target_id in world.targets.items()}
    # Heartbeat trong 60 giây gần nhất (gồm đúng 60 giây) là online.
    assert {name: t.online for name, t in mine.items()} == {
        "fresh": True, "edge": True, "stale": False, "never": False,
    }  # fmt: skip
    assert mine["fresh"].queue_length == 2  # experiment running không tính
    assert mine["stale"].queue_length == 0
    assert (mine["fresh"].default_time_limit_s, mine["fresh"].max_time_limit_s) == (7200, 28800)
    assert mine["never"].gpu_model is None

    env.clock.advance(2)
    later = {x.id: x for x in _get(client, "/compute-targets", list[ComputeTargetPublic])}
    assert later[world.targets["fresh"]].online is False


@pytest.mark.parametrize("path", ["/models/{id}", "/dataset-versions/{id}"])
def test_unknown_id_is_404(client: TestClient, path: str) -> None:
    response = client.get(path.format(id=uuid.uuid4()))
    assert response.status_code == 404
    assert ErrorResponse.model_validate(response.json()).error.code == "not_found"


def test_reviewer_without_compute_target_read_is_forbidden(env: Env, world: World) -> None:
    _, email = _user(env.engine, roles=(Role.REVIEWER,))
    client = env.client()
    _login(client, email)
    assert client.get("/models").status_code == 200
    assert client.get("/compute-targets").status_code == 403
