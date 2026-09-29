"""Lease (validation.md Phase 3, test_leasing.py)."""

from __future__ import annotations

import pytest

from advertest_contracts.models import (
    ProgressReport,
)

from .conftest import REPO, Harness, start_request

pytestmark = pytest.mark.db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_first_come_first_served_and_not_released_while_held(harness: Harness) -> None:
    name, token = harness.target()
    first = harness.submit(name, harness.world.config({"fgsm": [4]}))
    harness.clock.advance(1)
    second = harness.submit(name, harness.world.config({"fgsm": [8]}))
    client = harness.client(token)
    lease = client.lease()
    assert lease is not None and lease.experiment_id == first
    experiment, _ = harness.state(first)
    assert experiment.status == "running"
    again = client.lease()
    assert again is not None and again.experiment_id == second  # không trả lại experiment đang giữ
    assert client.lease() is None


def test_expired_lease_goes_to_another_worker_and_old_worker_gets_409(harness: Harness) -> None:
    import json

    name, token = harness.target()
    experiment_id = harness.submit(name, harness.world.config({"fgsm": [4]}))
    old_worker, new_worker = harness.client(token), harness.client(token)
    old = old_worker.lease()
    assert old is not None
    _, runs = harness.state(experiment_id)
    run_id = runs[0].id
    assert old_worker.start(run_id, start_request(old.lease_id)).action == "run"
    report = ProgressReport(
        lease_id=old.lease_id, images_done=1, batch_index=0,
        checkpoint_key=f"runs/{run_id}/checkpoints/0.json", processing_seconds_delta=1.0,
    )  # fmt: skip
    old_worker.progress(run_id, report)

    harness.clock.advance(59)
    assert new_worker.lease() is None
    harness.clock.advance(2)  # 61 giây không heartbeat
    new = new_worker.lease()
    assert new is not None and new.experiment_id == experiment_id and new.lease_id != old.lease_id

    auth = _auth(token)
    stale = {"lease_id": str(old.lease_id), "experiment_id": str(experiment_id)}
    assert (
        harness.api.post("/internal/worker/heartbeat", json=stale, headers=auth).status_code == 409
    )
    later = report.model_copy(update={"images_done": 2}).model_dump(mode="json")
    response = harness.api.post(
        f"/internal/worker/runs/{run_id}/progress", json=later, headers=auth
    )
    assert response.status_code == 409
    completion = json.loads((REPO / "contracts/mocks/run_completion/failed.json").read_text())
    completion["lease_id"] = str(old.lease_id)
    response = harness.api.post(
        f"/internal/worker/runs/{run_id}/complete", json=completion, headers=auth
    )
    assert response.status_code == 409
    _, runs = harness.state(experiment_id)
    assert runs[0].status == "running" and runs[0].images_done == 1


def test_experiment_of_other_target_never_leased(harness: Harness) -> None:
    name_a, _ = harness.target()
    _, token_b = harness.target()
    harness.submit(name_a, harness.world.config({"fgsm": [4]}))
    client_b = harness.client(token_b)
    assert client_b.lease() is None
    harness.clock.advance(120)
    assert client_b.lease() is None
