"""Phase R3 (đề xuất contract 002): lưu trữ model.

`model_versions.archived_at`: model đã lưu trữ không chọn được cho experiment, thử nhanh hay class
mapping mới; experiment và report cũ vẫn tra được. Không đổi quyền: `advertest_app` đã có
SELECT, INSERT, UPDATE, DELETE trên `model_versions` từ migration 0001.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "model_versions", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("model_versions", "archived_at")
