"""App FastAPI của AdverTest."""

from __future__ import annotations

from importlib.metadata import version

from fastapi import FastAPI

from backend.app.api import health, public, worker
from backend.app.api.errors import install_error_handlers


def create_app() -> FastAPI:
    app = FastAPI(title="AdverTest API", version=version("advertest"))
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(public.router)
    app.include_router(public.verify_router)
    app.include_router(worker.router)
    return app


app = create_app()
