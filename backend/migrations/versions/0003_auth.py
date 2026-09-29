"""Phase 4: phiên đăng nhập, token đặt lại mật khẩu, sự kiện đăng nhập, cột mới của users.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-29
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)


def _id() -> sa.Column[uuid.UUID]:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def upgrade() -> None:
    op.add_column("users", sa.Column("reject_reason", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("disabled_at", TZ, nullable=True))

    op.create_table(
        "sessions",
        _id(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("expires_at", TZ, nullable=False),
        sa.Column("last_seen_at", TZ, nullable=False),
        sa.Column("revoked_at", TZ, nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("token_sha256", name=op.f("uq_sessions_token_sha256")),
    )
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"])

    op.create_table(
        "password_reset_tokens",
        _id(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", TZ, server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", TZ, nullable=False),
        sa.Column("used_at", TZ, nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_password_reset_tokens_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_password_reset_tokens_created_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_reset_tokens")),
        sa.UniqueConstraint("token_sha256", name=op.f("uq_password_reset_tokens_token_sha256")),
    )
    op.create_index(op.f("ix_password_reset_tokens_user_id"), "password_reset_tokens", ["user_id"])

    op.create_table(
        "auth_events",
        _id(),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("ip", sa.Text(), nullable=True),
        sa.Column(
            "kind",
            sa.Enum("login_success", "login_failed", "logout", name="auth_event_kind"),
            nullable=False,
        ),
        sa.Column("created_at", TZ, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_events")),
    )
    op.create_index(op.f("ix_auth_events_email"), "auth_events", ["email"])
    op.create_index(op.f("ix_auth_events_ip"), "auth_events", ["ip"])
    op.create_index(op.f("ix_auth_events_created_at"), "auth_events", ["created_at"])

    # Phiên và token đặt lại: thu hồi, đánh dấu đã dùng bằng UPDATE, không xóa.
    # auth_events: chỉ thêm.
    op.execute("GRANT SELECT, INSERT, UPDATE ON sessions TO advertest_app")
    op.execute("GRANT SELECT, INSERT, UPDATE ON password_reset_tokens TO advertest_app")
    op.execute("GRANT SELECT, INSERT ON auth_events TO advertest_app")


def downgrade() -> None:
    op.drop_table("auth_events")
    op.execute("DROP TYPE auth_event_kind")
    op.drop_table("password_reset_tokens")
    op.drop_table("sessions")
    op.drop_column("users", "disabled_at")
    op.drop_column("users", "reject_reason")
