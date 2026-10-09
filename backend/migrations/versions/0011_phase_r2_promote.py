"""Phase R2 Group 1: `experiments.promoted_from` (requirements.md Phase R2, Mode và nâng lên chính
thức). Experiment Khám phá nguồn khi nâng lên chính thức, chỉ để truy vết; null với experiment tạo
trực tiếp. Phần còn lại của DB R2 (catalog, model, job công cụ, thử nhanh) ở migration của Group 4.
Quyền của `advertest_app` trên `experiments` đã cấp ở 0001.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("experiments", sa.Column("promoted_from", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_experiments_promoted_from_experiments"),
        "experiments",
        "experiments",
        ["promoted_from"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_experiments_promoted_from_experiments"), "experiments", type_="foreignkey"
    )
    op.drop_column("experiments", "promoted_from")
