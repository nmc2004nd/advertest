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


class CaseSeverity(StrEnum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    ACCEPTABLE = "acceptable"
