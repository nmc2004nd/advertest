"""Client API của worker: retry với backoff, mã lỗi (httpx.MockTransport)."""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from advertest_worker.client import ApiError, LeaseLost, WorkerClient


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
