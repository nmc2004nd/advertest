"""Enum dùng chung giữa ML core, backend, worker và frontend."""

from enum import StrEnum


class Role(StrEnum):
    ENGINEER = "engineer"
    REVIEWER = "reviewer"
    ADMIN = "admin"


class UserStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"
    DISABLED = "disabled"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    STOPPED_LIMIT = "stopped_limit"
    CANCELLED = "cancelled"


class ExperimentStatus(StrEnum):
    DRAFT = "draft"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    SUBMITTED_FOR_REVIEW = "submitted_for_review"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class SearchStatus(StrEnum):
    FOUND = "found"
    NOT_REACHED = "not_reached"
    BELOW_MIN = "below_min"
    STOPPED_LIMIT = "stopped_limit"
    NON_MONOTONIC = "non_monotonic"


class StopReason(StrEnum):
    BUDGET = "budget"
    TIME = "time"


class SkipReason(StrEnum):
    CACHED = "cached"
    INCOMPATIBLE = "incompatible"
    EARLY_STOP = "early_stop"  # Phase 6: level nhỏ hơn của cùng attack đã làm model sụp


class ComputeKind(StrEnum):
    LOCAL = "local"
    RENTED = "rented"


class BillingMode(StrEnum):
    NONE = "none"
    HOURLY = "hourly"


class LimitKind(StrEnum):
    BUDGET = "budget"
    TIME = "time"


class AttackKind(StrEnum):
    ATTACK = "attack"
    CORRUPTION = "corruption"
    OCCLUSION = "occlusion"


class AttackAccess(StrEnum):
    WHITE_BOX = "white_box"
    BLACK_BOX = "black_box"
    NOT_APPLICABLE = "not_applicable"  # Phase 6: corruption và occlusion (không phải kẻ tấn công)


class RunMode(StrEnum):
    GRID = "grid"
    SEARCH = "search"


class ThresholdKind(StrEnum):
    RELATIVE_DROP = "relative_drop"
    ABSOLUTE_DROP = "absolute_drop"
    ATTACK_SUCCESS_RATE = "attack_success_rate"


class ReviewDecision(StrEnum):
    APPROVE = "approve"
    CHANGES_REQUESTED = "changes_requested"
    REJECT = "reject"


class ErrorCode(StrEnum):
    # Phase 3 thêm các mã cho API nội bộ của worker (401, 403, 404, 409, 422).
    # Phase 4 thêm các mã của xác thực và phân quyền.
    NOT_IMPLEMENTED = "not_implemented"
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    INVALID_REQUEST = "invalid_request"  # 422: dữ liệu hợp lệ về cú pháp nhưng sai nghiệp vụ
    INVALID_CREDENTIALS = "invalid_credentials"  # 401: sai email hoặc mật khẩu
    ACCOUNT_PENDING = "account_pending"  # 403: đúng mật khẩu, tài khoản chờ duyệt
    ACCOUNT_REJECTED = "account_rejected"
    ACCOUNT_DISABLED = "account_disabled"
    RATE_LIMITED = "rate_limited"  # 429
    CSRF_FAILED = "csrf_failed"  # 403
    VALIDATION_ERROR = "validation_error"  # 422: body không đúng schema
    # Phase 5: experiment trên web; lỗi máy chủ không xử lý được.
    NOT_SUPPORTED_YET = "not_supported_yet"  # 422: tính năng chưa có ở phase này (mode = search)
    QUEUE_LIMIT_REACHED = "queue_limit_reached"  # 409: đã có 3 experiment đang chờ
    INTERNAL_ERROR = "internal_error"  # 500: không kèm chi tiết (chi tiết chỉ ghi log server)


class ProtocolStatus(StrEnum):
    ACTIVE = "active"
    RETIRED = "retired"
    DEV = "dev"  # Protocol phát triển (dev-open, Phase 3): không bao giờ được gửi duyệt.


class CaseSeverity(StrEnum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    ACCEPTABLE = "acceptable"


class DisplayMode(StrEnum):
    """Cách hiển thị ảnh failure case (Phase 5; Phase 6 thêm làm mờ theo từng case)."""

    NORMAL = "normal"  # dataset đã ẩn danh, hoặc case đã làm mờ (Phase 6): có URL ảnh
    HIDDEN_UNANONYMIZED = "hidden_unanonymized"  # dataset và case chưa làm mờ: không cấp URL ảnh
    DEV_UNBLURRED = "dev_unblurred"  # chưa làm mờ nhưng server bật DEV_ALLOW_UNBLURRED


class RunPhase(StrEnum):
    """Giai đoạn của run đang chạy (Phase 6): run patch train trước khi đánh giá."""

    TRAINING = "training"
    EVALUATING = "evaluating"


class PerturbationImageKind(StrEnum):
    """Nội dung ảnh thứ ba của failure case (Phase 6)."""

    AMPLIFIED_NOISE = "amplified_noise"  # nhiễu khuếch đại (FGSM, PGD)
    DIFFERENCE = "difference"  # vùng khác biệt |δ| (corruption, occlusion)
    PATCH_LOCATION = "patch_location"  # vị trí patch
