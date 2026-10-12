"""Nhận xét chi tiết bằng LLM: bảng `experiment_narratives` (chỉ thêm). Mỗi experiment một bản
cho mỗi dữ liệu đầu vào (`input_sha256`) và phiên bản prompt; `advertest_app` chỉ SELECT, INSERT.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "experiment_narratives",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("llm_model", sa.Text(), nullable=False),
        sa.Column("content", JSONB, nullable=False),
        sa.Column("partial", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", TZ, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["experiments.id"],
            name=op.f("fk_experiment_narratives_experiment_id_experiments"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_experiment_narratives_created_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_experiment_narratives")),
        sa.UniqueConstraint(
            "experiment_id",
            "input_sha256",
            "prompt_version",
            name=op.f("uq_experiment_narratives_experiment_id"),
        ),
    )
    op.create_index(
        "ix_experiment_narratives_experiment_id",
        "experiment_narratives",
        ["experiment_id", "created_at"],
        unique=False,
    )
    op.execute("GRANT SELECT, INSERT ON experiment_narratives TO advertest_app")


def downgrade() -> None:
    op.drop_index("ix_experiment_narratives_experiment_id", table_name="experiment_narratives")
    op.drop_table("experiment_narratives")
