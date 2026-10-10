"""Phase R2 Group 4: vòng đời catalog attack, model qua web, job công cụ, thử nhanh
(requirements.md Phase R2, mục DB).

- `attack_specs`: `status` thay `is_active` (backfill: `active`, hoặc `retired` khi
  `is_active = false`), `metadata` (ngoài `spec_sha256`), người tạo/duyệt, kết quả `spec_check`.
  `status` mặc định `active` cho bản ghi chèn qua seed hoặc CLI; spec tạo qua API ghi rõ `draft`.
- `model_versions`: `status` (backfill `ready`) và kết quả `model_check`.
- `tool_jobs`: hàng đợi job công cụ của worker `--tools`; `attempts` đếm số lần lease (mất lease
  lần thứ 3 thì `failed`).
- `quick_tries`: một lượt thử nhanh; object MinIO dưới `quick-tries/<id>/`, dọn sau `expires_at`.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())

ENUMS = {
    "attack_spec_status": (
        "draft",
        "checking",
        "check_failed",
        "pending_approval",
        "active",
        "retired",
    ),
    "model_status": ("checking", "check_failed", "ready"),
    "tool_job_kind": ("spec_check", "model_check", "quick_try"),
    "tool_job_status": ("queued", "running", "completed", "failed"),
}


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind)

    # ------------------------------------------------------------ attack_specs
    op.add_column(
        "attack_specs",
        sa.Column("status", _enum("attack_spec_status"), server_default="active", nullable=False),
    )
    op.execute("UPDATE attack_specs SET status = 'retired' WHERE NOT is_active")
    op.drop_column("attack_specs", "is_active")
    op.add_column("attack_specs", sa.Column("metadata", JSONB, nullable=True))
    op.add_column("attack_specs", sa.Column("check", JSONB, nullable=True))
    op.add_column("attack_specs", sa.Column("created_by", sa.Uuid(), nullable=True))
    op.add_column("attack_specs", sa.Column("approved_by", sa.Uuid(), nullable=True))
    op.add_column("attack_specs", sa.Column("approved_at", TZ, nullable=True))
    for column in ("created_by", "approved_by"):
        op.create_foreign_key(
            op.f(f"fk_attack_specs_{column}_users"), "attack_specs", "users", [column], ["id"]
        )

    # ------------------------------------------------------------ model_versions
    op.add_column(
        "model_versions",
        sa.Column("status", _enum("model_status"), server_default="ready", nullable=False),
    )
    op.add_column("model_versions", sa.Column("check", JSONB, nullable=True))

    # ------------------------------------------------------------ tool_jobs
    op.create_table(
        "tool_jobs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("kind", _enum("tool_job_kind"), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("status", _enum("tool_job_status"), server_default="queued", nullable=False),
        sa.Column("lease_id", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", TZ, nullable=True),
        sa.Column("leased_by", sa.Uuid(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("result", JSONB, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", TZ, server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", TZ, nullable=True),
        sa.ForeignKeyConstraint(
            ["leased_by"],
            ["compute_targets.id"],
            name=op.f("fk_tool_jobs_leased_by_compute_targets"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_tool_jobs_created_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool_jobs")),
    )
    op.create_index(
        op.f("ix_tool_jobs_status"), "tool_jobs", ["status", "created_at"], unique=False
    )

    # ------------------------------------------------------------ quick_tries
    op.create_table(
        "quick_tries",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("tool_job_id", sa.Uuid(), nullable=False),
        sa.Column("model_version_id", sa.Uuid(), nullable=False),
        sa.Column("attack_spec_id", sa.Uuid(), nullable=False),
        sa.Column("preset", sa.Text(), nullable=False),
        sa.Column("input_uri", sa.Text(), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("expires_at", TZ, nullable=False),
        sa.Column("deleted_at", TZ, nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_quick_tries_owner_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["tool_job_id"], ["tool_jobs.id"], name=op.f("fk_quick_tries_tool_job_id_tool_jobs")
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_versions.id"],
            name=op.f("fk_quick_tries_model_version_id_model_versions"),
        ),
        sa.ForeignKeyConstraint(
            ["attack_spec_id"],
            ["attack_specs.id"],
            name=op.f("fk_quick_tries_attack_spec_id_attack_specs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quick_tries")),
        sa.UniqueConstraint("tool_job_id", name=op.f("uq_quick_tries_tool_job_id")),
    )
    op.create_index(op.f("ix_quick_tries_owner_id"), "quick_tries", ["owner_id"], unique=False)

    # Không DELETE: lượt thử nhanh đã dọn chỉ đặt deleted_at.
    for table in ("tool_jobs", "quick_tries"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO advertest_app")


def downgrade() -> None:
    op.drop_index(op.f("ix_quick_tries_owner_id"), table_name="quick_tries")
    op.drop_table("quick_tries")
    op.drop_index(op.f("ix_tool_jobs_status"), table_name="tool_jobs")
    op.drop_table("tool_jobs")

    op.drop_column("model_versions", "check")
    op.drop_column("model_versions", "status")

    for column in ("approved_by", "created_by"):
        op.drop_constraint(
            op.f(f"fk_attack_specs_{column}_users"), "attack_specs", type_="foreignkey"
        )
    for column in ("approved_at", "approved_by", "created_by", "check", "metadata"):
        op.drop_column("attack_specs", column)
    op.add_column(
        "attack_specs",
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.execute("UPDATE attack_specs SET is_active = (status = 'active')")
    op.drop_column("attack_specs", "status")

    bind = op.get_bind()
    for name in reversed(ENUMS):
        postgresql.ENUM(name=name).drop(bind)
