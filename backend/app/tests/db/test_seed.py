"""Script seed: đủ attack spec, local-dev không tính phí, một admin active; chạy lại không trùng."""

from __future__ import annotations

import pytest
from argon2 import PasswordHasher
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from advertest_contracts.enums import BillingMode, Role, UserStatus
from backend.admin_cli.seed import AdminAccount, load_attack_specs, seed
from backend.app.db import models as m

pytestmark = pytest.mark.db

ADMIN = AdminAccount(email="admin@advertest.test", password="correct horse battery staple")


def test_seed_creates_expected_rows_and_is_idempotent(app_engine: Engine) -> None:
    seed(app_engine, ADMIN)
    seed(app_engine, AdminAccount(email=ADMIN.email, password="mật khẩu khác"))

    with Session(app_engine) as s:
        spec_hashes = set(s.scalars(select(m.AttackSpecRow.spec_sha256)))
        assert {spec.spec_sha256 for spec in load_attack_specs()} <= spec_hashes

        targets = s.scalars(select(m.ComputeTarget).where(m.ComputeTarget.name == "local-dev"))
        (target,) = targets.all()
        assert target.billing_mode == BillingMode.NONE

        admins = s.scalars(select(m.User).where(m.User.email == ADMIN.email)).all()
        assert len(admins) == 1
        admin = admins[0]
        assert admin.status == UserStatus.ACTIVE
        # Lần seed thứ hai không đổi mật khẩu đã có.
        assert PasswordHasher().verify(admin.password_hash, ADMIN.password)
        roles = set(s.scalars(select(m.UserRole.role).where(m.UserRole.user_id == admin.id)))
        assert roles == {Role.ADMIN}

        count = s.scalar(
            select(func.count())
            .select_from(m.AttackSpecRow)
            .where(m.AttackSpecRow.spec_sha256.in_([sp.spec_sha256 for sp in load_attack_specs()]))
        )
        assert count == len(load_attack_specs()) == 10  # Phase 6: 3 attack + 7 spec mới


def test_admin_from_env_requires_both_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADVERTEST_ADMIN_EMAIL", "Admin@Example.com")
    monkeypatch.delenv("ADVERTEST_ADMIN_PASSWORD", raising=False)
    with pytest.raises(RuntimeError):
        AdminAccount.from_env()
    monkeypatch.setenv("ADVERTEST_ADMIN_PASSWORD", "pw")
    assert AdminAccount.from_env().email == "admin@example.com"
