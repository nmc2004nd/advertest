"""validation.md Phase R2, Group 1 — Nâng lên chính thức (`test_promote.py`, marker `db`).

- `promote` trả bản nháp đủ attack bắt buộc, hợp của level bắt buộc và level nguồn, giữ attack
  nguồn mà protocol không yêu cầu; không tạo experiment.
- Slice nhỏ hơn `min_slice_size` không chặn bản nháp, chỉ ghi `notes` (`slice_too_small`); tạo
  experiment từ bản nháp đó bị compliance chặn (422 `not_compliant`, kiểm lúc tạo từ Phase 8).
- Nguồn `official` hoặc chưa kết thúc → 409; protocol đích không `active` → 409.
- Tạo từ bản nháp: experiment mới có `promoted_from` (audit log `experiment.promoted`), không kế
  thừa run nào của nguồn.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from advertest_contracts.models import ExperimentClone
from backend.app.db import models as m

from .conftest import (
    DEV_OPEN,
    P5,
    audit_entries,
    count_rows,
    create_protocol,
    error,
    max_drop,
    ok,
    post,
    required_grid,
    spec_of,
)

pytestmark = pytest.mark.db


@pytest.fixture
def setup(api: Any) -> dict[str, Any]:
    _, _, owner = api.user("engineer")
    _, _, reviewer = api.user("reviewer")
    target = api.target()
    api.profile(target, sec=0.05, batch=5, attacks=["fgsm", "fog"])
    required = {
        "required_attacks": [required_grid("fgsm", [2.0, 4.0])],
        "pass_criteria": [max_drop("fgsm", 4.0)],
    }
    protocol = create_protocol(reviewer, min_slice_size=5, **required)
    large = create_protocol(reviewer, min_slice_size=10, **required)  # slice fixture có 5 ảnh
    return {
        "owner": owner,
        "reviewer": reviewer,
        "target": target,
        "protocol": protocol,
        "large": large,
    }


def _experiment(api: Any, s: dict[str, Any], attacks: dict[str, list[float]], **kw: Any) -> str:
    body = api.body(s["target"], [P5.attack(n, lv) for n, lv in attacks.items()], **kw)
    experiment_id: str = ok(post(s["owner"], "/experiments", body)).json()["id"]
    return experiment_id


def _promote(client: TestClient, experiment_id: str, protocol_id: str) -> Any:
    return post(client, f"/experiments/{experiment_id}/promote", {"protocol_id": protocol_id})


def test_promote_returns_draft_without_creating(api: Any, setup: dict[str, Any]) -> None:
    source = _experiment(api, setup, {"fgsm": [2.0, 8.0], "fog": [1.0]})
    api.work(setup["target"], source)
    before = count_rows(api.engine, m.Experiment)

    response = _promote(setup["owner"], source, setup["protocol"]["id"])
    assert response.status_code == 200, response.text
    clone = ExperimentClone.model_validate(response.json())
    assert count_rows(api.engine, m.Experiment) == before

    config = clone.config
    w = api.world
    assert str(config.protocol_id) == setup["protocol"]["id"]
    assert (str(config.model_version_id), str(config.slice_id), str(config.class_mapping_id)) == (
        w.model_id, w.slice_id, w.mapping_id,
    )  # fmt: skip
    assert str(config.compute_target_id) == setup["target"].id
    assert str(config.promoted_from) == source
    attacks = {str(a.attack_spec_id): a for a in config.attacks}
    fgsm, fog = spec_of("fgsm"), spec_of("fog")
    assert set(attacks) == {str(fgsm.id), str(fog.id)}  # fog không bắt buộc vẫn được giữ
    grid = attacks[str(fgsm.id)].grid
    assert grid is not None and sorted(grid.levels) == [2.0, 4.0, 8.0]
    assert attacks[str(fgsm.id)].spec_sha256 == fgsm.spec_sha256
    assert clone.notes == []

    created = ok(post(setup["owner"], "/experiments", clone.config.model_dump(mode="json")))
    new_id = created.json()["id"]
    assert new_id != source
    runs = setup["owner"].get(f"/experiments/{new_id}/runs").json()
    assert runs and all(r["status"] == "queued" for r in runs)
    assert {r["run_id"] for r in runs}.isdisjoint(
        {r["run_id"] for r in setup["owner"].get(f"/experiments/{source}/runs").json()}
    )
    entries = audit_entries(api.engine, "experiment.promoted", new_id)
    assert len(entries) == 1
    assert (entries[0].after or {}).get("promoted_from") == source
    assert setup["owner"].get(f"/experiments/{new_id}").json()["mode"] == "official"


def test_promote_rejects_official_or_unfinished_source(api: Any, setup: dict[str, Any]) -> None:
    unfinished = _experiment(api, setup, {"fgsm": [2.0]})
    status, code, _ = error(_promote(setup["owner"], unfinished, setup["protocol"]["id"]))
    assert (status, code) == (409, "conflict")

    official = _experiment(api, setup, {"fgsm": [2.0, 4.0]}, protocol_id=setup["protocol"]["id"])
    api.work(setup["target"], unfinished)
    api.work(setup["target"], official)
    status, code, _ = error(_promote(setup["owner"], official, setup["protocol"]["id"]))
    assert (status, code) == (409, "conflict")


def test_promote_rejects_inactive_target_protocol(api: Any, setup: dict[str, Any]) -> None:
    source = _experiment(api, setup, {"fgsm": [2.0]})
    api.work(setup["target"], source)
    assert error(_promote(setup["owner"], source, DEV_OPEN))[:2] == (409, "conflict")
    retired = create_protocol(setup["reviewer"])
    ok(post(setup["reviewer"], f"/protocols/{retired['id']}/retire"))
    assert error(_promote(setup["owner"], source, retired["id"]))[:2] == (409, "conflict")


def test_small_slice_is_a_note_not_a_block(api: Any, setup: dict[str, Any]) -> None:
    source = _experiment(api, setup, {"fgsm": [2.0]})
    api.work(setup["target"], source)
    response = _promote(setup["owner"], source, setup["large"]["id"])
    assert response.status_code == 200, response.text
    clone = ExperimentClone.model_validate(response.json())
    assert [n.code for n in clone.notes] == ["slice_too_small"]
    status, code, _ = error(
        post(setup["owner"], "/experiments", clone.config.model_dump(mode="json"))
    )
    assert (status, code) == (422, "not_compliant")
