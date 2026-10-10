"""`get_storage` thiếu cấu hình MinIO trả 500 `internal_error` (không lộ chi tiết), không ném
`RuntimeError` ra ngoài; override chuẩn của FastAPI vẫn thay được storage (review R2 G4 #2)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Any, cast

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from backend.app.api.deps import Storage, get_storage
from backend.app.api.errors import install_error_handlers


@pytest.fixture
def no_minio(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in ("MINIO_ENDPOINT", "MINIO_PUBLIC_ENDPOINT"):
        monkeypatch.delenv(name, raising=False)
    get_storage.cache_clear()
    yield
    get_storage.cache_clear()


def _app() -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/uses-storage")
    def uses_storage(stores: Annotated[Storage, Depends(get_storage)]) -> dict[str, str]:
        return {"presigner": type(stores.presigner).__name__}

    return app


@pytest.mark.usefixtures("no_minio")
def test_missing_minio_is_internal_error_without_detail() -> None:
    response = TestClient(_app()).get("/uses-storage")
    assert response.status_code == 500
    assert response.json()["error"] == {"code": "internal_error", "message": "Lỗi máy chủ"}
    assert "MINIO" not in response.text


@pytest.mark.usefixtures("no_minio")
def test_override_replaces_storage() -> None:
    app = _app()
    fake = Storage(buckets=cast(Any, None), presigner=cast(Any, "p"))
    app.dependency_overrides[get_storage] = lambda: fake
    response = TestClient(app).get("/uses-storage")
    assert response.status_code == 200
    assert response.json() == {"presigner": "str"}
