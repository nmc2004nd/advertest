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
    # Phase 4 thêm: invalid_credentials, account_pending, ...
    NOT_IMPLEMENTED = "not_implemented"
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    INVALID_REQUEST = "invalid_request"  # 422: dữ liệu hợp lệ về cú pháp nhưng sai nghiệp vụ


class ProtocolStatus(StrEnum):
    ACTIVE = "active"
    RETIRED = "retired"
    DEV = "dev"  # Protocol phát triển (dev-open, Phase 3): không bao giờ được gửi duyệt.


class CaseSeverity(StrEnum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    ACCEPTABLE = "acceptable"
