"""Kết nối Postgres. URL lấy từ biến môi trường, không đặt cứng trong code.

DATABASE_URL: role advertest_app (ứng dụng, seed). MIGRATION_DATABASE_URL: role advertest_owner
(chỉ Alembic dùng).
"""

from __future__ import annotations

import os

from sqlalchemy import Engine, create_engine


def database_url(env_var: str = "DATABASE_URL") -> str:
    url = os.environ.get(env_var)
    if not url:
        raise RuntimeError(f"Thiếu biến môi trường {env_var} (ví dụ postgresql+psycopg://...)")
    return url


def make_engine(url: str | None = None) -> Engine:
    return create_engine(url or database_url(), pool_pre_ping=True)
