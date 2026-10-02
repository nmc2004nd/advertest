"""Phase 8 Group 2: `runs.git_dirty` (requirements.md Phase 8, Gửi duyệt: `forbid_dirty_runs`).

Giá trị lấy từ `RunStartRequest.fingerprint_inputs.git_dirty` khi run bắt đầu (cả run trúng cache:
cùng fingerprint nên cùng giá trị). Null với run chưa bắt đầu và run bắt đầu trước migration này
(chỉ có ở experiment gắn dev-open, không gửi duyệt được). Quyền của `advertest_app` trên `runs`
đã cấp ở 0001.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("git_dirty", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "git_dirty")
