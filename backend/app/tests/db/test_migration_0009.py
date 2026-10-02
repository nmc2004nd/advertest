"""Migration 0009 (Phase 8): bảng review, quyền và trigger chống gian lận; downgrade 0006 (task
7a)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from advertest_contracts import enums
from advertest_contracts.enums import RunMode
from advertest_contracts.hashing import sha256_of
from advertest_contracts.models import (
    AttackConfig,
    AttackSpecBody,
    ExperimentConfig,
    GridConfig,
    Limit,
    compute_spec_sha256,
)
from attacks.registry import get_spec, load_catalog
from backend.app.db import models as m

pytestmark = pytest.mark.db
SHA = "b" * 64
DEV_OPEN = "2edcdef5-0d3a-5d5f-98ac-b02637fa6718"


def _sha() -> str:
    return uuid.uuid4().hex * 2


@dataclass(frozen=True)
class Chain:
    engineer: uuid.UUID
    reviewer: uuid.UUID
    experiment: uuid.UUID
    run: uuid.UUID
    case: uuid.UUID
    spec: uuid.UUID


def _chain(owner_engine: Engine, status: enums.ExperimentStatus) -> Chain:
    """Chuỗi dữ liệu tối thiểu tới một failure case, experiment ở `status`."""
    tag = uuid.uuid4().hex[:8]
    with Session(owner_engine) as s, s.begin():
        engineer = m.User(email=f"e-{tag}@p8.test", full_name="E", password_hash="x")
        reviewer = m.User(email=f"r-{tag}@p8.test", full_name="R", password_hash="x")
        target = m.ComputeTarget(
            name=f"t-{tag}", kind=enums.ComputeKind.LOCAL, billing_mode=enums.BillingMode.NONE
        )
        s.add_all([engineer, reviewer, target])
        s.flush()
        model = m.Model(name=f"m-{tag}", created_by=engineer.id)
        dataset = m.Dataset(name="d", created_by=engineer.id)
        # Spec hợp lệ (bản sao fgsm đổi tên): các test đọc catalog chạy sau trên cùng DB.
        body = {
            k: v
            for k, v in get_spec(load_catalog(), name="fgsm")
            .model_dump(mode="json", include=set(AttackSpecBody.model_fields))
            .items()
        }
        body["name"] = f"a{tag}"
        spec = m.AttackSpecRow(
            name=body["name"], version=1, kind=enums.AttackKind.ATTACK,
            access=enums.AttackAccess.WHITE_BOX, spec=body,
            spec_sha256=compute_spec_sha256(body),
        )  # fmt: skip
        s.add_all([model, dataset, spec])
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
        # Cấu hình hợp lệ (dev-open): hàng đợi review của test khác đọc mọi experiment đang review.
        config = ExperimentConfig(
            protocol_id=uuid.UUID(DEV_OPEN), model_version_id=mv.id, slice_id=sl.id,
            class_mapping_id=mapping.id, compute_target_id=target.id,
            attacks=[AttackConfig(
                attack_spec_id=spec.id, spec_sha256=spec.spec_sha256, mode=RunMode.GRID,
                grid=GridConfig(levels=[4]), seed=0,
            )],
            limit=Limit(kind=enums.LimitKind.TIME, value=Decimal(7200)),
        )  # fmt: skip
        exp = m.Experiment(
            created_by=engineer.id, protocol_id=config.protocol_id, model_version_id=mv.id,
            slice_id=sl.id, class_mapping_id=mapping.id, compute_target_id=target.id,
            config=config.model_dump(mode="json"), config_sha256=sha256_of(config),
            limit_kind=enums.LimitKind.TIME, limit_value=7200,
            status=enums.ExperimentStatus.COMPLETED, finished_at=datetime.now(UTC),
        )  # fmt: skip
        s.add(exp)
        s.flush()
        run = m.Run(
            experiment_id=exp.id, attack_spec_id=spec.id, level=4, params={}, seed=0,
            fingerprint=_sha(), images_total=1, status=enums.RunStatus.COMPLETED,
        )  # fmt: skip
        s.add(run)
        s.flush()
        case = m.FailureCase(
            run_id=run.id, image_id="1", severity_score=1.0, fingerprint=SHA, rank=0,
            lost_objects=1, new_false_positives=0, detections={}, artifacts={},
        )  # fmt: skip
        s.add(case)
        s.flush()
        if status != enums.ExperimentStatus.COMPLETED:
            reviewing = status != enums.ExperimentStatus.SUBMITTED_FOR_REVIEW
            exp.status = status
            exp.locked_at = datetime.now(UTC)
            exp.review_submitted_at = datetime.now(UTC)
            exp.review_assignee_id = reviewer.id if reviewing else None
        return Chain(engineer.id, reviewer.id, exp.id, run.id, case.id, spec.id)


@pytest.fixture
def app_conn(app_engine: Engine) -> Iterator[Connection]:
    with app_engine.connect() as conn:
        trans = conn.begin()
        yield conn
        trans.rollback()


def _fails(conn: Connection, sql: str, **params: object) -> str | None:
    """Thông điệp lỗi của câu lệnh (None nếu chạy được); không làm hỏng transaction ngoài."""
    savepoint = conn.begin_nested()
    try:
        conn.execute(text(sql), params)
    except DBAPIError as exc:
        savepoint.rollback()
        return str(exc)
    savepoint.rollback()
    return None


VERDICT = (
    "INSERT INTO case_verdicts (failure_case_id, reviewer_id, version, severity, kind)"
    " VALUES (:case, :reviewer, 1, 'major', 'acceptable')"
)
COMMENT = (
    "INSERT INTO review_comments (experiment_id, author_id, target_type, target_id, body)"
    " VALUES (:experiment, :reviewer, 'experiment', :experiment, 'x')"
)
EXPLANATION = "INSERT INTO run_explanations (run_id, author_id, text) VALUES (:run, :engineer, 'x')"


# ---------------------------------------------------------------- task 7a, hai chiều


def test_downgrade_0006_with_cost_profile_of_not_applicable_spec(
    alembic_config: Config, owner_engine: Engine
) -> None:
    """Phase 7 phát hiện 1: cost profile trỏ tới spec `not_applicable` chặn downgrade 0006."""
    chain = _chain(owner_engine, enums.ExperimentStatus.COMPLETED)
    with Session(owner_engine) as s, s.begin():
        experiment = s.get(m.Experiment, chain.experiment)
        assert experiment is not None
        spec = m.AttackSpecRow(
            name=f"fog{uuid.uuid4().hex[:6]}", version=1, kind=enums.AttackKind.CORRUPTION,
            access=enums.AttackAccess.NOT_APPLICABLE, spec={}, spec_sha256=_sha(),
        )  # fmt: skip
        s.add(spec)
        s.flush()
        spec_id = spec.id
        s.add(
            m.CostProfile(
                compute_target_id=experiment.compute_target_id,
                attack_spec_id=spec.id,
                model_version_id=experiment.model_version_id,
                sec_per_image=0.1,
                peak_vram_mb=100,
                batch_size=4,
                measured_at=datetime.now(UTC),
                environment={},
            )
        )
    command.downgrade(alembic_config, "0005")
    try:
        with owner_engine.connect() as conn:
            left: int = conn.execute(
                text("SELECT count(*) FROM attack_specs WHERE id = :id"), {"id": spec_id}
            ).scalar_one()
        assert left == 0
    finally:
        command.upgrade(alembic_config, "head")


def test_downgrade_and_upgrade_0009(alembic_config: Config, owner_engine: Engine) -> None:
    command.downgrade(alembic_config, "0008")
    try:
        tables = set(inspect(owner_engine).get_table_names())
        assert not {"run_explanations", "review_comments"} & tables
        columns = {c["name"] for c in inspect(owner_engine).get_columns("case_verdicts")}
        assert "verdict" in columns and "kind" not in columns
    finally:
        command.upgrade(alembic_config, "head")
    columns = {c["name"] for c in inspect(owner_engine).get_columns("reports")}
    assert {"status", "approved_by", "json_sha256", "pdf_sha256", "attempts"} <= columns
    assert not {"sha256", "exported_by", "pdf_uri", "json_uri"} & columns


# ---------------------------------------------------------------- quyền


@pytest.mark.parametrize("table", ["review_comments", "run_explanations", "case_verdicts"])
def test_app_cannot_update_or_delete_review_rows(app_conn: Connection, table: str) -> None:
    for sql in (f"UPDATE {table} SET id = id", f"DELETE FROM {table}"):
        message = _fails(app_conn, sql)
        assert message is not None and "permission denied" in message, sql


def test_app_updates_only_report_state_columns(app_conn: Connection) -> None:
    for column in ("id", "experiment_id", "approved_by", "created_at"):
        message = _fails(app_conn, f"UPDATE reports SET {column} = {column}")
        assert message is not None and "permission denied" in message, column
    for column in ("status", "attempts", "json_sha256", "pdf_key", "generated_at"):
        assert _fails(app_conn, f"UPDATE reports SET {column} = {column}") is None, column
    message = _fails(app_conn, "DELETE FROM reports")
    assert message is not None and "permission denied" in message


def test_ready_report_is_immutable(owner_engine: Engine, app_conn: Connection) -> None:
    chain = _chain(owner_engine, enums.ExperimentStatus.APPROVED)
    params = {"experiment": chain.experiment, "reviewer": chain.reviewer}
    report: uuid.UUID = app_conn.execute(
        text(
            "INSERT INTO reports (experiment_id, approved_by) VALUES (:experiment, :reviewer)"
            " RETURNING id"
        ),
        params,
    ).scalar_one()
    ready = (
        "UPDATE reports SET status = 'ready', attempts = 1, snapshot_key = 'reports/a/s.json',"
        " json_key = 'reports/a/r.json', pdf_key = 'reports/a/r.pdf', json_sha256 = :sha,"
        " pdf_sha256 = :sha, generated_at = now() WHERE id = :id"
    )
    assert _fails(app_conn, "UPDATE reports SET status = 'ready' WHERE id = :id", id=report)
    app_conn.execute(text(ready), {"sha": SHA, "id": report})
    message = _fails(app_conn, "UPDATE reports SET status = 'failed' WHERE id = :id", id=report)
    assert message is not None and "không sửa được" in message
    second = _fails(
        app_conn,
        "INSERT INTO reports (experiment_id, approved_by) VALUES (:experiment, :reviewer)",
        **params,
    )
    assert second is not None and "uq_reports_experiment_id" in second


# ---------------------------------------------------------------- trigger


def test_assignee_cannot_be_creator(owner_engine: Engine, app_conn: Connection) -> None:
    chain = _chain(owner_engine, enums.ExperimentStatus.SUBMITTED_FOR_REVIEW)
    message = _fails(
        app_conn,
        "UPDATE experiments SET review_assignee_id = created_by, status = 'in_review'"
        " WHERE id = :id",
        id=chain.experiment,
    )
    assert message is not None and "nhận review" in message
    assert (
        _fails(
            app_conn,
            "UPDATE experiments SET review_assignee_id = :r, status = 'in_review',"
            " claimed_at = now() WHERE id = :id",
            r=chain.reviewer,
            id=chain.experiment,
        )
        is None
    )


@pytest.mark.parametrize(
    "change",
    [
        "config = '{\"x\": 1}'::jsonb",
        "name = 'đổi tên'",
        "status = 'completed'",
        "status = 'cancelled'",
        "locked_at = NULL",
        "limit_value = 1",
    ],
)
def test_locked_experiment_rejects_changes(
    owner_engine: Engine, app_conn: Connection, change: str
) -> None:
    chain = _chain(owner_engine, enums.ExperimentStatus.SUBMITTED_FOR_REVIEW)
    message = _fails(
        app_conn, f"UPDATE experiments SET {change} WHERE id = :id", id=chain.experiment
    )
    assert message is not None and "bị khóa" in message


def test_locked_experiment_allows_review_flow(owner_engine: Engine, app_conn: Connection) -> None:
    chain = _chain(owner_engine, enums.ExperimentStatus.IN_REVIEW)
    for change in (
        "status = 'submitted_for_review', review_assignee_id = NULL, claimed_at = NULL",
        "status = 'in_review', review_assignee_id = :r, claimed_at = now()",
        "status = 'approved', decided_at = now()",
    ):
        sql = f"UPDATE experiments SET {change} WHERE id = :id"
        assert _fails(app_conn, sql, id=chain.experiment, r=chain.reviewer) is None, change
        app_conn.execute(text(sql), {"id": chain.experiment, "r": chain.reviewer})


def test_locked_experiment_rejects_run_and_case_writes(
    owner_engine: Engine, app_conn: Connection
) -> None:
    chain = _chain(owner_engine, enums.ExperimentStatus.SUBMITTED_FOR_REVIEW)
    message = _fails(app_conn, "UPDATE runs SET level = 8 WHERE id = :id", id=chain.run)
    assert message is not None and "bị khóa" in message
    message = _fails(
        app_conn,
        "INSERT INTO runs (experiment_id, attack_spec_id, level, params, seed, images_total)"
        " VALUES (:e, :s, 16, '{}'::jsonb, 0, 1)",
        e=chain.experiment,
        s=chain.spec,
    )
    assert message is not None and "bị khóa" in message
    message = _fails(
        app_conn, "UPDATE failure_cases SET severity_score = 9 WHERE id = :id", id=chain.case
    )
    assert message is not None and "bị khóa" in message


def test_unlocked_experiment_unaffected(owner_engine: Engine, app_conn: Connection) -> None:
    chain = _chain(owner_engine, enums.ExperimentStatus.COMPLETED)
    assert _fails(app_conn, "UPDATE runs SET level = 8 WHERE id = :id", id=chain.run) is None
    sql = "UPDATE experiments SET name = 'đổi tên' WHERE id = :id"
    assert _fails(app_conn, sql, id=chain.experiment) is None


@pytest.mark.parametrize(
    "status",
    [
        enums.ExperimentStatus.APPROVED,
        enums.ExperimentStatus.CHANGES_REQUESTED,
        enums.ExperimentStatus.REJECTED,
    ],
)
def test_no_review_rows_after_decision(
    owner_engine: Engine, app_conn: Connection, status: enums.ExperimentStatus
) -> None:
    chain = _chain(owner_engine, status)
    params = {
        "case": chain.case, "reviewer": chain.reviewer, "experiment": chain.experiment,
        "run": chain.run, "engineer": chain.engineer,
    }  # fmt: skip
    for sql in (VERDICT, COMMENT, EXPLANATION):
        message = _fails(app_conn, sql, **params)
        assert message is not None and "đã có quyết định" in message, sql


def test_review_rows_allowed_while_in_review(owner_engine: Engine, app_conn: Connection) -> None:
    chain = _chain(owner_engine, enums.ExperimentStatus.IN_REVIEW)
    params = {
        "case": chain.case, "reviewer": chain.reviewer, "experiment": chain.experiment,
        "run": chain.run, "engineer": chain.engineer,
    }  # fmt: skip
    for sql in (VERDICT, COMMENT, EXPLANATION):
        assert _fails(app_conn, sql, **params) is None, sql
        app_conn.execute(text(sql), params)
    duplicate = _fails(app_conn, EXPLANATION, **params)
    assert duplicate is not None and "uq_run_explanations_run_id" in duplicate


def test_comment_on_experiment_must_target_itself(
    owner_engine: Engine, app_conn: Connection
) -> None:
    chain = _chain(owner_engine, enums.ExperimentStatus.IN_REVIEW)
    message = _fails(
        app_conn,
        "INSERT INTO review_comments (experiment_id, author_id, target_type, target_id, body)"
        " VALUES (:e, :a, 'experiment', :other, 'x')",
        e=chain.experiment,
        a=chain.reviewer,
        other=chain.run,
    )
    assert message is not None and "experiment_target" in message


def test_errors_are_integrity_or_permission(app_conn: Connection) -> None:
    """Lỗi trigger là check_violation (IntegrityError) để service phân biệt với lỗi quyền."""
    with pytest.raises((IntegrityError, ProgrammingError)):
        app_conn.execute(text("UPDATE review_comments SET body = 'x'"))


@pytest.mark.parametrize(
    "change",
    [
        "status = 'in_review'",
        "status = 'submitted_for_review', review_assignee_id = NULL, claimed_at = NULL",
        "decided_at = now()",
        "review_assignee_id = NULL",
    ],
)
@pytest.mark.parametrize(
    "status",
    [
        enums.ExperimentStatus.APPROVED,
        enums.ExperimentStatus.CHANGES_REQUESTED,
        enums.ExperimentStatus.REJECTED,
    ],
)
def test_decided_experiment_is_final(
    owner_engine: Engine, app_conn: Connection, status: enums.ExperimentStatus, change: str
) -> None:
    """Review Group 1 #1: trạng thái quyết định là cuối, kể cả ở tầng DB."""
    chain = _chain(owner_engine, status)
    message = _fails(
        app_conn, f"UPDATE experiments SET {change} WHERE id = :id", id=chain.experiment
    )
    assert message is not None and "không đổi được nữa" in message
