"""API nội bộ cho worker (`/internal/worker`), xác thực bằng token của compute target.

Mọi thay đổi trạng thái do API thực hiện qua service (requirements.md Phase 3); worker không có
thông tin đăng nhập DB hay MinIO. Lỗi service đổi sang HTTP ở `errors.install_error_handlers`.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, Security, status

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
from backend.app.api.deps import (
    SessionFactory,
    Storage,
    authenticate_worker,
    bearer_token,
    get_clock,
    get_sessionmaker,
    get_storage,
    transaction,
)
from backend.app.api.errors import (
    NOT_IMPLEMENTED_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
    not_implemented,
)
from backend.app.api.security import worker_token
from backend.app.services import bundle, leasing, runs
from backend.app.services.clock import Clock

router = APIRouter(
    prefix="/internal/worker",
    tags=["internal-worker"],
    dependencies=[Security(worker_token)],
    responses=NOT_IMPLEMENTED_RESPONSE | VALIDATION_ERROR_RESPONSE,
)

Credentials = Annotated[str, Depends(bearer_token)]
Sessions = Annotated[SessionFactory, Depends(get_sessionmaker)]
Stores = Annotated[Storage, Depends(get_storage)]
Now = Annotated[Clock, Depends(get_clock)]


@router.post(
    "/lease",
    response_model=WorkerLease,
    responses={status.HTTP_204_NO_CONTENT: {"description": "Không có experiment nào chờ"}},
)
def lease(credentials: Credentials, sessions: Sessions, clock: Now) -> WorkerLease | Response:
    """Nhận experiment `queued` cũ nhất của target (hoặc experiment có lease đã hết hạn)."""
    with transaction(sessions) as session:
        target = authenticate_worker(session, credentials)
        experiment = leasing.lease(session, target, clock)
        if experiment is None:
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        assert experiment.lease_id is not None and experiment.lease_expires_at is not None
        return WorkerLease(
            experiment_id=experiment.id,
            lease_id=experiment.lease_id,
            lease_expires_at=experiment.lease_expires_at,
        )


@router.get("/experiments/{experiment_id}/bundle")
def get_bundle(
    experiment_id: UUID, credentials: Credentials, sessions: Sessions, stores: Stores, clock: Now
) -> WorkerJobBundle:
    """Mọi thứ cần để chạy experiment, kèm presigned URL tải (hết hạn sau 15 phút)."""
    with transaction(sessions) as session:
        target = authenticate_worker(session, credentials)
        return bundle.build(session, target, experiment_id, stores.buckets, stores.presigner, clock)


@router.post("/heartbeat")
def heartbeat(
    body: HeartbeatRequest, credentials: Credentials, sessions: Sessions, clock: Now
) -> WorkerDirective:
    """Gia hạn lease 60 giây."""
    with transaction(sessions) as session:
        target = authenticate_worker(session, credentials)
        return leasing.heartbeat(session, target, body.experiment_id, body.lease_id, clock)


@router.post("/runs/{run_id}/start")
def start_run(
    run_id: UUID, body: RunStartRequest, credentials: Credentials, sessions: Sessions, clock: Now
) -> RunStartResponse:
    """Chạy run, hoặc bỏ qua khi đã có run `completed` cùng fingerprint."""
    with transaction(sessions) as session:
        target = authenticate_worker(session, credentials)
        try:
            return runs.start(session, target, run_id, body, clock)
        except runs.RunInvalidated as exc:
            invalidated = exc  # commit trạng thái failed rồi mới trả 409
    raise invalidated


@router.post("/runs/{run_id}/progress")
def report_progress(
    run_id: UUID, body: ProgressReport, credentials: Credentials, sessions: Sessions, clock: Now
) -> WorkerDirective:
    """Báo tiến độ sau mỗi batch; cộng dồn thời gian xử lý."""
    with transaction(sessions) as session:
        target = authenticate_worker(session, credentials)
        return runs.progress(session, target, run_id, body, clock)


@router.post("/runs/{run_id}/artifact-url")
def artifact_url(
    run_id: UUID,
    body: ArtifactUrlRequest,
    credentials: Credentials,
    sessions: Sessions,
    stores: Stores,
    clock: Now,
) -> ArtifactUrlResponse:
    """Presigned URL (PUT, GET, DELETE) cho một khóa nằm trong `runs/<run_id>/`."""
    with transaction(sessions) as session:
        target = authenticate_worker(session, credentials)
        return runs.artifact_url(session, target, run_id, body, stores.presigner, clock)


@router.post("/runs/{run_id}/complete", status_code=status.HTTP_204_NO_CONTENT)
def complete_run(
    run_id: UUID,
    body: RunCompletion,
    credentials: Credentials,
    sessions: Sessions,
    stores: Stores,
    clock: Now,
) -> None:
    """Kết quả cuối của run kèm failure case."""
    with transaction(sessions) as session:
        target = authenticate_worker(session, credentials)
        runs.complete(session, target, run_id, body, stores.buckets.artifacts.exists, clock)


@router.post("/cost-profiles", status_code=status.HTTP_204_NO_CONTENT)
def submit_cost_profile(body: CostProfile, credentials: Credentials, sessions: Sessions) -> None:
    """Cost profile đo bằng calibration cho target của token."""
    with transaction(sessions) as session:
        target = authenticate_worker(session, credentials)
        runs.record_cost_profile(session, target, body)


@router.post("/experiments/{experiment_id}/search-result")
def submit_search_result(experiment_id: UUID, result: SearchResult) -> None:
    not_implemented()
