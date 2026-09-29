"""Artifact trong MinIO (validation.md Phase 3, test_artifacts.py)."""

from __future__ import annotations

import io
import json
import time
from datetime import UTC, datetime
from itertools import count
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import httpx
import pytest
from PIL import Image

from advertest_contracts.models import compute_failure_case_id
from backend.app.storage import Buckets
from ml_core.runner import executor as executor_module

from .conftest import REPO, Harness, presigner, start_request

pytestmark = pytest.mark.db
MOCKS = REPO / "contracts" / "mocks"


def _mock(path: str) -> Any:
    return json.loads((MOCKS / path).read_text())


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _started(harness: Harness, attacks: dict[str, list[float]]) -> tuple[str, UUID, list[Any], str]:
    """Experiment đã lease, run đầu đã start (qua API). Trả (token, lease_id, runs, fingerprint)."""
    name, token = harness.target()
    experiment_id = harness.submit(name, harness.world.config(attacks))
    client = harness.client(token)
    lease = client.lease()
    assert lease is not None
    _, runs = harness.state(experiment_id)
    request = start_request(lease.lease_id)
    assert client.start(runs[0].id, request).action == "run"
    return token, lease.lease_id, runs, request.fingerprint


def _url(harness: Harness, token: str, run_id: UUID, lease_id: UUID, key: str) -> httpx.Response:
    body = {"lease_id": str(lease_id), "key": key, "method": "PUT"}
    response: httpx.Response = harness.api.post(
        f"/internal/worker/runs/{run_id}/artifact-url", json=body, headers=_auth(token)
    )
    return response


def _completion(
    run: Any, lease_id: UUID, fingerprint: str, keys: dict[str, str] | None, status: str
) -> dict[str, Any]:
    result = _mock(
        "run_result/completed.json" if status == "completed" else "run_result/failed.json"
    )
    result.update(
        run_id=str(run.id), experiment_id=str(run.experiment_id), fingerprint=fingerprint,
        attack_spec_id=str(run.attack_spec_id), level=run.level, cost=None,
        progress={"images_done": run.images_total if status == "completed" else 0,
                  "images_total": run.images_total},
        manifest_uri=None, failure_case_ids=[],
    )  # fmt: skip
    cases = []
    if keys is not None:
        template = _mock("failure_case_record/worker_minio.json")
        case_id = compute_failure_case_id(fingerprint, run.id, template["image_id"])
        cases.append(
            {**template, "id": str(case_id), "run_id": str(run.id), "fingerprint": fingerprint,
             "artifacts": keys}
        )  # fmt: skip
        result["failure_case_ids"] = [str(case_id)]
    return {"lease_id": str(lease_id), "run_result": result, "failure_cases": cases}


def _case_keys(run_id: UUID, prefix: str | None = None) -> dict[str, str]:
    base = prefix or f"runs/{run_id}/cases/c1"
    return {
        "clean_png": f"{base}/clean.png",
        "adversarial_png": f"{base}/adversarial.png",
        "perturbation_png": f"{base}/perturbation.png",
        "clean_thumb": f"{base}/clean_thumb.webp",
        "adversarial_thumb": f"{base}/adversarial_thumb.webp",
    }


def test_url_outside_run_directory_rejected(harness: Harness) -> None:
    token, lease_id, runs, _ = _started(harness, {"fgsm": [4]})
    run_id = runs[0].id
    assert (
        _url(harness, token, run_id, lease_id, f"runs/{run_id}/checkpoints/0.json").status_code
        == 200
    )
    other = _url(harness, token, run_id, lease_id, f"runs/{runs[0].experiment_id}/x.json")
    assert other.status_code == 403
    assert _url(harness, token, run_id, lease_id, "datasets/x.png").status_code == 403


def test_expired_presigned_url_unusable(buckets: Buckets) -> None:
    buckets.artifacts.put("runs/expiry-phase03/a.txt", b"x")
    now = datetime.now(UTC)
    signed = presigner(expires_s=1).url("artifacts", "runs/expiry-phase03/a.txt", "GET", now)
    assert httpx.get(signed.url).status_code == 200
    time.sleep(2)
    assert httpx.get(signed.url).status_code == 403


def test_no_url_for_run_not_running(harness: Harness) -> None:
    token, lease_id, runs, fingerprint = _started(harness, {"fgsm": [4, 8]})
    first = runs[0]
    body = _completion(first, lease_id, fingerprint, None, "failed")
    done = harness.api.post(
        f"/internal/worker/runs/{first.id}/complete", json=body, headers=_auth(token)
    )
    assert done.status_code == 204, done.text
    late = _url(harness, token, first.id, lease_id, f"runs/{first.id}/late.json")
    assert late.status_code == 409
    queued = runs[1]  # chưa start
    assert _url(harness, token, queued.id, lease_id, f"runs/{queued.id}/x.json").status_code == 409


def test_completed_run_artifacts_exist_no_candidates_and_webp_thumbnails(
    harness: Harness, buckets: Buckets
) -> None:
    name, token = harness.target()
    harness.profile(name, token, sec=0.01, batch=5, attacks=["fgsm"])
    experiment_id = harness.submit(name, harness.world.config({"fgsm": [8]}))
    harness.work(token, experiment_id)
    _, runs = harness.state(experiment_id)
    run = runs[0]
    assert run.status == "completed" and run.manifest_uri is not None
    assert buckets.artifacts.exists(run.manifest_uri.removeprefix("s3://artifacts/"))
    cases = harness.cases(run.id)
    assert cases, "fixture phải có failure case với FGSM eps 8"
    for case in cases:
        for key in case.artifacts.values():
            assert key is not None and buckets.artifacts.exists(key), key
        for key in (case.artifacts["clean_thumb"], case.artifacts["adversarial_thumb"]):
            image = Image.open(io.BytesIO(buckets.artifacts.get(key)))
            assert image.format == "WEBP" and image.width == 320
    assert buckets.artifacts.list(f"runs/{run.id}/candidates/") == []


def test_complete_validates_cases_and_artifacts(harness: Harness, buckets: Buckets) -> None:
    token, lease_id, runs, fingerprint = _started(harness, {"fgsm": [4]})
    run = runs[0]
    path = f"/internal/worker/runs/{run.id}/complete"

    def post(body: dict[str, Any]) -> httpx.Response:
        response: httpx.Response = harness.api.post(path, json=body, headers=_auth(token))
        return response

    keys = _case_keys(run.id)
    mismatched = _completion(run, lease_id, fingerprint, keys, "completed")
    mismatched["run_result"]["failure_case_ids"] = []
    assert post(mismatched).status_code == 422  # contract: id phải khớp record
    missing = _completion(run, lease_id, fingerprint, keys, "completed")  # chưa upload artifact
    missing["run_result"]["manifest_uri"] = f"s3://artifacts/runs/{run.id}/manifest.json"
    response = post(missing)
    assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_request"
    outside = _completion(run, lease_id, fingerprint, _case_keys(run.id, "runs/khac/cases/c1"),
                          "completed")  # fmt: skip
    outside["run_result"]["manifest_uri"] = f"s3://artifacts/runs/{run.id}/manifest.json"
    response = post(outside)
    assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_request"
    assert harness.cases(run.id) == []

    for key in keys.values():
        buckets.artifacts.put(key, key.encode())
    buckets.artifacts.put(f"runs/{run.id}/manifest.json", b"{}")
    valid = _completion(run, lease_id, fingerprint, keys, "completed")
    valid["run_result"]["manifest_uri"] = f"s3://artifacts/runs/{run.id}/manifest.json"
    assert post(valid).status_code == 204
    cases = harness.cases(run.id)
    assert [str(c.id) for c in cases] == valid["run_result"]["failure_case_ids"]


def test_same_fingerprint_stopped_then_full_both_keep_cases(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = harness.world.config({"fgsm": [8]}, seed=9)
    name, token = harness.target()
    harness.profile(name, token, sec=20.0, batch=4, attacks=["fgsm"])
    # Mỗi batch "tốn" 90 giây, giới hạn 100: batch 4 ảnh chạy (ước lượng 80), batch kế tiếp
    # (ước lượng 20 > 10 còn lại) không chạy → run dừng với kết quả một phần.
    ticks = count(0, 90)
    fake = SimpleNamespace(perf_counter=lambda: next(ticks))
    monkeypatch.setattr(executor_module, "time", fake)
    first = harness.submit(name, config, time_limit=100)
    harness.work(token, first)
    monkeypatch.undo()
    monkeypatch.setenv("GIT_COMMIT", "3" * 40)
    _, runs1 = harness.state(first)
    assert runs1[0].status == "stopped_limit" and runs1[0].images_done == 4

    second = harness.submit(name, config)  # cùng fingerprint, run gốc chưa completed
    harness.work(token, second)
    _, runs2 = harness.state(second)
    assert runs2[0].status == "completed" and runs2[0].fingerprint == runs1[0].fingerprint
    cases1, cases2 = harness.cases(runs1[0].id), harness.cases(runs2[0].id)
    assert cases1 and cases2
    assert not {c.id for c in cases1} & {c.id for c in cases2}
