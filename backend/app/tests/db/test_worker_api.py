"""API nội bộ worker qua HTTP (validation.md Phase 3: xác thực worker, lease, artifact).

Postgres và MinIO thật (`make test-db`); presigned URL được dùng thật bằng httpx.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from advertest_contracts.enums import RunStatus
from advertest_contracts.models import (
    ArtifactUrlResponse,
    ErrorResponse,
    RunStartResponse,
    WorkerDirective,
    WorkerJobBundle,
    WorkerLease,
)
from backend.app.api.deps import Storage, get_clock, get_sessionmaker, get_storage
from backend.app.db import models as m
from backend.app.main import create_app
from backend.app.presign import Presigner
from backend.app.services import compute_targets, experiments
from backend.app.storage import Buckets

from .conftest import _url
from .test_worker_services import (
    FakeClock,
    World,
    _completion,
    _config,
    _start_request,
    world,  # fixture dùng chung
)

pytestmark = pytest.mark.db
__all__ = ["world"]


def _presigner(expires_s: int = 900) -> Presigner:
    return Presigner.for_endpoint(
        _url("ADVERTEST_TEST_MINIO_ENDPOINT"),
        _url("ADVERTEST_TEST_MINIO_ACCESS_KEY"),
        _url("ADVERTEST_TEST_MINIO_SECRET_KEY"),
        expires_s,
    )


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def client(app_engine: Engine, buckets: Buckets, clock: FakeClock) -> Iterator[TestClient]:
    app = create_app()
    factory = sessionmaker(app_engine)
    app.dependency_overrides[get_sessionmaker] = lambda: factory
    app.dependency_overrides[get_storage] = lambda: Storage(buckets, _presigner())
    app.dependency_overrides[get_clock] = lambda: clock
    with TestClient(app) as test_client:
        yield test_client


def _setup(app_engine: Engine, world: World, clock: FakeClock) -> tuple[str, UUID, UUID]:
    """Target mới (trả token) và một experiment `queued` của target đó."""
    with Session(app_engine) as session, session.begin():
        admin = session.get_one(m.User, world.admin_id)
        issued = compute_targets.create(session, actor=admin, name=f"t-{uuid.uuid4().hex[:8]}")
        experiment = experiments.submit(
            session, actor=admin, config=_config(world), target=issued.target, clock=clock
        )
        return issued.token, issued.target.id, experiment.id


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _error(response: httpx.Response) -> str:
    return ErrorResponse.model_validate(response.json()).error.code


def _lease(client: TestClient, token: str) -> WorkerLease:
    response = client.post("/internal/worker/lease", headers=_auth(token))
    assert response.status_code == 200, response.text
    return WorkerLease.model_validate(response.json())


def _runs(app_engine: Engine, experiment_id: UUID) -> list[m.Run]:
    with Session(app_engine) as session:
        return experiments.runs_of(session, experiment_id)


def test_token_auth_and_rotation(
    client: TestClient, app_engine: Engine, world: World, clock: FakeClock
) -> None:
    with Session(app_engine) as session, session.begin():
        admin = session.get_one(m.User, world.admin_id)
        name = f"t-{uuid.uuid4().hex[:8]}"
        old = compute_targets.create(session, actor=admin, name=name).token
    assert client.post("/internal/worker/lease", headers=_auth(old)).status_code == 204
    wrong = client.post("/internal/worker/lease", headers=_auth("sai"))
    assert wrong.status_code == 401 and _error(wrong) == "unauthenticated"
    with Session(app_engine) as session, session.begin():
        admin = session.get_one(m.User, world.admin_id)
        new = compute_targets.rotate_token(session, actor=admin, name=name).token
    assert client.post("/internal/worker/lease", headers=_auth(old)).status_code == 401
    assert client.post("/internal/worker/lease", headers=_auth(new)).status_code == 204


def test_bundle_with_working_presigned_downloads(
    client: TestClient, app_engine: Engine, world: World, clock: FakeClock
) -> None:
    token, _, experiment_id = _setup(app_engine, world, clock)
    lease = _lease(client, token)
    assert lease.experiment_id == experiment_id
    response = client.get(
        f"/internal/worker/experiments/{experiment_id}/bundle", headers=_auth(token)
    )
    assert response.status_code == 200, response.text
    bundle = WorkerJobBundle.model_validate(response.json())
    assert [r.status for r in bundle.runs] == [RunStatus.QUEUED] * 3
    assert bundle.model_card.id == world.local.card.id
    assert bundle.slice.id == world.local.slice.id
    assert set(bundle.downloads.images) == set(world.local.slice.image_ids)
    assert bundle.limit.used == 0 and bundle.cost_profiles == []
    by_id = {img.image_id: img.sha256 for img in world.local.manifest.images}
    for image_id, url in bundle.downloads.images.items():
        data = httpx.get(url).raise_for_status().content
        assert hashlib.sha256(data).hexdigest() == by_id[image_id]
    weights = httpx.get(bundle.downloads.weights).raise_for_status().content
    assert hashlib.sha256(weights).hexdigest() == world.local.card.weights_sha256

    other_token, _, _ = _setup(app_engine, world, clock)
    forbidden = client.get(
        f"/internal/worker/experiments/{experiment_id}/bundle", headers=_auth(other_token)
    )
    assert forbidden.status_code == 403 and _error(forbidden) == "forbidden"
    missing = client.get(
        f"/internal/worker/experiments/{uuid.uuid4()}/bundle", headers=_auth(token)
    )
    assert missing.status_code == 404 and _error(missing) == "not_found"


def test_run_flow_over_http(
    client: TestClient, app_engine: Engine, world: World, clock: FakeClock, buckets: Buckets
) -> None:
    token, _, experiment_id = _setup(app_engine, world, clock)
    lease = _lease(client, token)
    run = _runs(app_engine, experiment_id)[0]
    base = f"/internal/worker/runs/{run.id}"

    start = _start_request(lease.lease_id)
    response = client.post(
        f"{base}/start", json=start.model_dump(mode="json"), headers=_auth(token)
    )
    assert response.status_code == 200
    assert RunStartResponse.model_validate(response.json()).action == "run"

    def url(key: str, method: str = "PUT") -> httpx.Response:
        body = {"lease_id": str(lease.lease_id), "key": key, "method": method}
        response: httpx.Response = client.post(
            f"{base}/artifact-url", json=body, headers=_auth(token)
        )
        return response

    key = f"runs/{run.id}/checkpoints/0.json"
    granted = url(key)
    assert granted.status_code == 200
    signed = ArtifactUrlResponse.model_validate(granted.json())
    httpx.put(signed.url, content=b'{"done": 1}').raise_for_status()
    assert buckets.artifacts.get(key) == b'{"done": 1}'
    outside = url(f"runs/{uuid.uuid4()}/x.json")
    assert outside.status_code == 403 and _error(outside) == "forbidden"
    assert url(f"runs/{run.id}/../x.json").status_code == 422  # contract: ObjectKey

    report = {
        "lease_id": str(lease.lease_id),
        "images_done": 1,
        "batch_index": 0,
        "checkpoint_key": key,
        "processing_seconds_delta": 2.0,
    }
    response = client.post(f"{base}/progress", json=report, headers=_auth(token))
    assert WorkerDirective.model_validate(response.json()).action == "continue"
    heartbeat = client.post(
        "/internal/worker/heartbeat",
        json={"lease_id": str(lease.lease_id), "experiment_id": str(experiment_id)},
        headers=_auth(token),
    )
    assert heartbeat.status_code == 200
    bundle = WorkerJobBundle.model_validate(
        client.get(
            f"/internal/worker/experiments/{experiment_id}/bundle", headers=_auth(token)
        ).json()
    )
    checkpoint = bundle.runs[0].checkpoint
    assert checkpoint is not None and checkpoint.key == key
    assert httpx.get(checkpoint.url).raise_for_status().content == b'{"done": 1}'

    with Session(app_engine) as session:
        current = session.get_one(m.Run, run.id)
    # Artifact chưa có trong MinIO → 422; đặt artifact lên rồi gửi lại → 204.
    missing_artifacts = _completion(current, lease.lease_id, None)
    invalid = client.post(
        f"{base}/complete", json=missing_artifacts.model_dump(mode="json"), headers=_auth(token)
    )
    assert invalid.status_code == 422 and _error(invalid) == "invalid_request"
    completion = _completion(current, lease.lease_id, buckets)
    done = client.post(
        f"{base}/complete", json=completion.model_dump(mode="json"), headers=_auth(token)
    )
    assert done.status_code == 204, done.text
    after = url(f"runs/{run.id}/late.json")  # run đã completed: không cấp URL
    assert after.status_code == 409 and _error(after) == "conflict"


def test_stale_lease_rejected_over_http(
    client: TestClient, app_engine: Engine, world: World, clock: FakeClock
) -> None:
    token, _, experiment_id = _setup(app_engine, world, clock)
    old = _lease(client, token)
    clock.advance(61)
    new = _lease(client, token)
    assert new.experiment_id == experiment_id and new.lease_id != old.lease_id
    stale = client.post(
        "/internal/worker/heartbeat",
        json={"lease_id": str(old.lease_id), "experiment_id": str(experiment_id)},
        headers=_auth(token),
    )
    assert stale.status_code == 409 and _error(stale) == "conflict"


def test_cost_profile_endpoint(
    client: TestClient, app_engine: Engine, world: World, clock: FakeClock
) -> None:
    token, target_id, experiment_id = _setup(app_engine, world, clock)
    _lease(client, token)
    fgsm = next(iter(_config(world).attacks)).attack_spec_id
    profile: dict[str, Any] = {
        "compute_target_id": str(target_id),
        "model_version_id": str(world.local.card.id),
        "attack_spec_id": str(fgsm),
        "sec_per_image": 0.2,
        "peak_vram_mb": 0,
        "batch_size": 2,
        "measured_at": clock.now.isoformat(),
        "environment": {
            "compute_target_id": str(target_id),
            "gpu_model": None,
            "cuda_version": None,
            "driver_version": None,
        },
    }
    response = client.post("/internal/worker/cost-profiles", json=profile, headers=_auth(token))
    assert response.status_code == 204, response.text
    bundle = WorkerJobBundle.model_validate(
        client.get(
            f"/internal/worker/experiments/{experiment_id}/bundle", headers=_auth(token)
        ).json()
    )
    assert [p.attack_spec_id for p in bundle.cost_profiles] == [fgsm]
    other = {**profile, "compute_target_id": str(uuid.uuid4())}
    other["environment"] = {
        **profile["environment"],
        "compute_target_id": other["compute_target_id"],
    }
    forbidden = client.post("/internal/worker/cost-profiles", json=other, headers=_auth(token))
    assert forbidden.status_code == 403


def test_expired_presigned_url_is_rejected(buckets: Buckets) -> None:
    buckets.artifacts.put("runs/expiry-test/a.txt", b"x")
    signer = _presigner(expires_s=1)
    signed = signer.url("artifacts", "runs/expiry-test/a.txt", "GET", FakeClock().now)
    assert httpx.get(signed.url).status_code == 200
    time.sleep(2)
    assert httpx.get(signed.url).status_code == 403


def test_changed_fingerprint_on_resume_commits_failed_then_409(
    client: TestClient, app_engine: Engine, world: World, clock: FakeClock
) -> None:
    token, _, experiment_id = _setup(app_engine, world, clock)
    lease = _lease(client, token)
    run = _runs(app_engine, experiment_id)[0]
    path = f"/internal/worker/runs/{run.id}/start"
    first = _start_request(lease.lease_id).model_dump(mode="json")
    assert client.post(path, json=first, headers=_auth(token)).status_code == 200
    other = _start_request(lease.lease_id).model_dump(mode="json")
    response = client.post(path, json=other, headers=_auth(token))
    assert response.status_code == 409 and _error(response) == "conflict"
    # Trạng thái failed đã được commit dù API trả 409.
    assert _runs(app_engine, experiment_id)[0].status == RunStatus.FAILED
