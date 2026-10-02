"""Phase 8 Group 1: protocol, review, report (requirements.md Phase 8, Thay đổi DB; plan task 7).

- `protocols`: `created_at`; body của `dev-open` theo `ProtocolBody` v2
  (`contracts/mocks/protocol_body/dev_open.json`).
- `experiments`: `submission_note`, `review_assignee_id`, `claimed_at`, `decided_at`
  (`submitted_at`, `locked_at` có từ Phase 0). Trigger: người nhận review khác người tạo;
  experiment đã khóa (`locked_at`) chỉ đổi được trạng thái review và người nhận.
- `runs`, `failure_cases`: không thêm hay sửa được khi experiment đã khóa.
- `run_explanations`, `review_comments` (mới): `advertest_app` chỉ SELECT, INSERT.
- `case_verdicts`: thêm `kind`, bỏ `verdict` (contract Phase 8 không còn trường này).
- `reviews`: `model_verdict`, `inconclusive_justification`, `criteria_results`, `checklist`.
- `reports`: trạng thái sinh report, khóa và hash của từng file, `attempts`, `generated_at`;
  `exported_by` → `approved_by`; mỗi experiment một report. `advertest_app` chỉ UPDATE được các
  cột trạng thái, khóa, hash (quyền theo cột: `UPDATE ... SET id = id` vẫn bị từ chối như Phase 0);
  trigger không cho sửa report đã `ready` (kickoff Phase 8).
- Trigger: không thêm `case_verdicts`, `review_comments`, `run_explanations` khi experiment đã
  `approved`, `changes_requested`, `rejected`.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
UUID_PK = sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)

DEV_OPEN_ID = "2edcdef5-0d3a-5d5f-98ac-b02637fa6718"
# canonical_json của ProtocolBody dev-open (contracts/mocks/protocol_body/dev_open.json).
DEV_OPEN_BODY = (
    '{"schema_version": 2, "description": "Protocol phát triển: không có attack bắt buộc, không'
    ' bao giờ gửi duyệt.", "required_attacks": [], "min_slice_size": 1, "pass_criteria": [],'
    ' "cases_to_review_per_attack": 5, "forbid_dirty_runs": true}'
)
DEV_OPEN_BODY_SHA256 = "55bfd18a8a25c5e02f9dfe58477b9ca1d7c20c878d60db4262e90fc6830df800"
OLD_DEV_OPEN_BODY_SHA256 = "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"

DECIDED = "('approved', 'changes_requested', 'rejected')"
REVIEW_STATUSES = (
    "('submitted_for_review', 'in_review', 'approved', 'changes_requested', 'rejected')"
)
REPORT_UPDATABLE = (
    "status", "attempts", "snapshot_key", "json_key", "pdf_key", "json_sha256", "pdf_sha256",
    "generated_at",
)  # fmt: skip

FUNCTIONS = f"""
CREATE FUNCTION forbid_self_assignee() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.review_assignee_id IS NOT NULL AND NEW.review_assignee_id = NEW.created_by THEN
        RAISE EXCEPTION 'Người tạo experiment không được nhận review experiment của mình'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION forbid_locked_experiment_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.locked_at IS NULL THEN
        RETURN NEW;
    END IF;
    IF NEW.locked_at IS DISTINCT FROM OLD.locked_at
        OR NEW.status::text NOT IN {REVIEW_STATUSES}
        OR (to_jsonb(NEW) - ARRAY['status', 'review_assignee_id', 'claimed_at', 'decided_at'])
            IS DISTINCT FROM
           (to_jsonb(OLD) - ARRAY['status', 'review_assignee_id', 'claimed_at', 'decided_at'])
    THEN
        RAISE EXCEPTION 'Experiment đã gửi duyệt nên bị khóa'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION forbid_locked_run_write() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (SELECT locked_at FROM experiments WHERE id = NEW.experiment_id) IS NOT NULL THEN
        RAISE EXCEPTION 'Experiment đã gửi duyệt nên bị khóa'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION forbid_locked_case_write() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (SELECT e.locked_at FROM runs r JOIN experiments e ON e.id = r.experiment_id
        WHERE r.id = NEW.run_id) IS NOT NULL THEN
        RAISE EXCEPTION 'Experiment đã gửi duyệt nên bị khóa'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION forbid_review_write_after_decision() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    experiment_status text;
BEGIN
    IF TG_TABLE_NAME = 'case_verdicts' THEN
        SELECT e.status::text INTO experiment_status
        FROM failure_cases c JOIN runs r ON r.id = c.run_id
        JOIN experiments e ON e.id = r.experiment_id
        WHERE c.id = NEW.failure_case_id;
    ELSIF TG_TABLE_NAME = 'run_explanations' THEN
        SELECT e.status::text INTO experiment_status
        FROM runs r JOIN experiments e ON e.id = r.experiment_id WHERE r.id = NEW.run_id;
    ELSE
        SELECT status::text INTO experiment_status FROM experiments WHERE id = NEW.experiment_id;
    END IF;
    IF experiment_status IN {DECIDED} THEN
        RAISE EXCEPTION 'Review đã có quyết định; không thêm được %', TG_TABLE_NAME
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION forbid_ready_report_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status = 'ready' THEN
        RAISE EXCEPTION 'Report đã phát hành không sửa được'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$;
"""

TRIGGERS = [
    (
        "experiments_forbid_self_assignee",
        "BEFORE INSERT OR UPDATE OF review_assignee_id ON experiments",
        "forbid_self_assignee",
    ),
    (
        "experiments_forbid_locked_change",
        "BEFORE UPDATE ON experiments",
        "forbid_locked_experiment_change",
    ),
    ("runs_forbid_locked_write", "BEFORE INSERT OR UPDATE ON runs", "forbid_locked_run_write"),
    (
        "failure_cases_forbid_locked_write",
        "BEFORE INSERT OR UPDATE ON failure_cases",
        "forbid_locked_case_write",
    ),
    (
        "case_verdicts_forbid_after_decision",
        "BEFORE INSERT ON case_verdicts",
        "forbid_review_write_after_decision",
    ),
    (
        "review_comments_forbid_after_decision",
        "BEFORE INSERT ON review_comments",
        "forbid_review_write_after_decision",
    ),
    (
        "run_explanations_forbid_after_decision",
        "BEFORE INSERT ON run_explanations",
        "forbid_review_write_after_decision",
    ),
    ("reports_forbid_ready_change", "BEFORE UPDATE ON reports", "forbid_ready_report_change"),
]
FUNCTION_NAMES = [
    "forbid_self_assignee",
    "forbid_locked_experiment_change",
    "forbid_locked_run_write",
    "forbid_locked_case_write",
    "forbid_review_write_after_decision",
    "forbid_ready_report_change",
]


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in {
        "case_verdict_kind": ("safety_relevant", "acceptable", "annotation_issue"),
        "model_verdict": ("meets_criteria", "does_not_meet", "conditional"),
        "report_status": ("generating", "ready", "failed"),
        "comment_target_type": ("experiment", "run", "failure_case"),
    }.items():
        postgresql.ENUM(*values, name=name).create(bind)

    # ------------------------------------------------------------ protocols
    op.add_column("protocols", sa.Column("created_at", TZ, server_default=sa.func.now()))
    op.execute("UPDATE protocols SET created_at = now() WHERE created_at IS NULL")
    op.alter_column("protocols", "created_at", nullable=False)
    op.execute(
        sa.text(
            "UPDATE protocols SET body = CAST(:body AS jsonb), body_sha256 = :sha"
            " WHERE id = CAST(:id AS uuid)"
        ).bindparams(body=DEV_OPEN_BODY, sha=DEV_OPEN_BODY_SHA256, id=DEV_OPEN_ID)
    )

    # ------------------------------------------------------------ experiments
    op.add_column("experiments", sa.Column("submission_note", sa.Text(), nullable=True))
    op.add_column("experiments", sa.Column("review_assignee_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_experiments_review_assignee_id_users"),
        "experiments",
        "users",
        ["review_assignee_id"],
        ["id"],
    )
    op.add_column("experiments", sa.Column("claimed_at", TZ, nullable=True))
    op.add_column("experiments", sa.Column("decided_at", TZ, nullable=True))

    # ------------------------------------------------------------ run_explanations
    op.create_table(
        "run_explanations",
        UUID_PK.copy(),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", TZ, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name=op.f("fk_run_explanations_run_id_runs")
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_run_explanations_author_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_run_explanations")),
        sa.UniqueConstraint("run_id", name=op.f("uq_run_explanations_run_id")),
    )

    # ------------------------------------------------------------ review_comments
    op.create_table(
        "review_comments",
        UUID_PK.copy(),
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column(
            "target_type",
            postgresql.ENUM(name="comment_target_type", create_type=False),
            nullable=False,
        ),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", TZ, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["experiments.id"],
            name=op.f("fk_review_comments_experiment_id_experiments"),
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_review_comments_author_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_comments")),
        sa.CheckConstraint(
            "target_type <> 'experiment' OR target_id = experiment_id",
            name=op.f("ck_review_comments_experiment_target"),
        ),
    )
    op.create_index(
        "ix_review_comments_experiment_created",
        "review_comments",
        ["experiment_id", "created_at"],
    )

    # ------------------------------------------------------------ case_verdicts
    op.add_column(
        "case_verdicts",
        sa.Column(
            "kind",
            postgresql.ENUM(name="case_verdict_kind", create_type=False),
            server_default=sa.text("'acceptable'"),
            nullable=False,
        ),
    )
    op.alter_column("case_verdicts", "kind", server_default=None)
    op.drop_column("case_verdicts", "verdict")

    # ------------------------------------------------------------ reviews
    op.add_column(
        "reviews",
        sa.Column(
            "model_verdict",
            postgresql.ENUM(name="model_verdict", create_type=False),
            nullable=True,
        ),
    )
    op.add_column("reviews", sa.Column("inconclusive_justification", sa.Text(), nullable=True))
    op.add_column(
        "reviews",
        sa.Column("criteria_results", JSONB, server_default=sa.text("'[]'"), nullable=False),
    )
    op.add_column(
        "reviews", sa.Column("checklist", JSONB, server_default=sa.text("'[]'"), nullable=False)
    )

    # ------------------------------------------------------------ reports
    # Report chỉ có từ Phase 8: bảng của Phase 0 chưa từng có dòng nào được ghi.
    op.execute("DELETE FROM reports")
    op.drop_constraint(op.f("uq_reports_sha256"), "reports", type_="unique")
    op.drop_column("reports", "sha256")
    op.drop_column("reports", "pdf_uri")
    op.drop_column("reports", "json_uri")
    op.drop_constraint(op.f("fk_reports_exported_by_users"), "reports", type_="foreignkey")
    op.alter_column("reports", "exported_by", new_column_name="approved_by")
    op.create_foreign_key(
        op.f("fk_reports_approved_by_users"), "reports", "users", ["approved_by"], ["id"]
    )
    op.add_column(
        "reports",
        sa.Column(
            "status",
            postgresql.ENUM(name="report_status", create_type=False),
            server_default=sa.text("'generating'"),
            nullable=False,
        ),
    )
    op.add_column(
        "reports", sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False)
    )
    for column in ("snapshot_key", "json_key", "pdf_key"):
        op.add_column("reports", sa.Column(column, sa.Text(), nullable=True))
    for column in ("json_sha256", "pdf_sha256"):
        op.add_column("reports", sa.Column(column, sa.String(length=64), nullable=True))
    op.add_column("reports", sa.Column("generated_at", TZ, nullable=True))
    op.create_unique_constraint(op.f("uq_reports_experiment_id"), "reports", ["experiment_id"])
    op.create_check_constraint(
        op.f("ck_reports_ready_has_files"),
        "reports",
        "status <> 'ready' OR (snapshot_key IS NOT NULL AND json_key IS NOT NULL"
        " AND pdf_key IS NOT NULL AND json_sha256 IS NOT NULL AND pdf_sha256 IS NOT NULL"
        " AND generated_at IS NOT NULL)",
    )

    # ------------------------------------------------------------ trigger, quyền
    op.execute(FUNCTIONS)
    for name, when, function in TRIGGERS:
        op.execute(f"CREATE TRIGGER {name} {when} FOR EACH ROW EXECUTE FUNCTION {function}()")
    for table in ("run_explanations", "review_comments"):
        op.execute(f"GRANT SELECT, INSERT ON {table} TO advertest_app")
    op.execute(f"GRANT UPDATE ({', '.join(REPORT_UPDATABLE)}) ON reports TO advertest_app")


def downgrade() -> None:
    op.execute(f"REVOKE UPDATE ({', '.join(REPORT_UPDATABLE)}) ON reports FROM advertest_app")
    for name, when, _ in TRIGGERS:
        table = when.rsplit(" ON ", 1)[1]
        op.execute(f"DROP TRIGGER {name} ON {table}")
    for function in FUNCTION_NAMES:
        op.execute(f"DROP FUNCTION {function}()")

    op.execute("DELETE FROM reports")
    op.drop_constraint(op.f("ck_reports_ready_has_files"), "reports", type_="check")
    op.drop_constraint(op.f("uq_reports_experiment_id"), "reports", type_="unique")
    for column in (
        "generated_at", "pdf_sha256", "json_sha256", "pdf_key", "json_key", "snapshot_key",
        "attempts", "status",
    ):  # fmt: skip
        op.drop_column("reports", column)
    op.drop_constraint(op.f("fk_reports_approved_by_users"), "reports", type_="foreignkey")
    op.alter_column("reports", "approved_by", new_column_name="exported_by")
    op.create_foreign_key(
        op.f("fk_reports_exported_by_users"), "reports", "users", ["exported_by"], ["id"]
    )
    op.add_column("reports", sa.Column("json_uri", sa.Text(), nullable=False))
    op.add_column("reports", sa.Column("pdf_uri", sa.Text(), nullable=False))
    op.add_column("reports", sa.Column("sha256", sa.String(length=64), nullable=False))
    op.create_unique_constraint(op.f("uq_reports_sha256"), "reports", ["sha256"])

    op.drop_column("reviews", "checklist")
    op.drop_column("reviews", "criteria_results")
    op.drop_column("reviews", "inconclusive_justification")
    op.drop_column("reviews", "model_verdict")

    op.add_column(
        "case_verdicts",
        sa.Column("verdict", sa.Text(), server_default=sa.text("''"), nullable=False),
    )
    op.alter_column("case_verdicts", "verdict", server_default=None)
    op.drop_column("case_verdicts", "kind")

    op.drop_index("ix_review_comments_experiment_created", table_name="review_comments")
    op.drop_table("review_comments")
    op.drop_table("run_explanations")

    op.drop_column("experiments", "decided_at")
    op.drop_column("experiments", "claimed_at")
    op.drop_constraint(
        op.f("fk_experiments_review_assignee_id_users"), "experiments", type_="foreignkey"
    )
    op.drop_column("experiments", "review_assignee_id")
    op.drop_column("experiments", "submission_note")

    op.execute(
        sa.text(
            "UPDATE protocols SET body = '{}'::jsonb, body_sha256 = :sha"
            " WHERE id = CAST(:id AS uuid)"
        ).bindparams(sha=OLD_DEV_OPEN_BODY_SHA256, id=DEV_OPEN_ID)
    )
    op.drop_column("protocols", "created_at")

    bind = op.get_bind()
    for name in ("comment_target_type", "report_status", "model_verdict", "case_verdict_kind"):
        postgresql.ENUM(name=name).drop(bind)
