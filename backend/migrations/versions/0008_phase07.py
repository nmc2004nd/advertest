"""Phase 7 Group 4: tự tìm ngưỡng (requirements.md Phase 7; plan task 18a, 22, 22b).

- `runs.scope` (`full` | `subset`, mặc định `full`), `runs.search_order` (thứ tự điểm của tìm
  ngưỡng; null với run quét lưới), `runs.predictions_key` (file prediction theo ảnh).
  Run `subset` phải có `search_order`; một attack không có hai run cùng `search_order` trong một
  experiment.
- `search_results`: mỗi (experiment, attack) một dòng (`SearchResult` mới nhất), `updated_at`.

Không có bảng mới: quyền của `advertest_app` trên `runs` (không xóa) và `search_results` đã cấp ở
0001.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column(
        "runs", sa.Column("scope", sa.Text(), server_default=sa.text("'full'"), nullable=False)
    )
    op.add_column("runs", sa.Column("search_order", sa.Integer(), nullable=True))
    op.add_column("runs", sa.Column("predictions_key", sa.Text(), nullable=True))
    op.create_check_constraint(op.f("ck_runs_scope_value"), "runs", "scope IN ('full', 'subset')")
    op.create_check_constraint(
        op.f("ck_runs_subset_has_search_order"),
        "runs",
        "scope = 'full' OR search_order IS NOT NULL",
    )
    op.create_index(
        "uq_runs_search_order",
        "runs",
        ["experiment_id", "attack_spec_id", "search_order"],
        unique=True,
        postgresql_where=sa.text("search_order IS NOT NULL"),
    )
    op.add_column(
        "search_results",
        sa.Column("updated_at", TZ, server_default=sa.text("now()"), nullable=False),
    )
    op.create_unique_constraint(
        op.f("uq_search_results_experiment_attack"),
        "search_results",
        ["experiment_id", "attack_spec_id"],
    )


def downgrade() -> None:
    # Dữ liệu SearchResult chỉ có từ Phase 7: xóa để downgrade xa hơn (0002 xóa experiment của
    # protocol dev) không vướng khóa ngoại.
    op.execute("DELETE FROM search_results")
    op.drop_constraint(
        op.f("uq_search_results_experiment_attack"), "search_results", type_="unique"
    )
    op.drop_column("search_results", "updated_at")
    op.drop_index("uq_runs_search_order", table_name="runs")
    op.drop_constraint(op.f("ck_runs_subset_has_search_order"), "runs", type_="check")
    op.drop_constraint(op.f("ck_runs_scope_value"), "runs", type_="check")
    op.drop_column("runs", "predictions_key")
    op.drop_column("runs", "search_order")
    op.drop_column("runs", "scope")
