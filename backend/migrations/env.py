"""Môi trường Alembic: chạy migration bằng role advertest_owner.

URL lấy từ MIGRATION_DATABASE_URL, tách khỏi DATABASE_URL (role advertest_app của ứng dụng).
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context

from backend.app.db.engine import database_url, make_engine
from backend.app.db.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
MIGRATION_URL_ENV = "MIGRATION_DATABASE_URL"


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(MIGRATION_URL_ENV), target_metadata=target_metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine(config.attributes.get("url") or database_url(MIGRATION_URL_ENV))
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
