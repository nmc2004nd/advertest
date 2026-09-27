"""Nghiệm thu Phase 0, mục Database (validation.md). Cần Postgres thật: `make test-db`."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from alembic import command
from alembic.config import Config
from argon2 import PasswordHasher
from sqlalchemy import Connection, Engine, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from advertest_contracts import enums
from backend.admin_cli.seed import AdminAccount, load_attack_specs, seed
from backend.app.db import models as m

pytestmark = pytest.mark.db

TABLES = {
    "users", "user_roles", "compute_targets", "cost_profiles", "models", "model_versions",
    "datasets", "dataset_versions", "class_mappings", "slices", "attack_specs", "protocols",
    "experiments", "runs", "search_results", "failure_cases", "case_verdicts", "reviews",
    "reports", "budgets", "quotas", "ledger_entries", "audit_log",
}  # fmt: skip
SHA = "c" * 64


def _sha() -> str:
    return uuid.uuid4().hex * 2


@dataclass(frozen=True)
class Chain:
    engineer: uuid.UUID
    reviewer: uuid.UUID
    experiment: uuid.UUID
    run: uuid.UUID
    attack_spec: uuid.UUID


def test_migration_upgrade_downgrade_upgrade(alembic_config: Config, owner_engine: Engine) -> None:
    # Chạy đầu tiên trong file: các test sau tạo dữ liệu trên schema mới nhất.
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")


def test_all_tables_exist(owner_engine: Engine) -> None:
    with owner_engine.connect() as conn:
        tables = set(
            conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables"
                    " WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
                )
            ).scalars()
        )
    assert tables >= TABLES


@pytest.fixture(scope="module")
def chain(owner_engine: Engine) -> Chain:
    tag = uuid.uuid4().hex[:8]
    with Session(owner_engine) as s, s.begin():
        engineer = m.User(email=f"eng-{tag}@acc.test", full_name="E", password_hash="x")
        reviewer = m.User(email=f"rev-{tag}@acc.test", full_name="R", password_hash="x")
        target = m.ComputeTarget(
            name=f"t-{tag}", kind=enums.ComputeKind.LOCAL, billing_mode=enums.BillingMode.NONE
        )
        s.add_all([engineer, reviewer, target])
        s.flush()
        model = m.Model(name=f"m-{tag}", created_by=engineer.id)
        dataset = m.Dataset(name="d", created_by=engineer.id)
        spec = m.AttackSpecRow(
            name=f"a-{tag}", version=1, kind=enums.AttackKind.ATTACK,
            access=enums.AttackAccess.WHITE_BOX, spec={}, spec_sha256=_sha(),
        )  # fmt: skip
        protocol = m.Protocol(
            name=f"p-{tag}", version=1, body={}, body_sha256=SHA, created_by=reviewer.id
        )
        s.add_all([model, dataset, spec, protocol])
        s.flush()
        mv = m.ModelVersion(
            model_id=model.id, weights_sha256=_sha(), weights_uri="s3://w", framework="u",
            class_names=["car"], input_size=640,
        )  # fmt: skip
        dv = m.DatasetVersion(
            dataset_id=dataset.id, manifest_sha256=_sha(), manifest_uri="s3://m", num_images=1,
            class_names=["Car"],
        )  # fmt: skip
        s.add_all([mv, dv])
        s.flush()
        mapping = m.ClassMapping(
            dataset_version_id=dv.id, model_version_id=mv.id, mapping={}, mapping_sha256=_sha()
        )
        sl = m.Slice(
            dataset_version_id=dv.id, name="s", filter={}, seed=0, image_ids=["1"],
            image_ids_sha256=SHA,
        )  # fmt: skip
        s.add_all([mapping, sl])
        s.flush()
        exp = m.Experiment(
            created_by=engineer.id, protocol_id=protocol.id, model_version_id=mv.id,
            slice_id=sl.id, class_mapping_id=mapping.id, compute_target_id=target.id, config={},
            config_sha256=SHA, limit_kind=enums.LimitKind.TIME, limit_value=7200,
        )  # fmt: skip
        s.add(exp)
        s.flush()
        run = m.Run(
            experiment_id=exp.id, attack_spec_id=spec.id, level=4, params={}, seed=0,
            fingerprint=SHA, images_total=1,
        )  # fmt: skip
        s.add(run)
        s.flush()
        return Chain(engineer.id, reviewer.id, exp.id, run.id, spec.id)


@pytest.fixture
def app_conn(app_engine: Engine) -> Iterator[Connection]:
    """Kết nối bằng advertest_app, luôn rollback sau test."""
    with app_engine.connect() as conn:
        trans = conn.begin()
        yield conn
        trans.rollback()


def _denied(conn: Connection, sql: str, **params: object) -> bool:
    savepoint = conn.begin_nested()
    try:
        conn.execute(text(sql), params)
    except DBAPIError as exc:
        savepoint.rollback()
        return "permission denied" in str(exc)
    savepoint.rollback()
    return False


def test_app_can_insert_audit_log(app_conn: Connection, chain: Chain) -> None:
    app_conn.execute(
        text("INSERT INTO audit_log (actor_id, action, entity_type) VALUES (:a, 'x', 'user')"),
        {"a": chain.engineer},
    )


def test_app_cannot_update_delete_truncate_audit_log(app_conn: Connection, chain: Chain) -> None:
    assert _denied(app_conn, "UPDATE audit_log SET action = 'y'")
    assert _denied(app_conn, "DELETE FROM audit_log")
    assert _denied(app_conn, "TRUNCATE audit_log")


@pytest.mark.parametrize("table", ["case_verdicts", "reviews", "reports", "ledger_entries"])
def test_app_cannot_update_or_delete_append_only(
    app_conn: Connection, chain: Chain, table: str
) -> None:
    assert _denied(app_conn, f"UPDATE {table} SET id = id")
    assert _denied(app_conn, f"DELETE FROM {table}")


def test_app_cannot_delete_runs_but_can_archive(app_conn: Connection, chain: Chain) -> None:
    assert _denied(app_conn, "DELETE FROM runs WHERE id = :id", id=chain.run)
    result = app_conn.execute(
        text("UPDATE runs SET archived = true WHERE id = :id"), {"id": chain.run}
    )
    assert result.rowcount == 1


def test_duplicate_fingerprint_in_experiment_violates_unique(
    owner_engine: Engine, chain: Chain
) -> None:
    dup = m.Run(
        experiment_id=chain.experiment, attack_spec_id=chain.attack_spec, level=8, params={},
        seed=1, fingerprint=SHA, images_total=1,
    )  # fmt: skip
    with pytest.raises(IntegrityError), Session(owner_engine) as s:
        s.add(dup)
        s.commit()


def test_self_review_rejected_by_trigger(app_conn: Connection, chain: Chain) -> None:
    with pytest.raises(IntegrityError):
        app_conn.execute(
            text(
                "INSERT INTO reviews (experiment_id, reviewer_id, version, decision, conclusion)"
                " VALUES (:e, :r, 1, 'approve', 'ok')"
            ),
            {"e": chain.experiment, "r": chain.engineer},
        )


def test_seed(app_engine: Engine) -> None:
    admin = AdminAccount(email="admin@acceptance.test", password="acceptance-password")
    seed(app_engine, admin)
    seed(app_engine, admin)
    expected = {spec.spec_sha256 for spec in load_attack_specs()}
    with Session(app_engine) as s:
        seeded = set(
            s.scalars(
                select(m.AttackSpecRow.spec_sha256).where(m.AttackSpecRow.spec_sha256.in_(expected))
            )
        )
        assert seeded == expected
        target = s.scalars(select(m.ComputeTarget).where(m.ComputeTarget.name == "local-dev")).one()
        assert target.billing_mode == enums.BillingMode.NONE
        user = s.scalars(select(m.User).where(m.User.email == admin.email)).one()
        assert user.status == enums.UserStatus.ACTIVE
        assert PasswordHasher().verify(user.password_hash, admin.password)
        roles = set(s.scalars(select(m.UserRole.role).where(m.UserRole.user_id == user.id)))
        assert enums.Role.ADMIN in roles
