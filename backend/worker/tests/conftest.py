"""Fixture cho test end-to-end của worker: Postgres và MinIO thật (`make test-db`), API chạy
trong tiến trình (FastAPI qua TestClient). Dùng lại fixture DB của test backend."""

from __future__ import annotations

from backend.app.tests.db.conftest import alembic_config, app_engine, buckets, owner_engine

__all__ = ["alembic_config", "app_engine", "buckets", "owner_engine"]
