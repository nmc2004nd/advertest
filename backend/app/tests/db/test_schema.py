"""Kiểm tra schema, phân quyền và ràng buộc chống gian lận ở cấp DB (Phase 0, mục Database)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from advertest_contracts import enums
from backend.app.db import models as m

pytestmark = pytest.mark.db

EXPECTED_TABLES = {
    "users", "user_roles", "compute_targets", "cost_profiles", "models", "model_versions",
    "datasets", "dataset_versions", "class_mappings", "slices", "attack_specs", "protocols",
    "experiments", "runs", "search_results", "failure_cases", "case_verdicts", "reviews",
    "reports", "budgets", "quotas", "ledger_entries", "audit_log",
    # Phase 4
    "sessions", "password_reset_tokens", "auth_events",
}  # fmt: skip
APPEND_ONLY = [
    "audit_log", "case_verdicts", "reviews", "reports", "ledger_entries", "auth_events",
]  # fmt: skip
# Phase 4: thu hồi phiên, đánh dấu token đã dùng bằng UPDATE; không bao giờ xóa.
NO_DELETE_AUTH = ["sessions", "password_reset_tokens"]

# Enum Postgres ↔ enum contract (giá trị trong migration được ghi cứng, phải khớp contract).
PG_ENUMS = {
    "role": enums.Role,
    "user_status": enums.UserStatus,
    "run_status": enums.RunStatus,
    "experiment_status": enums.ExperimentStatus,
    "compute_kind": enums.ComputeKind,
    "billing_mode": enums.BillingMode,
    "limit_kind": enums.LimitKind,
    "attack_kind": enums.AttackKind,
    "attack_access": enums.AttackAccess,
    "review_decision": enums.ReviewDecision,
    "case_severity": enums.CaseSeverity,
    "protocol_status": enums.ProtocolStatus,
    "auth_event_kind": m.AuthEventKind,
}

SHA = "a" * 64


@dataclass(frozen=True)
class Sample:
    engineer: uuid.UUID
    reviewer: uuid.UUID
    experiment: uuid.UUID
    run: uuid.UUID
    attack_spec: uuid.UUID


@pytest.fixture(scope="module")
def sample(owner_engine: Engine) -> Sample:
    """Một chuỗi dữ liệu tối thiểu: user → model → dataset → slice → experiment → run → case."""
    tag = uuid.uuid4().hex[:8]
    with Session(owner_engine) as s, s.begin():
        engineer = m.User(email=f"eng-{tag}@x.test", full_name="E", password_hash="x")
        reviewer = m.User(email=f"rev-{tag}@x.test", full_name="R", password_hash="x")
        target = m.ComputeTarget(
            name=f"local-{tag}", kind=enums.ComputeKind.LOCAL, billing_mode=enums.BillingMode.NONE
        )
        s.add_all([engineer, reviewer, target])
        s.flush()
        model = m.Model(name=f"yolo-{tag}", created_by=engineer.id)
        dataset = m.Dataset(name="kitti", created_by=engineer.id)
        spec = m.AttackSpecRow(
            name=f"pgd-{tag}", version=1, kind=enums.AttackKind.ATTACK,
            access=enums.AttackAccess.WHITE_BOX, spec={}, spec_sha256=_sha(),
        )  # fmt: skip
        protocol = m.Protocol(
            name=f"p-{tag}", version=1, body={}, body_sha256=SHA, created_by=reviewer.id
        )
        s.add_all([model, dataset, spec, protocol])
        s.flush()
        model_version = m.ModelVersion(
            model_id=model.id, weights_sha256=_sha(), weights_uri="s3://models/w.pt",
            framework="ultralytics", class_names=["car"], input_size=640,
        )  # fmt: skip
        dataset_version = m.DatasetVersion(
            dataset_id=dataset.id, manifest_sha256=_sha(), manifest_uri="s3://datasets/m.json",
            num_images=5, class_names=["Car"],
        )  # fmt: skip
        s.add_all([model_version, dataset_version])
        s.flush()
        mapping = m.ClassMapping(
            dataset_version_id=dataset_version.id, model_version_id=model_version.id,
            mapping={}, mapping_sha256=_sha(),
        )  # fmt: skip
        slice_row = m.Slice(
            dataset_version_id=dataset_version.id, name="s", filter={}, seed=42,
            image_ids=["000001"], image_ids_sha256=SHA,
        )  # fmt: skip
        s.add_all([mapping, slice_row])
        s.flush()
        experiment = m.Experiment(
            created_by=engineer.id, protocol_id=protocol.id, model_version_id=model_version.id,
            slice_id=slice_row.id, class_mapping_id=mapping.id, compute_target_id=target.id,
            config={}, config_sha256=SHA, limit_kind=enums.LimitKind.TIME, limit_value=7200,
        )  # fmt: skip
        s.add(experiment)
        s.flush()
        run = m.Run(
            experiment_id=experiment.id, attack_spec_id=spec.id, level=4, params={}, seed=0,
            fingerprint=SHA, images_total=5,
        )  # fmt: skip
        s.add(run)
        s.flush()
        return Sample(engineer.id, reviewer.id, experiment.id, run.id, spec.id)


def _sha() -> str:
    return uuid.uuid4().hex * 2


@pytest.fixture
def app_conn(app_engine: Engine) -> Iterator[Connection]:
    """Kết nối bằng advertest_app trong một transaction luôn rollback."""
    with app_engine.connect() as conn:
        trans = conn.begin()
        yield conn
        trans.rollback()


def _denied(conn: Connection, sql: str, **params: object) -> bool:
    savepoint = conn.begin_nested()
    try:
        conn.execute(text(sql), params)
    except ProgrammingError as exc:
        savepoint.rollback()
        return "permission denied" in str(exc)
    savepoint.rollback()
    return False


def test_all_tables_exist(owner_engine: Engine) -> None:
    with owner_engine.connect() as conn:
        tables: set[str] = set(
            conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables"
                    " WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
                )
            ).scalars()
        )
    assert tables == EXPECTED_TABLES


@pytest.mark.parametrize("pg_name", sorted(PG_ENUMS))
def test_pg_enums_match_contract(owner_engine: Engine, pg_name: str) -> None:
    with owner_engine.connect() as conn:
        values: set[str] = set(
            conn.execute(text("SELECT unnest(enum_range(NULL::" + pg_name + "))::text")).scalars()
        )
    assert values == {m.value for m in PG_ENUMS[pg_name]}


def test_every_table_is_granted_to_app(owner_engine: Engine) -> None:
    """Bảng nào thiếu quyền cho advertest_app nghĩa là migration quên GRANT."""
    with owner_engine.connect() as conn:
        granted: set[str] = set(
            conn.execute(
                text(
                    "SELECT table_name FROM information_schema.role_table_grants"
                    " WHERE grantee = 'advertest_app' AND privilege_type = 'SELECT'"
                )
            ).scalars()
        )
    assert granted == EXPECTED_TABLES


def test_app_can_insert_audit_log(app_conn: Connection, sample: Sample) -> None:
    app_conn.execute(
        text("INSERT INTO audit_log (actor_id, action, entity_type) VALUES (:a, 'test', 'user')"),
        {"a": sample.engineer},
    )


@pytest.mark.parametrize("table", APPEND_ONLY)
def test_app_cannot_update_delete_truncate_append_only(
    app_conn: Connection, sample: Sample, table: str
) -> None:
    assert _denied(app_conn, f"UPDATE {table} SET id = id")
    assert _denied(app_conn, f"DELETE FROM {table}")
    assert _denied(app_conn, f"TRUNCATE {table}")


def test_app_cannot_delete_runs_but_can_archive(app_conn: Connection, sample: Sample) -> None:
    assert _denied(app_conn, "DELETE FROM runs WHERE id = :id", id=sample.run)
    updated = app_conn.execute(
        text("UPDATE runs SET archived = true WHERE id = :id"), {"id": sample.run}
    )
    assert updated.rowcount == 1


def test_duplicate_fingerprint_in_experiment_rejected(owner_engine: Engine, sample: Sample) -> None:
    duplicate = m.Run(
        experiment_id=sample.experiment, attack_spec_id=sample.attack_spec, level=8, params={},
        seed=1, fingerprint=SHA, images_total=5,
    )  # fmt: skip
    with pytest.raises(IntegrityError, match="uq_runs_experiment_id"), Session(owner_engine) as s:
        s.add(duplicate)
        s.commit()


def test_abnormal_run_status_requires_reason(owner_engine: Engine, sample: Sample) -> None:
    with (
        pytest.raises(IntegrityError, match="abnormal_status_has_reason"),
        owner_engine.begin() as c,
    ):
        c.execute(text("UPDATE runs SET status = 'failed' WHERE id = :id"), {"id": sample.run})


def test_self_review_rejected_by_trigger(app_conn: Connection, sample: Sample) -> None:
    review = {"e": sample.experiment, "d": "approve", "c": "ok"}
    with pytest.raises(IntegrityError, match="không được review"):
        app_conn.execute(
            text(
                "INSERT INTO reviews (experiment_id, reviewer_id, version, decision, conclusion)"
                " VALUES (:e, :r, 1, :d, :c)"
            ),
            {**review, "r": sample.engineer},
        )


def test_independent_review_allowed(app_conn: Connection, sample: Sample) -> None:
    app_conn.execute(
        text(
            "INSERT INTO reviews (experiment_id, reviewer_id, version, decision, conclusion)"
            " VALUES (:e, :r, 1, 'approve', 'ok')"
        ),
        {"e": sample.experiment, "r": sample.reviewer},
    )


@pytest.mark.parametrize("table", NO_DELETE_AUTH)
def test_app_cannot_delete_sessions_or_reset_tokens(app_conn: Connection, table: str) -> None:
    assert _denied(app_conn, f"DELETE FROM {table}")
    assert _denied(app_conn, f"TRUNCATE {table}")
