"""validation.md Phase 5, Đọc tài nguyên (`test_catalog_read.py`) và lọc, phân trang danh sách."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import Engine, update
from sqlalchemy.orm import Session

from advertest_contracts.enums import AttackAccess, AttackKind, ProtocolStatus
from advertest_contracts.models import compute_spec_sha256
from backend.app.db import models as m

from .conftest import DEV_OPEN, REPO, Api, attack, ok, post

pytestmark = pytest.mark.db


def test_attack_specs_only_active(api: Api, app_engine: Engine) -> None:
    base = next(
        s for s in json.loads((REPO / "contracts" / "seeds" / "attack_specs.json").read_text())
        if s["name"] == "fgsm"
    )  # fmt: skip
    body = {k: v for k, v in base.items() if k not in ("id", "spec_sha256")}
    body["name"] = f"fgsm_off_{uuid.uuid4().hex[:6]}"
    with Session(app_engine) as session, session.begin():
        row = m.AttackSpecRow(
            name=body["name"], version=1, kind=AttackKind.ATTACK, access=AttackAccess.WHITE_BOX,
            spec=body, spec_sha256=compute_spec_sha256(body), is_active=False,
        )  # fmt: skip
        session.add(row)
    _, _, client = api.user("engineer")
    names = {s["name"] for s in client.get("/attack-specs").json()}
    assert {"fgsm", "pgd_linf", "pgd_l2"} <= names and body["name"] not in names


def test_protocols_exclude_retired(api: Api, app_engine: Engine) -> None:
    with Session(app_engine) as session, session.begin():
        admin_id = session.query(m.User).filter_by(email="admin-phase05@example.com").one().id
        retired = m.Protocol(name=f"cu-{uuid.uuid4().hex[:6]}", version=1, body={},
                             body_sha256="b" * 64, status=ProtocolStatus.RETIRED,
                             created_by=admin_id)  # fmt: skip
        session.add(retired)
        session.flush()
        retired_id = str(retired.id)
    _, _, client = api.user("reviewer")
    ids = {p["id"] for p in client.get("/protocols").json()}
    assert DEV_OPEN in ids and retired_id not in ids


def test_class_mappings_filtered(api: Api) -> None:
    _, _, client = api.user("engineer")
    slices = client.get("/slices").json()
    version = next(s["dataset_version_id"] for s in slices if s["id"] == api.world.slice_id)
    both = client.get(
        f"/class-mappings?dataset_version={version}&model={api.world.model_id}"
    ).json()
    assert [mp["id"] for mp in both] == [api.world.mapping_id]
    by_version = {
        mp["id"] for mp in client.get(f"/class-mappings?dataset_version={version}").json()
    }
    assert {api.world.mapping_id, api.world.random_mapping_id} <= by_version


def test_online_by_heartbeat_and_queue_length(api: Api, app_engine: Engine) -> None:
    fresh, stale = api.target(), api.target()
    with Session(app_engine) as session, session.begin():
        for target, seconds in ((fresh, 59), (stale, 61)):
            session.execute(
                update(m.ComputeTarget)
                .where(m.ComputeTarget.id == UUID(target.id))
                .values(last_heartbeat_at=api.clock.now - timedelta(seconds=seconds))
            )
    _, _, client = api.user("engineer")
    for _ in range(2):
        ok(post(client, "/experiments", api.body(fresh, [attack("fgsm", [4])])))
    targets = {t["id"]: t for t in client.get("/compute-targets").json()}
    assert (targets[fresh.id]["online"], targets[stale.id]["online"]) == (True, False)
    assert (targets[fresh.id]["queue_length"], targets[stale.id]["queue_length"]) == (2, 0)


def test_experiment_list_filters_and_cursor(api: Api) -> None:
    target = api.target()
    me, _, client = api.user("engineer")
    mine = []
    for _ in range(3):
        mine.append(
            ok(post(client, "/experiments", api.body(target, [attack("fgsm", [4])]))).json()["id"]
        )
        api.clock.advance(1)
    _, _, other = api.user("engineer")
    theirs = ok(post(other, "/experiments", api.body(target, [attack("fgsm", [4])]))).json()["id"]

    first = client.get("/experiments", params={"owner": "me", "limit": 2}).json()
    assert [e["id"] for e in first["items"]] == [mine[2], mine[1]]
    rest = client.get(
        "/experiments", params={"owner": "me", "limit": 2, "cursor": first["next_cursor"]}
    ).json()
    assert [e["id"] for e in rest["items"]] == [mine[0]] and rest["next_cursor"] is None
    assert all(e["owner"]["id"] == str(me) for e in first["items"] + rest["items"])

    everyone = client.get(
        "/experiments",
        params={"owner": "all", "status": "queued", "model": api.world.model_id, "limit": 100},
    ).json()
    ids = {e["id"] for e in everyone["items"]}
    assert set(mine) | {theirs} <= ids
    assert (
        client.get("/experiments", params={"owner": "me", "status": "completed"}).json()["items"]
        == []
    )
