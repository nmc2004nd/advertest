import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from advertest_contracts.enums import Role, UserStatus
from advertest_contracts.models import (
    AccessRequest,
    ApproveRequest,
    AuditLogEntry,
    LoginRequest,
    Me,
    PasswordChange,
    RolesUpdate,
    UserAdminView,
)

MOCKS = Path(__file__).resolve().parents[2] / "mocks"


def _mock(schema: str, name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((MOCKS / schema / f"{name}.json").read_text())
    return data


def test_email_is_lowercased_and_trimmed() -> None:
    body = _mock("login_request", "default") | {"email": "  An.Nguyen@Example.COM "}
    assert LoginRequest.model_validate(body).email == "an.nguyen@example.com"


@pytest.mark.parametrize("email", ["", "khong-co-a-cong", "a@b", "a b@c.com"])
def test_malformed_email_is_rejected(email: str) -> None:
    with pytest.raises(ValidationError):
        LoginRequest.model_validate({"email": email, "password": "x"})


def test_access_request_password_rules() -> None:
    body = _mock("access_request", "default")
    with pytest.raises(ValidationError):
        AccessRequest.model_validate(body | {"password": "ngan-9-kt"})
    with pytest.raises(ValidationError):
        AccessRequest.model_validate(body | {"password": body["email"].upper()})
    AccessRequest.model_validate(body | {"password": "1234567890"})


def test_new_password_minimum_length() -> None:
    with pytest.raises(ValidationError):
        PasswordChange.model_validate({"current_password": "x", "new_password": "123456789"})


@pytest.mark.parametrize("model", [ApproveRequest, RolesUpdate])
def test_roles_need_at_least_one_unique_role(model: type[ApproveRequest | RolesUpdate]) -> None:
    for roles in ([], ["engineer", "engineer"], ["superuser"]):
        with pytest.raises(ValidationError):
            model.model_validate({"roles": roles})
    model.model_validate({"roles": ["engineer", "admin"]})


def test_me_permissions_must_match_roles() -> None:
    body = _mock("me", "engineer")
    with pytest.raises(ValidationError):
        Me.model_validate(body | {"permissions": [*body["permissions"], "user.manage"]})


def test_me_mocks_cover_every_role_and_a_combination() -> None:
    mes = [Me.model_validate_json(p.read_text()) for p in (MOCKS / "me").glob("*.json")]
    single = {m.roles[0] for m in mes if len(m.roles) == 1}
    assert single == set(Role)
    assert any(len(m.roles) > 1 for m in mes)


def test_user_admin_view_mocks_cover_every_status() -> None:
    statuses = {
        UserAdminView.model_validate_json(p.read_text()).status
        for p in (MOCKS / "user_admin_view").glob("*.json")
    }
    assert statuses == set(UserStatus)


def test_audit_log_entry_actor_may_be_null_and_action_is_dotted() -> None:
    body = _mock("audit_log_entry", "system")
    assert AuditLogEntry.model_validate(body).actor is None
    with pytest.raises(ValidationError):
        AuditLogEntry.model_validate(body | {"action": "approved"})
