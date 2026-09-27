"""API nội bộ cho worker (`/internal/worker`), xác thực bằng token của compute target."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Security

from advertest_contracts.models import ExperimentConfig, Progress, RunResult, SearchResult
from backend.app.api.errors import NOT_IMPLEMENTED_RESPONSE, not_implemented
from backend.app.api.security import worker_token

router = APIRouter(
    prefix="/internal/worker",
    tags=["internal-worker"],
    dependencies=[Security(worker_token)],
    responses=NOT_IMPLEMENTED_RESPONSE,
)


@router.post("/lease")
def lease() -> ExperimentConfig:
    """Nhận experiment kế tiếp dành cho máy này."""
    not_implemented()


@router.post("/heartbeat")
def heartbeat() -> None:
    not_implemented()


@router.post("/runs/{run_id}/progress")
def report_progress(run_id: UUID, progress: Progress) -> None:
    """Cập nhật tiến độ và checkpoint."""
    not_implemented()


@router.post("/runs/{run_id}/artifact-url")
def artifact_url(run_id: UUID) -> None:
    """Xin presigned URL để upload artifact."""
    not_implemented()


@router.post("/runs/{run_id}/complete")
def complete_run(run_id: UUID, result: RunResult) -> None:
    """Gửi RunResult cuối cùng."""
    not_implemented()


@router.post("/experiments/{experiment_id}/search-result")
def submit_search_result(experiment_id: UUID, result: SearchResult) -> None:
    not_implemented()
