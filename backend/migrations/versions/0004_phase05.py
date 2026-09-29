"""Phase 5: giới hạn thời gian tối đa của compute target; tên, nguồn nhân bản, thời điểm tạo và
kết thúc của experiment; hàng đợi email (requirements.md Phase 5, Thay đổi DB).

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)
EMAIL_STATUS = sa.Enum("pending", "sent", "failed", name="email_status")

# Tên mặc định của experiment (requirements.md Phase 5, Kiểm tra khi tạo): `{row}` là bản ghi.
DEFAULT_NAME_SQL = """(
    SELECT mo.name || ' · ' || s.name || ' · '
           || to_char(COALESCE({row}.created_at, now()) AT TIME ZONE 'UTC', 'YYYY-MM-DD')
    FROM model_versions mv JOIN models mo ON mo.id = mv.model_id, slices s
    WHERE mv.id = {row}.model_version_id AND s.id = {row}.slice_id
)"""
DEFAULT_NAME_FUNCTION = f"""
CREATE FUNCTION experiment_default_name() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.name IS NULL THEN
        NEW.name := {DEFAULT_NAME_SQL.format(row="NEW")};
    END IF;
    RETURN NEW;
END
$$
"""


def upgrade() -> None:
    # compute_targets: trần mà người dùng được chọn (mặc định 8 giờ, kickoff Phase 5).
    op.add_column(
        "compute_targets",
        sa.Column(
            "max_time_limit_s", sa.Integer(), server_default=sa.text("28800"), nullable=False
        ),
    )
    op.create_check_constraint(
        "default_within_max",
        "compute_targets",
        "default_time_limit_s <= max_time_limit_s",
    )

    # experiments.created_at: experiment cũ (Phase 3) lấy thời điểm gửi.
    op.add_column(
        "experiments", sa.Column("created_at", TZ, server_default=sa.text("now()"), nullable=True)
    )
    op.execute("UPDATE experiments SET created_at = submitted_at WHERE submitted_at IS NOT NULL")
    op.alter_column("experiments", "created_at", nullable=False)
    op.create_index("ix_experiments_created_at_id", "experiments", ["created_at", "id"])

    # experiments.name: bỏ trống thì DB đặt `<model> · <slice> · <YYYY-MM-DD UTC>` bằng trigger
    # (một quy tắc cho API, CLI và mọi INSERT); experiment cũ điền theo cùng quy tắc.
    op.add_column("experiments", sa.Column("name", sa.Text(), nullable=True))
    op.execute(DEFAULT_NAME_FUNCTION)
    op.execute(
        "CREATE TRIGGER experiments_default_name BEFORE INSERT ON experiments"
        " FOR EACH ROW EXECUTE FUNCTION experiment_default_name()"
    )
    op.execute(f"UPDATE experiments e SET name = {DEFAULT_NAME_SQL.format(row='e')}")
    op.alter_column("experiments", "name", nullable=False)

    op.add_column("experiments", sa.Column("cloned_from", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_experiments_cloned_from_experiments"),
        "experiments",
        "experiments",
        ["cloned_from"],
        ["id"],
    )

    # experiments.finished_at: experiment cũ đã kết thúc lấy thời điểm run cuối cùng xong.
    op.add_column("experiments", sa.Column("finished_at", TZ, nullable=True))
    op.execute(
        """
        UPDATE experiments e
        SET finished_at = GREATEST(
            e.created_at,
            COALESCE(
                (SELECT max(r.finished_at) FROM runs r WHERE r.experiment_id = e.id),
                e.submitted_at,
                e.created_at
            )
        )
        WHERE e.status NOT IN ('draft', 'queued', 'running')
        """
    )

    op.create_table(
        "email_outbox",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("to", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("status", EMAIL_STATUS, server_default=sa.text("'pending'"), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", TZ, server_default=sa.text("now()"), nullable=False),
        # Lần gửi tiếp theo (backoff của Group 3, quyết định Group 1).
        sa.Column("next_attempt_at", TZ, server_default=sa.text("now()"), nullable=False),
        sa.Column("sent_at", TZ, nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_outbox")),
    )
    op.create_index(
        "ix_email_outbox_status_next_attempt_at", "email_outbox", ["status", "next_attempt_at"]
    )
    # Tác vụ gửi đánh dấu trạng thái bằng UPDATE; không xóa email.
    op.execute("GRANT SELECT, INSERT, UPDATE ON email_outbox TO advertest_app")


def downgrade() -> None:
    op.drop_table("email_outbox")
    EMAIL_STATUS.drop(op.get_bind())
    op.drop_column("experiments", "finished_at")
    op.drop_constraint(
        op.f("fk_experiments_cloned_from_experiments"), "experiments", type_="foreignkey"
    )
    op.drop_column("experiments", "cloned_from")
    op.execute("DROP TRIGGER experiments_default_name ON experiments")
    op.execute("DROP FUNCTION experiment_default_name()")
    op.drop_column("experiments", "name")
    op.drop_index("ix_experiments_created_at_id", table_name="experiments")
    op.drop_column("experiments", "created_at")
    op.drop_constraint(
        op.f("ck_compute_targets_default_within_max"), "compute_targets", type_="check"
    )
    op.drop_column("compute_targets", "max_time_limit_s")
