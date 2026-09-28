"""API nội bộ cho worker (`/internal/worker`), xác thực bằng token của compute target.

Chữ ký endpoint theo `requirements.md` Phase 3 (Group 0); Group 3 cài đặt phần thân.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Security, status

from advertest_contracts.models import (
    ArtifactUrlRequest,
    ArtifactUrlResponse,
    CostProfile,
    HeartbeatRequest,
    ProgressReport,
    RunCompletion,
    RunStartRequest,
    RunStartResponse,
    SearchResult,
    WorkerDirective,
    WorkerJobBundle,
    WorkerLease,
)
from backend.app.api.errors import NOT_IMPLEMENTED_RESPONSE, not_implemented
from backend.app.api.security import worker_token

router = APIRouter(
    prefix="/internal/worker",
    tags=["internal-worker"],
    dependencies=[Security(worker_token)],
    responses=NOT_IMPLEMENTED_RESPONSE,
)


@router.post(
    "/lease",
    responses={status.HTTP_204_NO_CONTENT: {"description": "Không có experiment nào chờ"}},
)
def lease() -> WorkerLease:
    """Nhận experiment `queued` cũ nhất của target (hoặc experiment có lease đã hết hạn)."""
    not_implemented()


@router.get("/experiments/{experiment_id}/bundle")
def get_bundle(experiment_id: UUID) -> WorkerJobBundle:
    """Mọi thứ cần để chạy experiment, kèm presigned URL tải (hết hạn sau 15 phút)."""
    not_implemented()


@router.post("/heartbeat")
def heartbeat(body: HeartbeatRequest) -> WorkerDirective:
    """Gia hạn lease 60 giây."""
    not_implemented()


@router.post("/runs/{run_id}/start")
def start_run(run_id: UUID, body: RunStartRequest) -> RunStartResponse:
    """Chạy run, hoặc bỏ qua khi đã có run `completed` cùng fingerprint."""
    not_implemented()


@router.post("/runs/{run_id}/progress")
def report_progress(run_id: UUID, body: ProgressReport) -> WorkerDirective:
    """Báo tiến độ sau mỗi batch; cộng dồn thời gian xử lý."""
    not_implemented()


@router.post("/runs/{run_id}/artifact-url")
def artifact_url(run_id: UUID, body: ArtifactUrlRequest) -> ArtifactUrlResponse:
    """Presigned URL (PUT, GET, DELETE) cho một khóa nằm trong `runs/<run_id>/`."""
    not_implemented()


@router.post("/runs/{run_id}/complete", status_code=status.HTTP_204_NO_CONTENT)
def complete_run(run_id: UUID, body: RunCompletion) -> None:
    """Kết quả cuối của run kèm failure case."""
    not_implemented()


@router.post("/cost-profiles", status_code=status.HTTP_204_NO_CONTENT)
def submit_cost_profile(body: CostProfile) -> None:
    """Cost profile đo bằng calibration cho target của token."""
    not_implemented()


@router.post("/experiments/{experiment_id}/search-result")
def submit_search_result(experiment_id: UUID, result: SearchResult) -> None:
    not_implemented()
