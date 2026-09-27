"""Nạp dữ liệu khởi đầu: attack catalog, compute target `local-dev`, tài khoản admin.

Chạy bằng role advertest_app:
    DATABASE_URL=... ADVERTEST_ADMIN_EMAIL=... ADVERTEST_ADMIN_PASSWORD=... \\
        python -m backend.admin_cli.seed

Chạy lại nhiều lần không tạo bản ghi trùng và không đổi mật khẩu admin đã có.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from argon2 import PasswordHasher
from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from advertest_contracts.enums import BillingMode, ComputeKind, Role, UserStatus
from advertest_contracts.models import AttackSpec
from backend.app.db import models as m
from backend.app.db.engine import make_engine

SEED_FILE = Path(__file__).resolve().parents[2] / "contracts" / "seeds" / "attack_specs.json"
LOCAL_TARGET = "local-dev"


@dataclass(frozen=True)
class AdminAccount:
    email: str
    password: str
    full_name: str = "Administrator"

    @classmethod
    def from_env(cls) -> AdminAccount:
        email = os.environ.get("ADVERTEST_ADMIN_EMAIL", "").strip()
        password = os.environ.get("ADVERTEST_ADMIN_PASSWORD", "")
        if not email or not password:
            raise RuntimeError("Cần ADVERTEST_ADMIN_EMAIL và ADVERTEST_ADMIN_PASSWORD")
        return cls(email=email.lower(), password=password)


def load_attack_specs(path: Path = SEED_FILE) -> list[AttackSpec]:
    return [AttackSpec.model_validate(item) for item in json.loads(path.read_text())]


def seed(engine: Engine, admin: AdminAccount) -> None:
    with Session(engine) as session, session.begin():
        _seed_attack_specs(session, load_attack_specs())
        _seed_local_target(session)
        _seed_admin(session, admin)


def _seed_attack_specs(session: Session, specs: list[AttackSpec]) -> None:
    for spec in specs:
        session.execute(
            insert(m.AttackSpecRow)
            .values(
                id=spec.id,
                name=spec.name,
                version=spec.version,
                kind=spec.kind,
                access=spec.access,
                spec=spec.model_dump(mode="json"),
                spec_sha256=spec.spec_sha256,
            )
            .on_conflict_do_nothing(index_elements=["spec_sha256"])
        )


def _seed_local_target(session: Session) -> None:
    session.execute(
        insert(m.ComputeTarget)
        .values(name=LOCAL_TARGET, kind=ComputeKind.LOCAL, billing_mode=BillingMode.NONE)
        .on_conflict_do_nothing(index_elements=["name"])
    )


def _seed_admin(session: Session, admin: AdminAccount) -> None:
    user = session.scalar(select(m.User).where(m.User.email == admin.email))
    if user is None:
        user = m.User(
            email=admin.email,
            full_name=admin.full_name,
            password_hash=PasswordHasher().hash(admin.password),
            status=UserStatus.ACTIVE,
        )
        session.add(user)
        session.flush()
    session.execute(
        insert(m.UserRole)
        .values(user_id=user.id, role=Role.ADMIN)
        .on_conflict_do_nothing(index_elements=["user_id", "role"])
    )


def main() -> None:
    seed(make_engine(), AdminAccount.from_env())
    print("Đã nạp attack catalog, compute target local-dev và tài khoản admin.")


if __name__ == "__main__":
    main()
