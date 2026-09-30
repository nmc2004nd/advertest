"""Client của API nội bộ `/internal/worker` (plan.md Phase 3, task 23).

Mất kết nối hoặc lỗi 5xx: thử lại với backoff lũy thừa. Lỗi 4xx không thử lại: 409 là
`LeaseLost` (lease đã được cấp cho worker khác, hoặc run/experiment đổi trạng thái), còn lại là
`ApiError`.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar
from uuid import UUID

import httpx
from pydantic import BaseModel

from advertest_contracts.models import (
    ArtifactUrlRequest,
    ArtifactUrlResponse,
    CostProfile,
    ErrorResponse,
    HeartbeatRequest,
    PatchArtifact,
    PatchRegistration,
    ProgressReport,
    RunCompletion,
    RunSkipRequest,
    RunStartRequest,
    RunStartResponse,
    WorkerDirective,
    WorkerJobBundle,
    WorkerLease,
)
from ml_core.store.presigned import Method

logger = logging.getLogger(__name__)
PREFIX = "/internal/worker"
T = TypeVar("T", bound=BaseModel)


class ApiError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(f"{status_code} {code}: {message}")
        self.status_code = status_code
        self.code = code


class LeaseLost(ApiError):
    """409: worker phải dừng experiment đang chạy (không gửi gì thêm)."""


class WorkerClient:
    def __init__(
        self,
        http: httpx.Client,
        token: str,
        *,
        retries: int = 5,
        backoff_s: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.http = http
        self.headers = {"Authorization": f"Bearer {token}"}
        self.retries = retries
        self.backoff_s = backoff_s
        self.sleep = sleep

    @classmethod
    def connect(cls, api_url: str, token: str) -> WorkerClient:
        return cls(httpx.Client(base_url=api_url, timeout=60.0), token)

    def _request(self, method: str, path: str, body: BaseModel | None = None) -> httpx.Response:
        json: Any = body.model_dump(mode="json") if body is not None else None
        for attempt in range(self.retries + 1):
            try:
                response = self.http.request(method, PREFIX + path, json=json, headers=self.headers)
            except httpx.TransportError as exc:
                if attempt == self.retries:
                    raise
                logger.warning("Mất kết nối tới API (%s), thử lại", exc)
            else:
                if response.status_code < 500 or attempt == self.retries:
                    return self._check(response)
                logger.warning("API lỗi %s, thử lại", response.status_code)
            self.sleep(self.backoff_s * 2**attempt)
        raise AssertionError("không tới được đây")

    @staticmethod
    def _check(response: httpx.Response) -> httpx.Response:
        if response.status_code < 400:
            return response
        try:
            error = ErrorResponse.model_validate(response.json()).error
            code, message = str(error.code), error.message
        except (ValueError, TypeError):
            code, message = "unknown", response.text[:200]
        cls = LeaseLost if response.status_code == httpx.codes.CONFLICT else ApiError
        raise cls(response.status_code, code, message)

    def _parse(self, model: type[T], response: httpx.Response) -> T:
        return model.model_validate(response.json())

    # ------------------------------------------------------------------ endpoint

    def lease(self) -> WorkerLease | None:
        response = self._request("POST", "/lease")
        if response.status_code == httpx.codes.NO_CONTENT:
            return None
        return self._parse(WorkerLease, response)

    def bundle(self, experiment_id: UUID) -> WorkerJobBundle:
        return self._parse(
            WorkerJobBundle, self._request("GET", f"/experiments/{experiment_id}/bundle")
        )

    def heartbeat(self, lease_id: UUID, experiment_id: UUID) -> WorkerDirective:
        body = HeartbeatRequest(lease_id=lease_id, experiment_id=experiment_id)
        return self._parse(WorkerDirective, self._request("POST", "/heartbeat", body))

    def start(self, run_id: UUID, body: RunStartRequest) -> RunStartResponse:
        return self._parse(RunStartResponse, self._request("POST", f"/runs/{run_id}/start", body))

    def progress(self, run_id: UUID, body: ProgressReport) -> WorkerDirective:
        return self._parse(WorkerDirective, self._request("POST", f"/runs/{run_id}/progress", body))

    def artifact_url(self, run_id: UUID, lease_id: UUID, key: str, method: Method) -> str:
        body = ArtifactUrlRequest(lease_id=lease_id, key=key, method=method)
        response = self._request("POST", f"/runs/{run_id}/artifact-url", body)
        return self._parse(ArtifactUrlResponse, response).url

    def complete(self, run_id: UUID, body: RunCompletion) -> None:
        self._request("POST", f"/runs/{run_id}/complete", body)

    def cost_profile(self, body: CostProfile) -> None:
        self._request("POST", "/cost-profiles", body)

    # Phase 6
    def skip(self, run_id: UUID, body: RunSkipRequest) -> None:
        """Bỏ run `queued` do dừng sớm."""
        self._request("POST", f"/runs/{run_id}/skip", body)

    def register_patch(self, run_id: UUID, body: PatchRegistration) -> PatchArtifact:
        """Đăng ký patch vừa train; khóa đã có thì API trả bản cũ (dùng bản trả về)."""
        return self._parse(PatchArtifact, self._request("POST", f"/runs/{run_id}/patch", body))
