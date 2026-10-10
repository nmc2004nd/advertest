"""validation.md Phase R3, Group 1 — `ExperimentDetail.promoted_from` (marker `db`): có với
experiment tạo qua "Nâng lên chính thức", không có ở experiment khác (trường bị bỏ khỏi JSON khi
null, như các trường `exclude_if` khác)."""

from __future__ import annotations

from typing import Any

import pytest

from advertest_contracts.models import ExperimentClone, ExperimentDetail

from .conftest import P5, create_protocol, max_drop, ok, post, required_grid

pytestmark = pytest.mark.db


def test_promoted_from_in_detail(api: Any) -> None:
    _, _, owner = api.user("engineer")
    _, _, reviewer = api.user("reviewer")
    target = api.target()
    api.profile(target, sec=0.05, batch=5, attacks=["fgsm"])
    protocol = create_protocol(
        reviewer,
        required_attacks=[required_grid("fgsm", [2.0, 4.0])],
        pass_criteria=[max_drop("fgsm", 4.0)],
    )

    source = ok(post(owner, "/experiments", api.body(target, [P5.attack("fgsm", [2.0])]))).json()
    api.work(target, source["id"])
    source_detail = owner.get(f"/experiments/{source['id']}").json()
    assert "promoted_from" not in source_detail

    draft = ok(post(owner, f"/experiments/{source['id']}/promote", {"protocol_id": protocol["id"]}))
    clone = ExperimentClone.model_validate(draft.json())
    created = ok(post(owner, "/experiments", clone.config.model_dump(mode="json"))).json()

    view = ExperimentDetail.model_validate(owner.get(f"/experiments/{created['id']}").json())
    assert view.mode == "official"
    assert str(view.promoted_from) == source["id"]
