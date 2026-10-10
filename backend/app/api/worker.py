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
    BundleRun,
    CostProfile,
    HeartbeatRequest,
    PatchArtifact,
    PatchRegistration,
    ProgressReport,
    RunCompletion,
    RunSkipRequest,
    RunStartRequest,
    RunStartResponse,
    SearchResultReport,
    SearchRunCreate,
    ToolHeartbeat,
    ToolJobBundle,
    ToolJobResult,
    ToolLease,
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
)
from backend.app.api.security import worker_token
from backend.app.services import bundle, leasing, runs, searches, tool_dispatch, tool_jobs
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
    run_id: UUID,
    body: RunStartRequest,
    credentials: Credentials,
    sessions: Sessions,
    stores: Stores,
    clock: Now,
) -> RunStartResponse:
    """Chạy run, hoặc bỏ qua khi đã có run `completed` cùng fingerprint."""
    # Phase 7 (đề xuất contract 001): trúng cache thì sao chép file prediction của run gốc.
    artifacts = stores.buckets.artifacts

    def copy(source: str, target_key: str) -> bool:
        if not artifacts.exists(source):
            return False
        artifacts.put(target_key, artifacts.get(source))
        return True

    with transaction(sessions) as session:
        target = authenticate_worker(session, credentials)
        try:
            return runs.start(session, target, run_id, body, clock, copy)
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


@router.post("/runs/{run_id}/skip", status_code=status.HTTP_204_NO_CONTENT)
def skip_run(
    run_id: UUID, body: RunSkipRequest, credentials: Credentials, sessions: Sessions, clock: Now
) -> None:
    """Bỏ run `queued` do dừng sớm (Phase 6); `trigger_run_id` là run cùng attack đã làm model
    sụp."""
    with transaction(sessions) as session:
        target = authenticate_worker(session, credentials)
        runs.skip(session, target, run_id, body, clock)


@router.post("/runs/{run_id}/patch")
def register_patch(
    run_id: UUID,
    body: PatchRegistration,
    credentials: Credentials,
    sessions: Sessions,
    stores: Stores,
    clock: Now,
) -> PatchArtifact:
    """Đăng ký patch vừa train xong cho run patch (Phase 6). Khóa đã có thì giữ bản cũ và trả bản
    đó."""
    with transaction(sessions) as session:
        target = authenticate_worker(session, credentials)
        return runs.register_patch(
            session, target, run_id, body, stores.buckets.artifacts.exists, clock
        )


@router.post("/cost-profiles", status_code=status.HTTP_204_NO_CONTENT)
def submit_cost_profile(body: CostProfile, credentials: Credentials, sessions: Sessions) -> None:
    """Cost profile đo bằng calibration cho target của token."""
    with transaction(sessions) as session:
        target = authenticate_worker(session, credentials)
        runs.record_cost_profile(session, target, body)


@router.post("/experiments/{experiment_id}/runs", status_code=status.HTTP_201_CREATED)
def create_search_run(
    experiment_id: UUID,
    body: SearchRunCreate,
    credentials: Credentials,
    sessions: Sessions,
    clock: Now,
) -> BundleRun:
    """Tạo run `queued` cho điểm tìm ngưỡng kế tiếp (Phase 7). Vi phạm (attack không ở chế độ tìm
    ngưỡng, level ngoài `[lo, hi]`, vượt `max_points`) trả `422`, không `409`."""
    # Hết thời gian: API chốt kết quả tìm ngưỡng, experiment kết thúc, trả 409 (quyết định Group 4).
    with transaction(sessions) as session:
        target = authenticate_worker(session, credentials)
        try:
            return searches.create_run(session, target, experiment_id, body, clock)
        except searches.SearchStopped as exc:
            stopped = exc  # commit kết quả đã chốt rồi mới trả 409
    raise stopped


@router.post("/experiments/{experiment_id}/search-result", status_code=status.HTTP_204_NO_CONTENT)
def submit_search_result(
    experiment_id: UUID,
    body: SearchResultReport,
    credentials: Credentials,
    sessions: Sessions,
    clock: Now,
) -> None:
    """SearchResult tạm thời sau mỗi điểm, hoặc kết quả cuối (Phase 7)."""
    with transaction(sessions) as session:
        target = authenticate_worker(session, credentials)
        searches.submit_result(session, target, experiment_id, body, clock)


# Phase R2: job công cụ của worker `--tools` (spec_check, model_check, quick_try).


@router.post(
    "/tool-lease",
    response_model=ToolLease,
    responses={status.HTTP_204_NO_CONTENT: {"description": "Không có job công cụ nào chờ"}},
)
def tool_lease(credentials: Credentials, sessions: Sessions, clock: Now) -> ToolLease | Response:
    """Job công cụ cũ nhất: quick_try trước, rồi model_check và spec_check theo thứ tự tạo."""
    with transaction(sessions) as session:
        target = authenticate_worker(session, credentials)
        leased = tool_dispatch.lease(session, target, clock())
    return leased if leased is not None else Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/tool-jobs/{job_id}")
def get_tool_job(
    job_id: UUID, credentials: Credentials, sessions: Sessions, stores: Stores, clock: Now
) -> ToolJobBundle:
    """Payload của job, kèm presigned URL (hết hạn sau 15 phút)."""
    with transaction(sessions) as session:
        target = authenticate_worker(session, credentials)
        return tool_dispatch.bundle(
            session, target, job_id, stores.buckets, stores.presigner, clock()
        )


@router.post("/tool-jobs/{job_id}/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
def tool_heartbeat(
    job_id: UUID, body: ToolHeartbeat, credentials: Credentials, sessions: Sessions, clock: Now
) -> None:
    """Gia hạn lease 60 giây (409 khi lease đã mất)."""
    with transaction(sessions) as session:
        target = authenticate_worker(session, credentials)
        tool_jobs.heartbeat(session, target, job_id, body.lease_id, clock())


@router.post("/tool-jobs/{job_id}/result", status_code=status.HTTP_204_NO_CONTENT)
def submit_tool_result(
    job_id: UUID,
    body: ToolJobResult,
    credentials: Credentials,
    sessions: Sessions,
    stores: Stores,
    clock: Now,
) -> None:
    """Kết quả job; chỉ token worker ghi được (mission.md nguyên tắc 3)."""
    with transaction(sessions) as session:
        target = authenticate_worker(session, credentials)
        tool_dispatch.submit(session, target, job_id, body, stores.buckets, clock())
