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
    "SearchStatus": {  # Phase 7: failed
        "found",
        "not_reached",
        "below_min",
        "stopped_limit",
        "non_monotonic",
        "failed",
    },
    "StopReason": {"budget", "time"},
    "SkipReason": {"cached", "incompatible", "early_stop"},  # Phase 6: early_stop
    "ComputeKind": {"local", "rented"},
    "BillingMode": {"none", "hourly"},
    "LimitKind": {"budget", "time"},
    "AttackKind": {"attack", "corruption", "occlusion"},
    "AttackAccess": {"white_box", "black_box", "not_applicable"},  # Phase 6: not_applicable
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
        # Phase 5.
        "not_supported_yet",
        "queue_limit_reached",
        "internal_error",
    },
    # Phase 3: protocol phát triển dev-open.
    "ProtocolStatus": {"active", "retired", "dev"},
    # Phase 5: cách hiển thị ảnh failure case.
    "DisplayMode": {"normal", "hidden_unanonymized", "dev_unblurred"},
    # Phase 6: giai đoạn của run patch, nội dung ảnh thứ ba của failure case.
    "RunPhase": {"training", "evaluating"},
    "PerturbationImageKind": {"amplified_noise", "difference", "patch_location"},
    # Phase 7: giai đoạn tìm ngưỡng, tập ảnh của run.
    "SearchStage": {"coarse", "bisect_subset", "confirm", "bisect_full", "done"},
    "EvalScope": {"full", "subset"},
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_enum_values_match_spec(name: str) -> None:
    enum_cls = getattr(enums, name)
    assert {member.value for member in enum_cls} == EXPECTED[name]
