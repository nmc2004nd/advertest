"""Client API của worker: retry với backoff, mã lỗi (httpx.MockTransport)."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from advertest_contracts.models import (
    BundleRun,
    SearchResultReport,
    SearchRunCreate,
    ToolJobResult,
)
from advertest_worker.client import ApiError, LeaseLost, WorkerClient

MOCKS = Path(__file__).resolve().parents[3] / "contracts" / "mocks"


def _client(handler: httpx.MockTransport, retries: int = 3) -> tuple[WorkerClient, list[float]]:
    sleeps: list[float] = []
    http = httpx.Client(base_url="http://api", transport=handler)
    return WorkerClient(http, "tok", retries=retries, backoff_s=0.1, sleep=sleeps.append), sleeps


def _error(status: int, code: str) -> httpx.Response:
    return httpx.Response(
        status, json={"schema_version": 1, "error": {"code": code, "message": "m"}}
    )


def test_lease_204_and_token_header() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    client, _ = _client(httpx.MockTransport(handler))
    assert client.lease() is None
    assert seen[0].url.path == "/internal/worker/lease"
    assert seen[0].headers["Authorization"] == "Bearer tok"


def test_retries_on_connection_error_and_5xx_with_backoff() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("down")
        if calls == 2:
            return httpx.Response(503)
        return httpx.Response(204)

    client, sleeps = _client(httpx.MockTransport(handler))
    assert client.lease() is None
    assert calls == 3 and sleeps == [0.1, 0.2]


def test_gives_up_after_retries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    client, sleeps = _client(httpx.MockTransport(handler), retries=2)
    with pytest.raises(httpx.ConnectError):
        client.lease()
    assert len(sleeps) == 2

    client, _ = _client(httpx.MockTransport(lambda r: _error(500, "x")), retries=1)
    with pytest.raises(ApiError) as info:
        client.lease()
    assert info.value.status_code == 500


def test_4xx_not_retried_and_409_is_lease_lost() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _error(409, "conflict")

    client, sleeps = _client(httpx.MockTransport(handler))
    with pytest.raises(LeaseLost):
        client.heartbeat(uuid4(), uuid4())
    assert calls == 1 and sleeps == []

    client, _ = _client(httpx.MockTransport(lambda r: _error(422, "invalid_request")))
    with pytest.raises(ApiError) as info:
        client.heartbeat(uuid4(), uuid4())
    assert info.value.code == "invalid_request" and not isinstance(info.value, LeaseLost)

    client, _ = _client(httpx.MockTransport(lambda r: httpx.Response(401, text="plain")))
    with pytest.raises(ApiError) as info:
        client.lease()
    assert info.value.code == "unknown"


# ---------------------------------------------------------------- Phase 7


def _mock(name: str) -> str:
    return (MOCKS / name).read_text()


def test_create_search_run_and_422_is_not_lease_lost() -> None:
    bundle = json.loads(_mock("worker_job_bundle/search_resume_coarse.json"))
    run = bundle["runs"][-1]
    seen: list[httpx.Request] = []
    status = {"code": 201}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if status["code"] == 422:
            return _error(422, "invalid_request")
        return httpx.Response(201, json=run)

    client, _ = _client(httpx.MockTransport(handler))
    body = SearchRunCreate.model_validate_json(_mock("search_run_create/subset_coarse.json"))
    experiment_id = uuid4()
    created = client.create_search_run(experiment_id, body)
    assert created == BundleRun.model_validate(run)
    assert seen[0].url.path == f"/internal/worker/experiments/{experiment_id}/runs"
    status["code"] = 422
    with pytest.raises(ApiError) as excinfo:
        client.create_search_run(experiment_id, body)
    assert not isinstance(excinfo.value, LeaseLost)


def test_search_result_posts_report() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    client, _ = _client(httpx.MockTransport(handler))
    body = SearchResultReport.model_validate_json(
        _mock("search_result_report/interim_bisect_subset.json")
    )
    client.search_result(body.result.experiment_id, body)
    assert seen[0].url.path.endswith(f"/experiments/{body.result.experiment_id}/search-result")
    assert SearchResultReport.model_validate_json(seen[0].content) == body


# ---------------------------------------------------------------- Phase R2: job công cụ


def test_tool_endpoints_parse_contract_mocks() -> None:
    lease = json.loads((MOCKS / "tool_lease" / "quick_try.json").read_text())
    bundle = json.loads((MOCKS / "tool_job_bundle" / "quick_try.json").read_text())
    result = json.loads((MOCKS / "tool_job_result" / "error.json").read_text())
    seen: list[tuple[str, str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.content))
        if request.url.path.endswith("/tool-lease"):
            return httpx.Response(200, json=lease)
        if request.method == "GET":
            return httpx.Response(200, json=bundle)
        return httpx.Response(204)

    client, _ = _client(httpx.MockTransport(handler))
    leased = client.tool_lease()
    assert leased is not None and str(leased.job_id) == lease["job_id"]
    assert client.tool_bundle(leased.job_id).payload.kind == "quick_try"
    client.tool_heartbeat(leased.job_id, leased.lease_id)
    client.tool_result(leased.job_id, ToolJobResult.model_validate(result))
    base = f"/internal/worker/tool-jobs/{leased.job_id}"
    assert [(m, p) for m, p, _ in seen] == [
        ("POST", "/internal/worker/tool-lease"),
        ("GET", base),
        ("POST", f"{base}/heartbeat"),
        ("POST", f"{base}/result"),
    ]
    assert json.loads(seen[2][2]) == {"lease_id": str(leased.lease_id)}
    assert json.loads(seen[3][2])["error"] == result["error"]


def test_tool_lease_204_and_lost_heartbeat() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tool-lease"):
            return httpx.Response(204)
        return _error(409, "conflict")

    client, _ = _client(httpx.MockTransport(handler))
    assert client.tool_lease() is None
    with pytest.raises(LeaseLost):
        client.tool_heartbeat(uuid4(), uuid4())
