"""Phase 6 Group 5: patch đã train, chi phí train, làm mờ và ảnh thứ ba của failure case, giai
đoạn của run (requirements.md Phase 6; plan task 25, 26, 28).

- Bảng `patches`: mỗi khóa patch một dòng; `artifact` (PatchArtifact) khi đã đăng ký,
  `checkpoint_key` khi đang train dở (xóa khi đăng ký). Chỉ thêm và cập nhật, không xóa.
- `cost_profiles.sec_per_image_iteration`.
- `failure_cases.anonymization` (CaseAnonymization, null với case cũ), `perturbation_kind`.
- `runs.phase`, `iterations_done`, `iterations_total` (tiến độ train patch cho RunView).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "patches",
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("attack_spec_id", sa.Uuid(), nullable=False),
        sa.Column("area_ratio", sa.Float(), nullable=False),
        sa.Column("artifact", JSONB(), nullable=True),
        sa.Column("checkpoint_key", sa.Text(), nullable=True),
        sa.Column("created_at", TZ, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TZ, server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_patches")),
        sa.ForeignKeyConstraint(
            ["attack_spec_id"], ["attack_specs.id"], name=op.f("fk_patches_attack_spec_id")
        ),
        sa.CheckConstraint(
            "artifact IS NULL OR checkpoint_key IS NULL", name=op.f("ck_patches_done_no_checkpoint")
        ),
    )
    # Patch đã đăng ký là bất biến và được dùng lại: app không xóa.
    op.execute("GRANT SELECT, INSERT, UPDATE ON patches TO advertest_app")

    op.add_column("cost_profiles", sa.Column("sec_per_image_iteration", sa.Float(), nullable=True))
    op.add_column("failure_cases", sa.Column("anonymization", JSONB(), nullable=True))
    op.add_column("failure_cases", sa.Column("perturbation_kind", sa.Text(), nullable=True))
    op.add_column("runs", sa.Column("phase", sa.Text(), nullable=True))
    op.add_column("runs", sa.Column("iterations_done", sa.Integer(), nullable=True))
    op.add_column("runs", sa.Column("iterations_total", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "iterations_total")
    op.drop_column("runs", "iterations_done")
    op.drop_column("runs", "phase")
    op.drop_column("failure_cases", "perturbation_kind")
    op.drop_column("failure_cases", "anonymization")
    op.drop_column("cost_profiles", "sec_per_image_iteration")
    op.drop_table("patches")
