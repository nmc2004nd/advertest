"""`SearchHooks` của `SearchDriver` trên API và model thật (requirements.md Phase 7; Phase R1,
`### Điều phối`).

Tạo run tìm ngưỡng qua API, chạy run bằng hàm chạy một run của worker, gửi kết quả tìm ngưỡng và
đọc prediction theo ảnh cho bootstrap (bộ nhớ trong phiên, hoặc file của run qua `artifact-url`).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from typing import Protocol
from uuid import UUID

import httpx

from advertest_contracts.enums import EvalScope, RunStatus
from advertest_contracts.models import (
    AttackConfig,
    AttackSpec,
    BundleRun,
    SearchResult,
    SearchResultReport,
    SearchRunCreate,
)
from advertest_worker.client import ApiError, LeaseLost
from advertest_worker.errors import StopExperiment
from advertest_worker.search import PointOutcome
from advertest_worker.state import JobState
from ml_core.metrics.bootstrap import load_run_predictions, run_predictions_key
from ml_core.metrics.filters import Prediction
from ml_core.store import KeyNotFoundError, PresignedStore
from ml_core.store.presigned import Method

logger = logging.getLogger(__name__)
_PREDICTIONS_KEY = re.compile(r"runs/([0-9a-f-]{36})/predictions\.json")

# (job, run_id, spec) → chạy run tới khi gửi kết quả; `StopExperiment` khi experiment phải dừng.
RunOne = Callable[[JobState, UUID, AttackSpec], None]


class SearchClient(Protocol):
    def create_search_run(self, experiment_id: UUID, body: SearchRunCreate) -> BundleRun: ...

    def search_result(self, experiment_id: UUID, body: SearchResultReport) -> None: ...

    def artifact_url(self, run_id: UUID, lease_id: UUID, key: str, method: Method) -> str: ...


class JobSearchHooks:
    """`SearchHooks` của `SearchDriver` trên API và model thật."""

    def __init__(
        self,
        client: SearchClient,
        url_http: httpx.Client,
        run_one: RunOne,
        job: JobState,
        attack: AttackConfig,
        spec: AttackSpec,
    ) -> None:
        self.client = client
        self.url_http = url_http
        self.run_one = run_one
        self.job = job
        self.attack = attack
        self.spec = spec

    def should_stop(self) -> bool:
        return self.job.stop_requested()

    def create_run(self, attack_spec_id: UUID, level: float, scope: EvalScope, order: int) -> UUID:
        job = self.job
        run = self.client.create_search_run(
            job.bundle.experiment_id,
            SearchRunCreate(
                lease_id=job.lease.lease_id,
                attack_spec_id=attack_spec_id,
                level=level,
                scope=scope,
                search_order=order,
            ),
        )
        if (run.attack_spec_id, run.level, run.scope, run.search_order) != (
            attack_spec_id,
            level,
            scope,
            order,
        ):
            raise ValueError(f"API tạo run {run.run_id} không khớp điểm đã yêu cầu")
        job.runs[run.run_id] = run
        job.ledger.add(run)
        return run.run_id

    def execute(self, run_id: UUID) -> PointOutcome:
        job = self.job
        try:
            self.run_one(job, run_id, self.spec)
        except StopExperiment:
            outcome = job.outcomes.get(run_id, PointOutcome(RunStatus.CANCELLED, None))
            return PointOutcome(outcome.status, outcome.metrics, outcome.message, stop=True)
        return job.outcomes[run_id]

    def report(self, result: SearchResult) -> None:
        self.client.search_result(
            self.job.bundle.experiment_id,
            SearchResultReport(lease_id=self.job.lease.lease_id, result=result),
        )

    def predictions(self, run_id: UUID) -> dict[str, Prediction] | None:
        """Prediction của run hoàn tất trong phiên này (bộ nhớ); run đã kết thúc ở phiên trước
        hoặc trúng cache thì đọc `runs/<run_id>/predictions.json` qua `artifact-url` của chính run
        (đề xuất contract 001, plan task 18b). Không có file → `None` (bỏ khỏi bootstrap)."""
        cached = self.job.predictions.get(run_id)
        if cached is not None:
            return cached
        client, lease_id = self.client, self.job.lease.lease_id
        store = PresignedStore(
            lambda key, method: client.artifact_url(run_id, lease_id, key, method),
            self.url_http,
        )
        try:
            return read_predictions_file(store.get(run_predictions_key(run_id)))
        except KeyNotFoundError:
            logger.warning("Run %s không có file prediction: bỏ khỏi bootstrap", run_id)
        except LeaseLost:
            raise
        except (ApiError, httpx.HTTPError, ValueError):
            # Review task 18b #1: lỗi đọc file (MinIO, API từ chối, file hỏng) không được làm sập
            # job; điểm bị bỏ khỏi bootstrap như khi không có file.
            logger.warning(
                "Không đọc được prediction của run %s: bỏ khỏi bootstrap", run_id, exc_info=True
            )
        return None


def read_predictions_file(data: bytes) -> dict[str, Prediction]:
    """File prediction của một run. Bản sao do API tạo khi trúng cache giữ khóa của run gốc trong
    trường `key`: đọc theo đúng run ghi trong file (vẫn kiểm file nhất quán với khóa của nó)."""
    key = json.loads(data).get("key")
    match = _PREDICTIONS_KEY.fullmatch(key) if isinstance(key, str) else None
    if match is None:
        raise ValueError(f"File prediction có khóa không hợp lệ: {key!r}")
    return load_run_predictions(data, UUID(match.group(1)))
