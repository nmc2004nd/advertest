"""Phase 6 Group 0: `attack_access` thêm `not_applicable` cho corruption và occlusion (contract
`AttackAccess`, requirements.md Phase 6 mục Contract). Seed catalog Phase 6 cần giá trị này.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-01
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ADD VALUE không chạy được trong transaction trên mọi phiên bản Postgres.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE attack_access ADD VALUE IF NOT EXISTS 'not_applicable'")


def downgrade() -> None:
    # Postgres không bỏ được giá trị enum; bỏ spec dùng giá trị này rồi tạo lại kiểu.
    op.execute("DELETE FROM attack_specs WHERE access = 'not_applicable'")
    op.execute("ALTER TYPE attack_access RENAME TO attack_access_old")
    op.execute("CREATE TYPE attack_access AS ENUM ('white_box', 'black_box')")
    op.execute(
        "ALTER TABLE attack_specs ALTER COLUMN access TYPE attack_access"
        " USING access::text::attack_access"
    )
    op.execute("DROP TYPE attack_access_old")
