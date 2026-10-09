"""Endpoint cho người dùng: mỗi nhóm một endpoint đại diện (khung tối thiểu), cộng đủ endpoint
xác thực, quản trị người dùng và audit log của Phase 4 (khung, trả 501 cho tới Group 1-3).

Model request/response chỉ dùng schema đã có trong `advertest_contracts`; schema còn lại
do phase tương ứng thêm vào contract (Phase 6-8). Phase 5 Group 0 thêm khung cho các endpoint
đọc tài nguyên, experiment, run, failure case và ảnh (requirements.md Phase 5, Behaviour).

Mọi route cần phiên khai quyền bằng `**guard(p)` (requirements.md Phase 4, mục Bảo vệ endpoint):
dependency kiểm tra phiên và permission chạy trước thân hàm (nên trước cả `501`), và `x-permission`
trong OpenAPI là một `Permission` của ma trận hoặc `authenticated` (chỉ cần đăng nhập).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    Request,
    Response,
    Security,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from advertest_contracts.enums import (
    ErrorCode,
    ExperimentMode,
    ExperimentStatus,
    ReviewDecision,
    ReviewQueueFilter,
    UserStatus,
)
from advertest_contracts.models import (
    AccessRequest,
    ApproveRequest,
    AttackAdapterInfo,
    AttackSpecAdminPage,
    AttackSpecAdminView,
    AttackSpecCreate,
    AttackSpecMetadata,
    AttackSpecReject,
    AttackSpecView,
    AuditLogPage,
    CaseVerdictInput,
    CaseVerdictView,
    ClassMappingSummary,
    ComputeTargetPublic,
    DatasetSummary,
    DatasetVersionSummary,
    ErrorResponse,
    EstimateResponse,
    ExperimentClone,
    ExperimentCreate,
    ExperimentDetail,
    ExperimentDraftRequest,
    ExperimentInsight,
    ExperimentPage,
    ExperimentPreset,
    FailureCaseView,
    LoginRequest,
    Manifest,
    Me,
    ModelRegister,
    ModelSummary,
    ModelUpload,
    ModelUploadCreate,
    PasswordChange,
    PasswordResetConsume,
    PasswordResetLink,
    PresetKey,
    PromoteRequest,
    ProtocolCreate,
    ProtocolSummary,
    ProtocolTemplate,
    ProtocolVersionCreate,
    ProtocolView,
    QuickTryView,
    RejectRequest,
    ReportDetail,
    ReportDownload,
    ReportView,
    ReviewComment,
    ReviewCommentCreate,
    ReviewDecisionInput,
    ReviewQueueItem,
    RolesUpdate,
    RunView,
    SliceSummary,
    SubmitForReview,
    UserAdminPage,
    UserAdminView,
    VerifyInfo,
)
from advertest_contracts.permissions import AUTHENTICATED
from advertest_contracts.permissions import Permission as P
from backend.app.admin import users as admin_users
from backend.app.api.deps import (
    ArtifactReader,
    SessionFactory,
    get_artifact_reader,
    get_clock,
    get_sessionmaker,
    get_storage,
    transaction,
)
from backend.app.api.errors import (
    AUTH_REQUIRED_RESPONSES,
    NOT_IMPLEMENTED_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
    ApiError,
    not_implemented,
)
from backend.app.api.security import user_session
from backend.app.audit.query import AuditFilter, list_entries
from backend.app.auth import service as auth_service
from backend.app.auth import sessions
from backend.app.auth.deps import CurrentUser, Principal
from backend.app.auth.permissions import guard
from backend.app.db import models as m
from backend.app.protocols import service as protocol_service
from backend.app.reports import service as report_service
from backend.app.reviews import service as review_service
from backend.app.services import (
    artifacts,
    catalog,
    estimate,
    experiment_config,
    experiment_views,
    experiments,
)
from backend.app.services.clock import Clock
from ml_core.store import KeyNotFoundError

Sessions = Annotated[SessionFactory, Depends(get_sessionmaker)]
Now = Annotated[Clock, Depends(get_clock)]

AUTH_FAILURE_STATUS = {
    ErrorCode.INVALID_CREDENTIALS: status.HTTP_401_UNAUTHORIZED,
    ErrorCode.ACCOUNT_PENDING: status.HTTP_403_FORBIDDEN,
    ErrorCode.ACCOUNT_REJECTED: status.HTTP_403_FORBIDDEN,
    ErrorCode.ACCOUNT_DISABLED: status.HTTP_403_FORBIDDEN,
    ErrorCode.RATE_LIMITED: status.HTTP_429_TOO_MANY_REQUESTS,
    ErrorCode.INVALID_REQUEST: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ErrorCode.VALIDATION_ERROR: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def auth_error(failure: auth_service.AuthFailure) -> ApiError:
    return ApiError(AUTH_FAILURE_STATUS[failure.code], failure.code, failure.message)


def client_ip(request: Request) -> str | None:
    """IP đã qua ProxyHeadersMiddleware (X-Forwarded-For chỉ khi đến từ TRUSTED_PROXIES)."""
    return request.client.host if request.client else None


# Endpoint công khai của xác thực: không cần phiên.
auth_public_router = APIRouter(
    prefix="/auth", tags=["auth"], responses=NOT_IMPLEMENTED_RESPONSE | VALIDATION_ERROR_RESPONSE
)


@auth_public_router.post("/request-access", status_code=status.HTTP_202_ACCEPTED)
def request_access(body: AccessRequest, factory: Sessions) -> Response:
    with transaction(factory) as session:
        auth_service.request_access(session, body)
    # 202 không có body (requirements.md Phase 4), không phải JSON `null`.
    return Response(status_code=status.HTTP_202_ACCEPTED)


@auth_public_router.post(
    "/login",
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "invalid_credentials",
        },
        status.HTTP_403_FORBIDDEN: {
            "model": ErrorResponse,
            "description": "account_pending, account_rejected hoặc account_disabled",
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse, "description": "rate_limited"},
    },
)
def login(
    body: LoginRequest, request: Request, response: Response, factory: Sessions, clock: Now
) -> Me:
    now = clock()
    with transaction(factory) as session:
        outcome = auth_service.login(
            session,
            body,
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
            now=now,
        )
    # Lỗi ném sau khi commit: sự kiện login_failed phải được ghi lại.
    if isinstance(outcome, auth_service.AuthFailure):
        raise auth_error(outcome)
    sessions.set_cookies(response, outcome.issued, now=now)
    return outcome.me


@auth_public_router.post("/password-reset", status_code=status.HTTP_204_NO_CONTENT)
def consume_password_reset(body: PasswordResetConsume, factory: Sessions, clock: Now) -> None:
    with transaction(factory) as session:
        failure = auth_service.consume_password_reset(session, body, now=clock())
        if failure is not None:
            raise auth_error(failure)


router = APIRouter(
    dependencies=[Security(user_session)],
    responses=NOT_IMPLEMENTED_RESPONSE | AUTH_REQUIRED_RESPONSES | VALIDATION_ERROR_RESPONSE,
)

Cursor = Annotated[str | None, Query(description="next_cursor của trang trước")]
Limit = Annotated[int, Query(ge=1, le=100)]


@router.post(
    "/auth/logout",
    tags=["auth"],
    status_code=status.HTTP_204_NO_CONTENT,
    **guard(AUTHENTICATED),
)
def logout(
    user: CurrentUser, request: Request, response: Response, factory: Sessions, clock: Now
) -> None:
    with transaction(factory) as session:
        auth_service.logout(
            session,
            session_id=user.session_id,
            email=user.email,
            ip=client_ip(request),
            now=clock(),
        )
    sessions.clear_cookies(response)


@router.get("/auth/me", tags=["auth"], **guard(AUTHENTICATED))
def get_me(user: CurrentUser) -> Me:
    return user.to_me()


@router.post(
    "/auth/password",
    tags=["auth"],
    status_code=status.HTTP_204_NO_CONTENT,
    **guard(AUTHENTICATED),
)
def change_password(body: PasswordChange, user: CurrentUser, factory: Sessions, clock: Now) -> None:
    with transaction(factory) as session:
        failure = auth_service.change_password(
            session, user_id=user.user_id, session_id=user.session_id, body=body, now=clock()
        )
        if failure is not None:
            raise auth_error(failure)


@router.get("/admin/users", tags=["admin-users"], **guard(P.USER_MANAGE))
def list_users(
    factory: Sessions,
    status: UserStatus | None = None,
    cursor: Cursor = None,
    limit: Limit = 50,
) -> UserAdminPage:
    with transaction(factory) as session:
        return admin_users.list_users(session, status=status, cursor=cursor, limit=limit)


@router.post("/admin/users/{user_id}/approve", tags=["admin-users"], **guard(P.USER_MANAGE))
def approve_user(
    user_id: UUID, body: ApproveRequest, user: CurrentUser, factory: Sessions, clock: Now
) -> UserAdminView:
    with transaction(factory) as session:
        actor = admin_users.get_actor(session, user.user_id)
        return admin_users.approve(session, actor, user_id, list(body.roles), now=clock())


@router.post("/admin/users/{user_id}/reject", tags=["admin-users"], **guard(P.USER_MANAGE))
def reject_user(
    user_id: UUID, body: RejectRequest, user: CurrentUser, factory: Sessions
) -> UserAdminView:
    with transaction(factory) as session:
        actor = admin_users.get_actor(session, user.user_id)
        return admin_users.reject(session, actor, user_id, body.reason)


@router.put("/admin/users/{user_id}/roles", tags=["admin-users"], **guard(P.USER_MANAGE))
def update_user_roles(
    user_id: UUID, body: RolesUpdate, user: CurrentUser, factory: Sessions
) -> UserAdminView:
    with transaction(factory) as session:
        actor = admin_users.get_actor(session, user.user_id)
        return admin_users.update_roles(session, actor, user_id, list(body.roles))


@router.post("/admin/users/{user_id}/disable", tags=["admin-users"], **guard(P.USER_MANAGE))
def disable_user(user_id: UUID, user: CurrentUser, factory: Sessions, clock: Now) -> UserAdminView:
    with transaction(factory) as session:
        actor = admin_users.get_actor(session, user.user_id)
        return admin_users.disable(session, actor, user_id, now=clock())


@router.post("/admin/users/{user_id}/enable", tags=["admin-users"], **guard(P.USER_MANAGE))
def enable_user(user_id: UUID, user: CurrentUser, factory: Sessions) -> UserAdminView:
    with transaction(factory) as session:
        actor = admin_users.get_actor(session, user.user_id)
        return admin_users.enable(session, actor, user_id)


@router.post(
    "/admin/users/{user_id}/reset-link",
    tags=["admin-users"],
    **guard(P.USER_MANAGE),
)
def create_reset_link(
    user_id: UUID, user: CurrentUser, factory: Sessions, clock: Now
) -> PasswordResetLink:
    with transaction(factory) as session:
        actor = admin_users.get_actor(session, user.user_id)
        return admin_users.create_reset_link(session, actor, user_id, now=clock())


# ---------------------------------------------------------------- Phase 5: đọc tài nguyên

NOT_FOUND_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Không tồn tại"}
}


@router.get("/models", tags=["models"], **guard(P.MODEL_READ))
def list_models(factory: Sessions) -> list[ModelSummary]:
    with transaction(factory) as session:
        return catalog.list_models(session)


@router.get(
    "/models/{model_id}", tags=["models"], responses=NOT_FOUND_RESPONSE, **guard(P.MODEL_READ)
)
def get_model(model_id: UUID, factory: Sessions) -> ModelSummary:
    with transaction(factory) as session:
        return catalog.get_model(session, model_id)


@router.get("/datasets", tags=["datasets"], **guard(P.DATASET_READ))
def list_datasets(factory: Sessions) -> list[DatasetSummary]:
    with transaction(factory) as session:
        return catalog.list_datasets(session)


@router.get(
    "/dataset-versions/{dataset_version_id}",
    tags=["datasets"],
    responses=NOT_FOUND_RESPONSE,
    **guard(P.DATASET_READ),
)
def get_dataset_version(dataset_version_id: UUID, factory: Sessions) -> DatasetVersionSummary:
    with transaction(factory) as session:
        return catalog.get_dataset_version(session, dataset_version_id)


@router.get("/slices", tags=["slices"], **guard(P.DATASET_READ))
def list_slices(
    factory: Sessions,
    dataset_version: UUID | None = None,
    disjoint_from: Annotated[
        UUID | None,
        Query(description="Chỉ slice không có ảnh chung với slice này (slice huấn luyện, Phase 6)"),
    ] = None,
) -> list[SliceSummary]:
    with transaction(factory) as session:
        return catalog.list_slices(session, dataset_version, disjoint_from)


@router.get("/class-mappings", tags=["datasets"], **guard(P.DATASET_READ))
def list_class_mappings(
    factory: Sessions, dataset_version: UUID | None = None, model: UUID | None = None
) -> list[ClassMappingSummary]:
    with transaction(factory) as session:
        return catalog.list_class_mappings(session, dataset_version, model)


@router.get("/attack-specs", tags=["attack-specs"], **guard(P.ATTACK_CATALOG_READ))
def list_attack_specs(factory: Sessions) -> list[AttackSpecView]:
    """Chỉ spec đang hoạt động, kèm metadata (Phase R2)."""
    with transaction(factory) as session:
        return catalog.list_attack_specs(session)


@router.get("/admin/attack-specs", tags=["admin-attacks"], **guard(P.ATTACK_CATALOG_MANAGE))
def list_attack_specs_admin(
    factory: Sessions, cursor: Cursor = None, limit: Limit = 50
) -> AttackSpecAdminPage:
    """Mọi spec, mọi version, kể cả spec đã tắt (Phase 6, trang `/admin/attacks`)."""
    with transaction(factory) as session:
        return catalog.list_attack_specs_admin(session, cursor, limit)


@router.get("/protocols", tags=["protocols"], **guard(P.PROTOCOL_READ))
def list_protocols(factory: Sessions, include_retired: bool = False) -> list[ProtocolSummary]:
    """Protocol trạng thái `active` và `dev`; `include_retired=true` thêm `retired` (trang
    `/protocols` của reviewer, Phase 8)."""
    with transaction(factory) as session:
        return catalog.list_protocols(session, include_retired=include_retired)


# Phase 8 Group 0: khung (501) cho protocol, gửi duyệt, review, report và xác minh; Group 1-3
# cài đặt (requirements.md Phase 8, Behaviour).
PHASE8_RESPONSES: dict[int | str, dict[str, Any]] = NOT_IMPLEMENTED_RESPONSE | {
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Không tìm thấy"},
    status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "Sai trạng thái"},
}


@router.get(
    "/protocols/{protocol_id}",
    tags=["protocols"],
    responses=PHASE8_RESPONSES,
    **guard(P.PROTOCOL_READ),
)
def get_protocol(protocol_id: UUID, factory: Sessions) -> ProtocolView:
    with transaction(factory) as session:
        return protocol_service.get(session, protocol_id)


@router.post(
    "/protocols",
    tags=["protocols"],
    status_code=status.HTTP_201_CREATED,
    responses=PHASE8_RESPONSES,
    **guard(P.PROTOCOL_MANAGE),
)
def create_protocol(body: ProtocolCreate, user: CurrentUser, factory: Sessions) -> ProtocolView:
    """Tạo protocol `active` version 1 (422 khi attack spec không có, `spec_sha256` không khớp,
    patch ở chế độ tìm ngưỡng, hoặc vượt `MAX_RUNS`)."""
    # 409 khi đã có protocol cùng tên (dùng tạo version mới).
    with transaction(factory) as session:
        return protocol_service.create(session, actor=_actor(session, user), body=body)


@router.post(
    "/protocols/{protocol_id}/versions",
    tags=["protocols"],
    status_code=status.HTTP_201_CREATED,
    responses=PHASE8_RESPONSES,
    **guard(P.PROTOCOL_MANAGE),
)
def create_protocol_version(
    protocol_id: UUID, body: ProtocolVersionCreate, user: CurrentUser, factory: Sessions
) -> ProtocolView:
    """Version mới cùng `name` từ version mới nhất (409 nếu không phải); version cũ chuyển
    `retired` trong cùng giao dịch."""
    with transaction(factory) as session:
        return protocol_service.create_version(
            session, actor=_actor(session, user), protocol_id=protocol_id, body=body
        )


@router.post(
    "/protocols/{protocol_id}/retire",
    tags=["protocols"],
    responses=PHASE8_RESPONSES,
    **guard(P.PROTOCOL_MANAGE),
)
def retire_protocol(protocol_id: UUID, user: CurrentUser, factory: Sessions) -> ProtocolView:
    """`active` → `retired` (409 với trạng thái khác)."""
    with transaction(factory) as session:
        return protocol_service.retire(
            session, actor=_actor(session, user), protocol_id=protocol_id
        )


@router.get("/compute-targets", tags=["compute-targets"], **guard(P.COMPUTE_TARGET_READ))
def list_compute_targets(factory: Sessions, clock: Now) -> list[ComputeTargetPublic]:
    """`online`: heartbeat trong 60 giây gần nhất; `queue_length`: số experiment `queued`."""
    with transaction(factory) as session:
        return catalog.list_compute_targets(session, clock())


# ---------------------------------------------------------------- Phase 5: experiment

Artifacts = Annotated[ArtifactReader, Depends(get_artifact_reader)]


def get_report_stores() -> report_service.Stores:
    """Bucket artifacts (manifest, thumbnail) và reports (Phase 8); kết nối mở khi dùng."""
    return report_service.Stores(
        read_artifact=lambda key: get_storage().buckets.artifacts.get(key),
        put=lambda key, data: get_storage().buckets.reports.put(key, data),
        get=lambda key: get_storage().buckets.reports.get(key),
    )


ReportStores = Annotated[report_service.Stores, Depends(get_report_stores)]


def _actor(session: Session, user: Principal) -> m.User:
    actor = session.get(m.User, user.user_id)
    assert actor is not None  # current_user vừa đọc user này
    return actor


CONFLICT_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "Sai trạng thái"}
}


@router.get("/experiments", tags=["experiments"], **guard(P.EXPERIMENT_READ))
def list_experiments(
    user: CurrentUser,
    factory: Sessions,
    owner: Literal["me", "all"] = "all",
    status: ExperimentStatus | None = None,
    model: UUID | None = None,
    cursor: Cursor = None,
    limit: Limit = 50,
    mode: ExperimentMode | None = None,
) -> ExperimentPage:
    """Mới nhất trước; `owner=me` chỉ experiment của mình; `mode` lọc Khám phá/Chính thức
    (Phase R2)."""
    if mode is not None:
        not_implemented()  # Phase R2 Group 1
    with transaction(factory) as session:
        return experiment_views.list_experiments(
            session,
            viewer_id=user.user_id,
            owner=owner,
            status=status,
            model_version_id=model,
            cursor=cursor,
            limit=limit,
        )


@router.post(
    "/experiments",
    tags=["experiments"],
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "queue_limit_reached"}
    },
    **guard(P.EXPERIMENT_CREATE),
)
def create_experiment(
    body: ExperimentCreate, user: CurrentUser, factory: Sessions, clock: Now
) -> ExperimentDetail:
    """Kiểm tra cấu hình (422 có đường dẫn trường), tối đa 3 experiment đang chờ mỗi người
    (409 `queue_limit_reached`); tạo experiment `queued` và danh sách run."""
    with transaction(factory) as session:
        actor = _actor(session, user)
        experiment = experiments.create_from_body(session, actor=actor, body=body, clock=clock)
        return experiment_views.detail(session, experiment.id)


@router.post("/experiments/estimate", tags=["experiments"], **guard(P.EXPERIMENT_CREATE))
def estimate_experiment(body: ExperimentCreate, factory: Sessions) -> EstimateResponse:
    """Kiểm tra cấu hình như khi tạo; không tạo gì."""
    with transaction(factory) as session:
        checked = experiment_config.check(session, body, enforce_compliance=False)
        return estimate.estimate_config(session, checked)


@router.get(
    "/experiments/{experiment_id}",
    tags=["experiments"],
    responses=NOT_FOUND_RESPONSE,
    **guard(P.EXPERIMENT_READ),
)
def get_experiment(experiment_id: UUID, factory: Sessions) -> ExperimentDetail:
    with transaction(factory) as session:
        return experiment_views.detail(session, experiment_id)


@router.get(
    "/experiments/{experiment_id}/runs",
    tags=["experiments"],
    responses=NOT_FOUND_RESPONSE,
    **guard(P.EXPERIMENT_READ),
)
def list_experiment_runs(experiment_id: UUID, factory: Sessions) -> list[RunView]:
    with transaction(factory) as session:
        return experiment_views.list_runs(session, experiment_id)


@router.post(
    "/experiments/{experiment_id}/cancel",
    tags=["experiments"],
    responses=NOT_FOUND_RESPONSE | CONFLICT_RESPONSE,
    **guard(P.EXPERIMENT_CANCEL_OWN),
)
def cancel_experiment(
    experiment_id: UUID, user: CurrentUser, factory: Sessions, clock: Now
) -> ExperimentDetail:
    """Chỉ chủ sở hữu (403 với người khác); trạng thái `queued` hoặc `running` (409 nếu khác)."""
    with transaction(factory) as session:
        actor = _actor(session, user)
        experiments.cancel(
            session, actor=actor, experiment_id=experiment_id, owner_only=True, clock=clock
        )
        return experiment_views.detail(session, experiment_id)


@router.get(
    "/experiments/{experiment_id}/clone",
    tags=["experiments"],
    responses=NOT_FOUND_RESPONSE,
    **guard(P.EXPERIMENT_CREATE),
)
def clone_experiment(experiment_id: UUID, factory: Sessions) -> ExperimentClone:
    with transaction(factory) as session:
        return experiment_views.clone(session, experiment_id)


@router.post(
    "/experiments/{experiment_id}/submit",
    tags=["experiments"],
    responses=PHASE8_RESPONSES,
    **guard(P.EXPERIMENT_SUBMIT_REVIEW),
)
def submit_experiment(
    experiment_id: UUID, body: SubmitForReview, user: CurrentUser, factory: Sessions, clock: Now
) -> ExperimentDetail:
    """Chỉ chủ sở hữu (403); điều kiện sai → 409, thiếu giải trình → 422; khóa experiment."""
    with transaction(factory) as session:
        review_service.submit(
            session,
            actor=_actor(session, user),
            experiment_id=experiment_id,
            body=body,
            now=clock(),
        )
        return experiment_views.detail(session, experiment_id)


@router.get(
    "/experiments/{experiment_id}/comments",
    tags=["experiments"],
    responses=PHASE8_RESPONSES,
    **guard(P.EXPERIMENT_READ),
)
def list_comments(experiment_id: UUID, factory: Sessions) -> list[ReviewComment]:
    """Cũ nhất trước."""
    with transaction(factory) as session:
        return review_service.list_comments(session, experiment_id)


@router.post(
    "/experiments/{experiment_id}/comments",
    tags=["experiments"],
    status_code=status.HTTP_201_CREATED,
    responses=PHASE8_RESPONSES,
    **guard(P.REVIEW_COMMENT),
)
def add_comment(
    experiment_id: UUID, body: ReviewCommentCreate, user: CurrentUser, factory: Sessions
) -> ReviewComment:
    """Chỉ khi `submitted_for_review` hoặc `in_review` (409); chỉ thêm, không sửa, không xóa."""
    with transaction(factory) as session:
        return review_service.add_comment(
            session, actor=_actor(session, user), experiment_id=experiment_id, body=body
        )


@router.get(
    "/runs/{run_id}", tags=["runs"], responses=NOT_FOUND_RESPONSE, **guard(P.EXPERIMENT_READ)
)
def get_run(run_id: UUID, factory: Sessions) -> RunView:
    with transaction(factory) as session:
        return experiment_views.get_run(session, run_id)


@router.get(
    "/runs/{run_id}/manifest",
    tags=["runs"],
    responses=NOT_FOUND_RESPONSE,
    **guard(P.EXPERIMENT_READ),
)
def get_run_manifest(run_id: UUID, factory: Sessions, read: Artifacts) -> Manifest:
    with transaction(factory) as session:
        return experiment_views.manifest(session, read, run_id)


@router.get(
    "/runs/{run_id}/failure-cases",
    tags=["runs"],
    responses=NOT_FOUND_RESPONSE,
    **guard(P.EXPERIMENT_READ),
)
def list_run_failure_cases(run_id: UUID, factory: Sessions, clock: Now) -> list[FailureCaseView]:
    """Sắp theo `severity_score` giảm dần; chỉ có URL thumbnail."""
    with transaction(factory) as session:
        return artifacts.list_cases(session, run_id, clock())


@router.get(
    "/failure-cases/{case_id}",
    tags=["failure-cases"],
    responses=NOT_FOUND_RESPONSE,
    **guard(P.EXPERIMENT_READ),
)
def get_failure_case(case_id: UUID, factory: Sessions, clock: Now) -> FailureCaseView:
    with transaction(factory) as session:
        return artifacts.get_case(session, case_id, clock())


@router.get(
    "/failure-cases/{case_id}/verdicts",
    tags=["failure-cases"],
    responses=PHASE8_RESPONSES,
    **guard(P.EXPERIMENT_READ),
)
def list_case_verdicts(case_id: UUID, factory: Sessions) -> list[CaseVerdictView]:
    """Mọi version, mới nhất trước."""
    with transaction(factory) as session:
        return review_service.list_verdicts(session, case_id)


@router.get(
    "/artifacts/{token}",
    tags=["artifacts"],
    response_class=Response,
    responses={
        status.HTTP_200_OK: {
            "content": {"image/png": {}, "image/webp": {}},
            "description": "Ảnh của đúng đối tượng gắn với token",
        },
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Token sai, bị sửa hoặc hết hạn (10 phút)",
        },
    },
    **guard(P.EXPERIMENT_READ),
)
def get_artifact(token: str, read: Artifacts, clock: Now) -> Response:
    """Ảnh từ MinIO. Cần cả phiên có `experiment.read` lẫn token do API cấp trong
    `FailureCaseView.urls`; token sai, bị sửa hoặc hết hạn → 404 (không phân biệt)."""
    key = artifacts.verify(token, clock())
    if key is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Không tìm thấy ảnh")
    try:
        data = read(key)
    except KeyNotFoundError as exc:
        raise ApiError(
            status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Không tìm thấy ảnh"
        ) from exc
    # Ảnh riêng tư, URL hết hạn sau 10 phút: trình duyệt cache riêng, không qua cache dùng chung.
    return Response(
        content=data,
        media_type=artifacts.media_type(key),
        headers={"Cache-Control": "private, max-age=600"},
    )


@router.get("/reviews", tags=["reviews"], **guard(P.REVIEW_DECIDE))
def list_reviews(
    user: CurrentUser,
    factory: Sessions,
    status: ReviewQueueFilter = ReviewQueueFilter.WAITING,
    sort: Literal["submitted_at", "max_drop"] = "submitted_at",
) -> list[ReviewQueueItem]:
    """Hàng đợi review, loại experiment do người gọi tạo. `submitted_at`: cũ nhất trước;
    `max_drop`: `max_relative_drop` giảm dần, null xếp cuối."""
    with transaction(factory) as session:
        return review_service.queue(session, actor=_actor(session, user), status=status, sort=sort)


@router.post(
    "/reviews/{experiment_id}/claim",
    tags=["reviews"],
    responses=PHASE8_RESPONSES,
    **guard(P.REVIEW_DECIDE),
)
def claim_review(
    experiment_id: UUID, user: CurrentUser, factory: Sessions, clock: Now
) -> ExperimentDetail:
    """`submitted_for_review` → `in_review` (409 với trạng thái khác); người tạo → 403."""
    with transaction(factory) as session:
        review_service.claim(
            session, actor=_actor(session, user), experiment_id=experiment_id, now=clock()
        )
        return experiment_views.detail(session, experiment_id)


@router.post(
    "/reviews/{experiment_id}/release",
    tags=["reviews"],
    responses=PHASE8_RESPONSES,
    **guard(P.REVIEW_DECIDE),
)
def release_review(experiment_id: UUID, user: CurrentUser, factory: Sessions) -> ExperimentDetail:
    """Chỉ người đang nhận (403); trở về `submitted_for_review`."""
    with transaction(factory) as session:
        review_service.release(session, actor=_actor(session, user), experiment_id=experiment_id)
        return experiment_views.detail(session, experiment_id)


@router.post(
    "/reviews/{experiment_id}/decision",
    tags=["reviews"],
    responses=PHASE8_RESPONSES,
    **guard(P.REVIEW_DECIDE),
)
def decide_review(
    experiment_id: UUID,
    body: ReviewDecisionInput,
    user: CurrentUser,
    factory: Sessions,
    clock: Now,
    stores: ReportStores,
    background: BackgroundTasks,
) -> ExperimentDetail:
    """Thứ tự kiểm tra: không phải người đang nhận → 403; thiếu trường nhập → 422; checklist
    chưa đủ → 409 `checklist_incomplete` kèm `checklist`."""
    with transaction(factory) as session:
        actor = _actor(session, user)
        review_service.decide(
            session, actor=actor, experiment_id=experiment_id, body=body, now=clock()
        )
        report_id = None
        if body.decision == ReviewDecision.APPROVE:
            # Phase 8 Group 3: report sinh ở tác vụ nền sau khi giao dịch này commit.
            experiment = session.get(m.Experiment, experiment_id)
            assert experiment is not None
            report_id = report_service.create_pending(session, experiment, actor.id).id
        detail = experiment_views.detail(session, experiment_id)
    if report_id is not None:
        background.add_task(report_service.generate, factory, stores, report_id, clock)
    return detail


@router.post(
    "/reviews/{experiment_id}/cases/{case_id}/verdicts",
    tags=["reviews"],
    status_code=status.HTTP_201_CREATED,
    responses=PHASE8_RESPONSES,
    **guard(P.REVIEW_DECIDE),
)
def add_case_verdict(
    experiment_id: UUID,
    case_id: UUID,
    body: CaseVerdictInput,
    user: CurrentUser,
    factory: Sessions,
) -> CaseVerdictView:
    """Chỉ người đang nhận review (403); case phải thuộc experiment (404); tạo version mới.
    Đặt dưới `/reviews` vì API người dùng không có endpoint ghi dưới `/failure-cases`
    (test kiến trúc Phase 3)."""
    with transaction(factory) as session:
        return review_service.add_verdict(
            session,
            actor=_actor(session, user),
            experiment_id=experiment_id,
            case_id=case_id,
            body=body,
        )


@router.get("/reports", tags=["reports"], **guard(P.REPORT_READ))
def list_reports(factory: Sessions) -> list[ReportView]:
    """Mới nhất trước."""
    with transaction(factory) as session:
        return report_service.list_reports(session)


REPORT_FILE_RESPONSES: dict[int | str, dict[str, Any]] = NOT_IMPLEMENTED_RESPONSE | {
    status.HTTP_200_OK: {
        "content": {"application/pdf": {}, "application/json": {}},
        "description": "Đúng file report đã lưu",
    },
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "Token sai, bị sửa hoặc hết hạn",
    },
}


@router.get(
    "/reports/files/{token}",
    tags=["reports"],
    response_class=Response,
    responses=REPORT_FILE_RESPONSES,
    **guard(P.REPORT_EXPORT),
)
def get_report_file(token: str, stores: ReportStores, clock: Now) -> Response:
    """File PDF hoặc JSON theo token do `/reports/{id}/download` cấp."""
    data, media_type, filename = report_service.read_file(stores, token, clock())
    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get(
    "/reports/{report_id}",
    tags=["reports"],
    responses=PHASE8_RESPONSES,
    **guard(P.REPORT_READ),
)
def get_report(report_id: UUID, factory: Sessions, stores: ReportStores) -> ReportDetail:
    with transaction(factory) as session:
        return report_service.detail(session, stores, report_id)


@router.get(
    "/reports/{report_id}/download",
    tags=["reports"],
    responses=PHASE8_RESPONSES,
    **guard(P.REPORT_EXPORT),
)
def download_report(
    report_id: UUID,
    format: Literal["pdf", "json"],
    user: CurrentUser,
    factory: Sessions,
    clock: Now,
) -> ReportDownload:
    """URL tạm thời tới file đã lưu (409 khi report chưa `ready`); ghi `report.downloaded`."""
    with transaction(factory) as session:
        return report_service.download(
            session, actor=_actor(session, user), report_id=report_id, fmt=format, now=clock()
        )


@router.post(
    "/reports/{report_id}/regenerate",
    tags=["reports"],
    responses=PHASE8_RESPONSES,
    **guard(P.REPORT_EXPORT),
)
def regenerate_report(
    report_id: UUID,
    factory: Sessions,
    stores: ReportStores,
    clock: Now,
    background: BackgroundTasks,
) -> ReportView:
    """Chỉ khi `failed` (409 nếu khác); giữ nguyên `report_id`."""
    with transaction(factory) as session:
        view = report_service.regenerate(session, report_id)
    background.add_task(report_service.generate, factory, stores, report_id, clock)
    return view


@router.get("/budget", tags=["budget"], **guard(P.BUDGET_MANAGE))
def get_budget() -> None:
    not_implemented()


@router.get("/audit-log", tags=["audit-log"], **guard(P.AUDIT_READ))
def list_audit_log(
    factory: Sessions,
    actor_id: UUID | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    since: Annotated[datetime | None, Query(description="Từ thời điểm (UTC, gồm)")] = None,
    until: Annotated[datetime | None, Query(description="Tới thời điểm (UTC, không gồm)")] = None,
    cursor: Cursor = None,
    limit: Limit = 50,
) -> AuditLogPage:
    filters = AuditFilter(actor_id, action, entity_type, entity_id, since, until)
    with transaction(factory) as session:
        return list_entries(session, filters, cursor=cursor, limit=limit)


# Phase R2 Group 0: khung (501) cho insight, template, preset, catalog và model qua cấu hình, thử
# nhanh; Group 1 và Group 4 cài đặt (requirements.md Phase R2, Behaviour).
R2_RESPONSES: dict[int | str, dict[str, Any]] = NOT_IMPLEMENTED_RESPONSE | {
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Không tìm thấy"},
    status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "Sai trạng thái hoặc trùng"},
}


@router.get(
    "/experiments/{experiment_id}/insight",
    tags=["experiments"],
    responses=R2_RESPONSES,
    **guard(P.EXPERIMENT_READ),
)
def get_insight(experiment_id: UUID) -> ExperimentInsight:
    """Điểm yếu chính, ma trận độ bền và câu kết luận từ các run đã có metric."""
    not_implemented()


@router.post(
    "/experiments/{experiment_id}/promote",
    tags=["experiments"],
    responses=R2_RESPONSES,
    **guard(P.EXPERIMENT_CREATE),
)
def promote_experiment(experiment_id: UUID, body: PromoteRequest) -> ExperimentClone:
    """Bản nháp Chính thức từ experiment Khám phá đã kết thúc; không tạo experiment (409 khi
    nguồn không phải exploration, chưa kết thúc, hoặc protocol đích không active)."""
    not_implemented()


@router.post(
    "/experiments/draft", tags=["experiments"], responses=R2_RESPONSES, **guard(P.EXPERIMENT_CREATE)
)
def draft_experiment(body: ExperimentDraftRequest) -> ExperimentClone:
    """Dựng `ExperimentCreate` từ protocol và preset; không tạo experiment."""
    not_implemented()


@router.get("/experiment-presets", tags=["experiments"], **guard(P.EXPERIMENT_READ))
def list_experiment_presets() -> list[ExperimentPreset]:
    """Preset trong `contracts/seeds/experiment_presets.json`."""
    not_implemented()


@router.get("/protocol-templates", tags=["protocols"], **guard(P.PROTOCOL_READ))
def list_protocol_templates() -> list[ProtocolTemplate]:
    """Template trong `contracts/seeds/protocol_templates.json`."""
    not_implemented()


@router.get(
    "/protocol-templates/{key}/draft",
    tags=["protocols"],
    responses=R2_RESPONSES,
    **guard(P.PROTOCOL_MANAGE),
)
def draft_protocol(key: str) -> ProtocolCreate:
    """`ProtocolCreate` điền sẵn spec active, level và tiêu chí gợi ý; không tạo protocol."""
    not_implemented()


@router.get("/attack-adapters", tags=["admin-attacks"], **guard(P.ATTACK_CATALOG_MANAGE))
def list_attack_adapters() -> list[AttackAdapterInfo]:
    """Adapter có trong registry của worker."""
    not_implemented()


@router.post(
    "/admin/attack-specs",
    tags=["admin-attacks"],
    status_code=status.HTTP_201_CREATED,
    responses=R2_RESPONSES,
    **guard(P.ATTACK_CATALOG_MANAGE),
)
def create_attack_spec(body: AttackSpecCreate) -> AttackSpecAdminView:
    """Spec mới (`draft` rồi `checking`); 422 khi adapter lạ, `fixed_params` sai hoặc version nhảy
    cóc; 409 khi trùng `spec_sha256`."""
    not_implemented()


@router.post(
    "/admin/attack-specs/{spec_id}/check",
    tags=["admin-attacks"],
    responses=R2_RESPONSES,
    **guard(P.ATTACK_CATALOG_MANAGE),
)
def recheck_attack_spec(spec_id: UUID) -> AttackSpecAdminView:
    """Chạy lại tự kiểm tra từ `check_failed` (409 với trạng thái khác)."""
    not_implemented()


@router.patch(
    "/admin/attack-specs/{spec_id}/metadata",
    tags=["admin-attacks"],
    responses=R2_RESPONSES,
    **guard(P.ATTACK_CATALOG_MANAGE),
)
def update_attack_spec_metadata(spec_id: UUID, body: AttackSpecMetadata) -> AttackSpecAdminView:
    """Sửa metadata, không đổi `spec_sha256` hay version; ghi audit log."""
    not_implemented()


@router.get("/attack-specs/pending", tags=["attack-specs"], **guard(P.ATTACK_CATALOG_APPROVE))
def list_pending_attack_specs() -> list[AttackSpecAdminView]:
    """Spec `pending_approval` chờ reviewer duyệt."""
    not_implemented()


@router.post(
    "/attack-specs/{spec_id}/approve",
    tags=["attack-specs"],
    responses=R2_RESPONSES,
    **guard(P.ATTACK_CATALOG_APPROVE),
)
def approve_attack_spec(spec_id: UUID) -> AttackSpecAdminView:
    """`pending_approval` → `active`; version cũ cùng name chuyển `retired`; người duyệt khác
    người tạo (403)."""
    not_implemented()


@router.post(
    "/attack-specs/{spec_id}/reject",
    tags=["attack-specs"],
    responses=R2_RESPONSES,
    **guard(P.ATTACK_CATALOG_APPROVE),
)
def reject_attack_spec(spec_id: UUID, body: AttackSpecReject) -> AttackSpecAdminView:
    """`pending_approval` → `draft`."""
    not_implemented()


@router.post("/models/uploads", tags=["models"], responses=R2_RESPONSES, **guard(P.MODEL_MANAGE))
def create_model_upload(body: ModelUploadCreate) -> ModelUpload:
    """Presigned PUT cho `.onnx` hoặc `.safetensors` tối đa 500 MB."""
    not_implemented()


@router.post(
    "/models",
    tags=["models"],
    status_code=status.HTTP_201_CREATED,
    responses=R2_RESPONSES,
    **guard(P.MODEL_MANAGE),
)
def register_model(body: ModelRegister) -> ModelSummary:
    """Model version `checking` (409 khi trùng sha256; 422 khi nội dung không phải safetensors
    hoặc onnx); xếp job model_check."""
    not_implemented()


QUICK_TRY_RESPONSES: dict[int | str, dict[str, Any]] = R2_RESPONSES | {
    status.HTTP_410_GONE: {"model": ErrorResponse, "description": "gone: đã hết hạn"},
    status.HTTP_429_TOO_MANY_REQUESTS: {
        "model": ErrorResponse,
        "description": "quick_try_busy: đã có một lượt queued/running",
    },
}


@router.post(
    "/quick-tries",
    tags=["quick-tries"],
    status_code=status.HTTP_202_ACCEPTED,
    responses=QUICK_TRY_RESPONSES,
    **guard(P.QUICK_TRY_USE),
)
def create_quick_try(
    model_version_id: Annotated[UUID, Form()],
    attack_spec_id: Annotated[UUID, Form()],
    image: Annotated[UploadFile, File(description="JPEG/PNG ≤ 10 MB, cạnh dài ≤ 4096 px")],
    preset: Annotated[PresetKey, Form()] = "standard",
) -> QuickTryView:
    """Thử nhanh một ảnh: không tạo experiment, kết quả giữ 24 giờ. Field form là các trường của
    `QuickTryCreate`, khai riêng vì form model `extra="forbid"` coi file là field thừa."""
    not_implemented()


@router.get(
    "/quick-tries/{quick_try_id}",
    tags=["quick-tries"],
    responses=QUICK_TRY_RESPONSES,
    **guard(P.QUICK_TRY_USE),
)
def get_quick_try(quick_try_id: UUID) -> QuickTryView:
    """Chỉ người tạo; hết hạn trả 410."""
    not_implemented()


# Trang xác minh report công khai, không cần đăng nhập.
verify_router = APIRouter(responses=NOT_IMPLEMENTED_RESPONSE | VALIDATION_ERROR_RESPONSE)


@verify_router.get(
    "/verify/{report_id}",
    tags=["verify"],
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Không có"}},
)
def verify_report(report_id: UUID, factory: Sessions) -> VerifyInfo:
    """Chỉ report `ready`; report không có hoặc chưa `ready` → 404."""
    with transaction(factory) as session:
        return report_service.verify_info(session, report_id)
