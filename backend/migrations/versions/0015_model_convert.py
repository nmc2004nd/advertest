"""Phase R3 (đề xuất contract 003): job công cụ `model_convert` đổi `.pt` sang safetensors trong
sandbox chuyển đổi. Trạng thái và kết quả nằm trong `tool_jobs` (payload, result), không cần bảng
mới; `advertest_app` đã có quyền trên `tool_jobs`.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE tool_job_kind ADD VALUE IF NOT EXISTS 'model_convert'")


def downgrade() -> None:
    # Postgres không bỏ được một giá trị enum: xóa job model_convert rồi dựng lại kiểu.
    op.execute("DELETE FROM tool_jobs WHERE kind = 'model_convert'")
    op.execute("ALTER TYPE tool_job_kind RENAME TO tool_job_kind_old")
    op.execute("CREATE TYPE tool_job_kind AS ENUM ('spec_check', 'model_check', 'quick_try')")
    op.execute(
        "ALTER TABLE tool_jobs ALTER COLUMN kind TYPE tool_job_kind USING kind::text::tool_job_kind"
    )
    op.execute("DROP TYPE tool_job_kind_old")
