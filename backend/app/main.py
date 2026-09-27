"""App FastAPI của AdverTest."""

from __future__ import annotations

from importlib.metadata import version

from fastapi import FastAPI

from backend.app.api import public, worker


def create_app() -> FastAPI:
    app = FastAPI(title="AdverTest API", version=version("advertest"))
    app.include_router(public.router)
    app.include_router(public.verify_router)
    app.include_router(worker.router)
    return app


app = create_app()
