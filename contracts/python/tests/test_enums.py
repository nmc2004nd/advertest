import pytest

from advertest_contracts import enums

# Bảng "Enum dùng chung" trong specs/2026-09-27-phase-00-contracts-skeleton/requirements.md
EXPECTED = {
    "Role": {"engineer", "reviewer", "admin"},
    "UserStatus": {"pending", "active", "rejected", "disabled"},
    "RunStatus": {
        "queued",
        "running",
        "completed",
        "failed",
        "skipped",
        "stopped_limit",
        "cancelled",
    },
    "ExperimentStatus": {
        "draft",
        "queued",
        "running",
        "completed",
        "submitted_for_review",
        "in_review",
        "approved",
        "changes_requested",
        "rejected",
        "cancelled",
    },
    "SearchStatus": {"found", "not_reached", "below_min", "stopped_limit", "non_monotonic"},
    "StopReason": {"budget", "time"},
    "SkipReason": {"cached", "incompatible"},
    "ComputeKind": {"local", "rented"},
    "BillingMode": {"none", "hourly"},
    "LimitKind": {"budget", "time"},
    "AttackKind": {"attack", "corruption", "occlusion"},
    "AttackAccess": {"white_box", "black_box"},
    "RunMode": {"grid", "search"},
    "ThresholdKind": {"relative_drop", "absolute_drop", "attack_success_rate"},
    "ReviewDecision": {"approve", "changes_requested", "reject"},
    "CaseSeverity": {"critical", "major", "minor", "acceptable"},
    # Đề xuất contract 001; Phase 3 thêm mã cho API worker; Phase 4 thêm mã xác thực, phân quyền.
    "ErrorCode": {
        "not_implemented",
        "unauthenticated",
        "forbidden",
        "not_found",
        "conflict",
        "invalid_request",
        "invalid_credentials",
        "account_pending",
        "account_rejected",
        "account_disabled",
        "rate_limited",
        "csrf_failed",
        "validation_error",
    },
    # Phase 3: protocol phát triển dev-open.
    "ProtocolStatus": {"active", "retired", "dev"},
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_enum_values_match_spec(name: str) -> None:
    enum_cls = getattr(enums, name)
    assert {member.value for member in enum_cls} == EXPECTED[name]
