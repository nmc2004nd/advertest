"""Phase 3: worker và máy local (lease, checkpoint, cache, failure case theo contract, dev-open).

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Protocol phát triển (requirements.md Phase 3, mục Protocol phát triển): id cố định để CLI và
# test tham chiếu (`content_id(sha256_of({"protocol": "dev-open"}))`); không có người tạo, body
# rỗng (không ràng buộc attack).
DEV_OPEN_ID = "2edcdef5-0d3a-5d5f-98ac-b02637fa6718"
DEV_OPEN_BODY_SHA256 = "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"  # {}


def upgrade() -> None:
    # Giá trị enum mới phải được commit trước khi dùng (INSERT dev-open bên dưới).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE protocol_status ADD VALUE IF NOT EXISTS 'dev'")

    # protocols: dev-open không có người tạo; protocol thật vẫn bắt buộc có.
    op.alter_column("protocols", "created_by", existing_type=sa.Uuid(), nullable=True)
    op.create_check_constraint(
        "creator_unless_dev", "protocols", "created_by IS NOT NULL OR status = 'dev'"
    )
    op.execute(
        "INSERT INTO protocols (id, name, version, body, body_sha256, status, created_by)"
        f" VALUES ('{DEV_OPEN_ID}', 'dev-open', 1, '{{}}'::jsonb, '{DEV_OPEN_BODY_SHA256}',"
        " 'dev', NULL)"
    )

    # experiments: lease, thời gian xử lý cộng dồn, tham số inference và số failure case.
    op.add_column("experiments", sa.Column("lease_id", sa.Uuid(), nullable=True))
    op.add_column(
        "experiments",
        sa.Column(
            "processing_seconds_used",
            sa.Numeric(precision=18, scale=6),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "experiments",
        sa.Column("inference_params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("experiments", sa.Column("failure_cases_per_run", sa.Integer(), nullable=True))

    # runs: fingerprint do worker tính lúc start; cache; checkpoint.
    op.alter_column("runs", "fingerprint", existing_type=sa.String(length=64), nullable=True)
    op.add_column("runs", sa.Column("cached_from_run_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_runs_cached_from_run_id_runs"), "runs", "runs", ["cached_from_run_id"], ["id"]
    )
    op.add_column("runs", sa.Column("checkpoint_key", sa.Text(), nullable=True))
    op.add_column("runs", sa.Column("checkpoint_batch_index", sa.Integer(), nullable=True))
    # Thứ tự chạy trong experiment (WorkerJobBundle.runs theo thứ tự này).
    op.add_column(
        "runs", sa.Column("ordinal", sa.Integer(), server_default=sa.text("0"), nullable=False)
    )
    op.create_index(op.f("ix_runs_fingerprint"), "runs", ["fingerprint"])

    # failure_cases theo FailureCaseRecord (contract Phase 2-3).
    op.drop_column("failure_cases", "artifact_uri")
    op.drop_column("failure_cases", "thumbnail_uri")
    op.drop_column("failure_cases", "details")
    op.add_column("failure_cases", sa.Column("fingerprint", sa.String(length=64), nullable=False))
    op.add_column("failure_cases", sa.Column("rank", sa.Integer(), nullable=False))
    op.add_column("failure_cases", sa.Column("lost_objects", sa.Integer(), nullable=False))
    op.add_column("failure_cases", sa.Column("new_false_positives", sa.Integer(), nullable=False))
    op.add_column(
        "failure_cases",
        sa.Column("detections", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.add_column(
        "failure_cases",
        sa.Column("artifacts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_unique_constraint(
        op.f("uq_failure_cases_run_id"), "failure_cases", ["run_id", "rank"]
    )

    # slices: khóa MinIO slices/<slice_sha256>.json.
    op.add_column("slices", sa.Column("slice_sha256", sa.String(length=64), nullable=True))

    # cost_profiles: môi trường đo; giữ lịch sử, profile mới nhất thắng.
    op.add_column(
        "cost_profiles",
        sa.Column("environment", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    # Bảng cũ, quyền đã cấp ở 0001; migration này không tạo bảng mới.


def downgrade() -> None:
    op.drop_column("cost_profiles", "environment")
    op.drop_column("slices", "slice_sha256")

    op.execute("DELETE FROM failure_cases")
    op.drop_constraint(op.f("uq_failure_cases_run_id"), "failure_cases", type_="unique")
    for column in (
        "artifacts",
        "detections",
        "new_false_positives",
        "lost_objects",
        "rank",
        "fingerprint",
    ):
        op.drop_column("failure_cases", column)
    op.add_column(
        "failure_cases",
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.add_column("failure_cases", sa.Column("thumbnail_uri", sa.Text(), nullable=False))
    op.add_column("failure_cases", sa.Column("artifact_uri", sa.Text(), nullable=False))

    op.drop_index(op.f("ix_runs_fingerprint"), table_name="runs")
    op.drop_column("runs", "ordinal")
    op.drop_column("runs", "checkpoint_batch_index")
    op.drop_column("runs", "checkpoint_key")
    op.drop_constraint(op.f("fk_runs_cached_from_run_id_runs"), "runs", type_="foreignkey")
    op.drop_column("runs", "cached_from_run_id")
    op.execute("DELETE FROM runs WHERE fingerprint IS NULL")
    op.alter_column("runs", "fingerprint", existing_type=sa.String(length=64), nullable=False)

    op.drop_column("experiments", "failure_cases_per_run")
    op.drop_column("experiments", "inference_params")
    op.drop_column("experiments", "processing_seconds_used")
    op.drop_column("experiments", "lease_id")

    # Bỏ protocol dev (và experiment gắn với nó) rồi dựng lại enum không có 'dev'.
    op.execute(
        "DELETE FROM runs WHERE experiment_id IN (SELECT e.id FROM experiments e"
        " JOIN protocols p ON p.id = e.protocol_id WHERE p.status = 'dev')"
    )
    op.execute(
        "DELETE FROM experiments WHERE protocol_id IN (SELECT id FROM protocols"
        " WHERE status = 'dev')"
    )
    op.execute("DELETE FROM protocols WHERE status = 'dev'")
    op.drop_constraint(op.f("ck_protocols_creator_unless_dev"), "protocols", type_="check")
    op.alter_column("protocols", "created_by", existing_type=sa.Uuid(), nullable=False)
    op.execute("ALTER TABLE protocols ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TYPE protocol_status RENAME TO protocol_status_old")
    op.execute("CREATE TYPE protocol_status AS ENUM ('active', 'retired')")
    op.execute(
        "ALTER TABLE protocols ALTER COLUMN status TYPE protocol_status"
        " USING status::text::protocol_status"
    )
    op.execute("ALTER TABLE protocols ALTER COLUMN status SET DEFAULT 'active'")
    op.execute("DROP TYPE protocol_status_old")
