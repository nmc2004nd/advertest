"""Phase 5 Group 2: điền lại `experiments.finished_at` cho experiment đã kết thúc sau migration
0004 nhưng trước khi API đặt `finished_at` (plan.md task 13, review Group 1). Cùng quy tắc với
0004: thời điểm run cuối cùng xong, không sớm hơn `created_at`.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-30
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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
        WHERE e.status NOT IN ('draft', 'queued', 'running') AND e.finished_at IS NULL
        """
    )


def downgrade() -> None:
    # Chỉ điền dữ liệu; không có gì để hoàn tác (0004 downgrade bỏ cả cột).
    pass
