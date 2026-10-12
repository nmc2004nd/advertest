"""`ToolRunner` trên API giả (`httpx.MockTransport`): hết job, lỗi hạ tầng gửi `error`, mất lease
thì không gửi gì."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from advertest_contracts.models import ToolJobResult
from advertest_worker.cache import JobCache
from advertest_worker.client import WorkerClient
from advertest_worker.tools import ToolRunner

MOCKS = Path(__file__).resolve().parents[3] / "contracts" / "mocks"
LEASE = json.loads((MOCKS / "tool_lease" / "quick_try.json").read_text())
BUNDLE = {
    **json.loads((MOCKS / "tool_job_bundle" / "quick_try.json").read_text()),
    "job_id": LEASE["job_id"],
}


class _Api:
    def __init__(self, *, has_job: bool = True, heartbeat_status: int = 204) -> None:
        self.has_job = has_job
        self.heartbeat_status = heartbeat_status
        self.heartbeat_called = threading.Event()
        self.results: list[ToolJobResult] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/tool-lease"):
            return httpx.Response(200, json=LEASE) if self.has_job else httpx.Response(204)
        if path.endswith("/heartbeat"):
            self.heartbeat_called.set()
            if self.heartbeat_status == 409:
                error = {"code": "conflict", "message": "mất lease"}
                return httpx.Response(409, json={"schema_version": 1, "error": error})
            return httpx.Response(204)
        if path.endswith("/result"):
            self.results.append(ToolJobResult.model_validate_json(request.content))
            return httpx.Response(204)
        return httpx.Response(200, json=BUNDLE)


def _offline(request: httpx.Request) -> httpx.Response:
    """Presigned URL không tải được (ví dụ MinIO không truy cập được)."""
    raise httpx.ConnectError("không tải được")


def _runner(api: _Api, tmp_path: Path, **kwargs: Any) -> ToolRunner:
    client = WorkerClient(
        httpx.Client(base_url="http://api", transport=httpx.MockTransport(api)),
        "tok",
        sleep=lambda _s: None,
    )
    offline = httpx.Client(transport=httpx.MockTransport(_offline))
    return ToolRunner(client, JobCache(tmp_path, http=offline), "cpu", url_http=offline, **kwargs)


def test_no_job(tmp_path: Path) -> None:
    api = _Api(has_job=False)
    assert _runner(api, tmp_path).run_next() is False
    assert api.results == []


def test_infrastructure_error_is_sent_as_error(tmp_path: Path) -> None:
    api = _Api()
    assert _runner(api, tmp_path).run_next() is True
    [result] = api.results
    assert str(result.lease_id) == LEASE["lease_id"] and result.report is None
    assert result.error is not None and "không tải được" in result.error


def test_lost_lease_drops_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    api = _Api(heartbeat_status=409)
    runner = _runner(api, tmp_path, heartbeat_interval_s=0.01)

    def slow(payload: Any) -> Any:
        assert api.heartbeat_called.wait(5)
        time.sleep(0.2)  # luồng heartbeat ghi nhận 409
        raise OSError("không tải được")

    monkeypatch.setattr(runner, "_run", slow)
    assert runner.run_next() is True
    assert api.results == []


class _FakeSandbox:
    """Thay `SpoolClient`: ghi lại file nhận được, trả safetensors do `save` tạo."""

    def __init__(self, result: bytes) -> None:
        self.result = result
        self.calls: list[tuple[str, bytes, str, str]] = []

    def convert(self, job_id: str, data: bytes, filename: str, framework: str) -> bytes:
        self.calls.append((job_id, data, filename, framework))
        return self.result


def test_model_convert_forwards_bytes_and_reads_header(tmp_path: Path) -> None:
    """Đề xuất contract 003: worker không mở `.pt`; chuyển byte cho sandbox, PUT kết quả, đọc
    metadata từ header safetensors."""
    import torch
    from safetensors.torch import save

    from advertest_contracts.models import ModelConvertPayload

    result = save(
        {"w": torch.zeros(2)},
        metadata={"framework": "ultralytics", "architecture": "yolo11n", "names": '["a", "b"]',
                  "imgsz": "640"},
    )  # fmt: skip
    puts: list[bytes] = []

    def storage(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            puts.append(request.content)
            return httpx.Response(200)
        return httpx.Response(200, content=b"\x80\x04pickle")

    payload = ModelConvertPayload.model_validate(
        json.loads((MOCKS / "tool_job_bundle" / "model_convert.json").read_text())["payload"]
    )
    sandbox = _FakeSandbox(result)
    runner = _runner(_Api(), tmp_path, converter=sandbox)
    runner.url_http = httpx.Client(transport=httpx.MockTransport(storage))
    report = runner._run(payload)
    assert sandbox.calls == [
        (str(payload.conversion_id), b"\x80\x04pickle", "best.pt", "ultralytics")
    ]
    assert puts == [result]
    assert report.kind == "model_convert"
    assert report.metadata.architecture == "yolo11n"  # type: ignore[union-attr]
    assert report.metadata.class_names == ["a", "b"]  # type: ignore[union-attr]


def test_model_convert_without_sandbox_is_error(tmp_path: Path) -> None:
    from advertest_contracts.models import ModelConvertPayload

    payload = ModelConvertPayload.model_validate(
        json.loads((MOCKS / "tool_job_bundle" / "model_convert.json").read_text())["payload"]
    )
    with pytest.raises(RuntimeError, match="CONVERT_SPOOL"):
        _runner(_Api(), tmp_path)._run(payload)
