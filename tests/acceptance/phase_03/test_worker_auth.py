"""Xác thực worker (validation.md Phase 3, test_worker_auth.py)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest
from sqlalchemy.orm import Session

from backend.app.db import models as m

from .conftest import ADMIN, REPO, Harness, admin

pytestmark = pytest.mark.db
MOCKS = REPO / "contracts" / "mocks"
SAMPLE = "00000000-0000-5000-8000-000000000001"
ARTIFACT_URL = "artifact_url_request/put_candidate.json"
ENDPOINTS: list[tuple[str, str, str | None]] = [
    ("post", "/internal/worker/lease", None),
    ("get", f"/internal/worker/experiments/{SAMPLE}/bundle", None),
    ("post", "/internal/worker/heartbeat", "heartbeat_request/default.json"),
    ("post", f"/internal/worker/runs/{SAMPLE}/start", "run_start_request/gpu_local.json"),
    ("post", f"/internal/worker/runs/{SAMPLE}/progress", "progress_report/after_batch_0.json"),
    (
        "post",
        f"/internal/worker/runs/{SAMPLE}/artifact-url",
        "artifact_url_request/put_candidate.json",
    ),
    ("post", f"/internal/worker/runs/{SAMPLE}/complete", "run_completion/failed.json"),
    ("post", "/internal/worker/cost-profiles", "cost_profile/gpu_local_pgd.json"),
]


def _mock(path: str | None) -> Any:
    return json.loads((MOCKS / path).read_text()) if path else None


@pytest.mark.parametrize(("method", "path", "body"), ENDPOINTS)
def test_missing_or_wrong_token_is_401(
    harness: Harness, method: str, path: str, body: str | None
) -> None:
    for headers in ({}, {"Authorization": "Bearer sai-token"}):
        response = harness.api.request(method, path, json=_mock(body), headers=headers)
        assert response.status_code == 401, (path, response.text)
        assert response.json()["error"]["code"] == "unauthenticated"


def test_rotated_token(harness: Harness) -> None:
    name, old = harness.target()
    rotated = admin(harness.cli_env, "compute-target", "rotate-token", name, "--as", ADMIN)
    new = rotated.output.strip().splitlines()[-1]
    lease = "/internal/worker/lease"
    assert harness.api.post(lease, headers={"Authorization": f"Bearer {old}"}).status_code == 401
    assert harness.api.post(lease, headers={"Authorization": f"Bearer {new}"}).status_code == 204


def test_token_of_other_target_is_403(harness: Harness) -> None:
    name_b, token_b = harness.target()
    _, token_a = harness.target()
    experiment_id = harness.submit(name_b, harness.world.config({"fgsm": [4]}))
    client_b = harness.client(token_b)
    lease = client_b.lease()
    assert lease is not None
    _, runs = harness.state(experiment_id)
    run_id = runs[0].id
    auth_a = {"Authorization": f"Bearer {token_a}"}

    bundle = harness.api.get(f"/internal/worker/experiments/{experiment_id}/bundle", headers=auth_a)
    assert bundle.status_code == 403
    progress = _mock("progress_report/after_batch_0.json")
    progress.update(
        lease_id=str(lease.lease_id), checkpoint_key=f"runs/{run_id}/checkpoints/0.json"
    )
    response = harness.api.post(
        f"/internal/worker/runs/{run_id}/progress", json=progress, headers=auth_a
    )
    assert response.status_code == 403
    completion = _mock("run_completion/failed.json")
    completion["lease_id"] = str(lease.lease_id)
    response = harness.api.post(
        f"/internal/worker/runs/{run_id}/complete", json=completion, headers=auth_a
    )
    assert response.status_code == 403
    _, runs = harness.state(experiment_id)
    assert runs[0].status == "queued" and runs[0].images_done == 0


def test_db_stores_only_token_sha256(harness: Harness) -> None:
    name, token = harness.target()
    with Session(harness.app_engine) as session:
        stored = session.query(m.ComputeTarget).filter_by(name=name).one().token_hash
    assert stored == hashlib.sha256(token.encode()).hexdigest() and token not in stored
