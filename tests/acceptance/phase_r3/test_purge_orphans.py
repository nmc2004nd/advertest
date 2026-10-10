"""validation.md Phase R3, Group 1 — Dọn object MinIO mồ côi của thử nhanh
(`test_purge_orphans.py`, marker `db`).

`backend.app.services.quick_tries.purge_orphans(session, buckets, now) -> int` xóa object dưới
`quick-tries/<id>/` khi không có dòng `quick_tries` với `id` đó, hoặc dòng đã có `deleted_at`,
**và** object cũ hơn 30 phút so với `now` (theo `LastModified` của MinIO). Giữ object mới hơn
và object của lượt còn hạn. Trả số object đã xóa.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.storage import BUCKET_ARTIFACTS, make_s3_client

from .conftest import KITTI_IMAGE, ToolWorker, csrf, spec_of

pytestmark = pytest.mark.db

AGE = timedelta(minutes=30)


def _s3(api: Any) -> Any:
    env = api.cli_env
    return make_s3_client(env["MINIO_ENDPOINT"], env["MINIO_ACCESS_KEY"], env["MINIO_SECRET_KEY"])


def _keys(api: Any, prefix: str) -> list[str]:
    response = _s3(api).list_objects_v2(Bucket=BUCKET_ARTIFACTS, Prefix=prefix)
    return [obj["Key"] for obj in response.get("Contents", [])]


def _put(api: Any, key: str) -> None:
    _s3(api).put_object(Bucket=BUCKET_ARTIFACTS, Key=key, Body=b"\x89PNG orphan")


def _purge(api: Any, now: datetime) -> int:
    from backend.app.services.quick_tries import (  # type: ignore[attr-defined,unused-ignore]
        purge_orphans,  # Group 1
    )

    with Session(api.engine) as session, session.begin():
        removed: int = purge_orphans(session, api.buckets, now)
    return removed


def _live_quick_try(api: Any) -> str:
    _, _, engineer = api.user("engineer")
    client: TestClient = engineer
    response = client.post(
        "/quick-tries",
        data={"model_version_id": api.world.model_id, "attack_spec_id": str(spec_of("fog").id)},
        files={"image": ("anh.png", KITTI_IMAGE.read_bytes(), "image/png")},
        headers=csrf(client),
    )
    assert response.status_code == 202, response.text
    quick_try_id: str = response.json()["id"]
    return quick_try_id


def test_orphan_without_row_removed_only_when_old(api: Any, tool_worker: ToolWorker) -> None:
    prefix = f"quick-tries/{uuid4()}/"
    _put(api, prefix + "level_0.png")
    real_now = datetime.now(UTC)

    _purge(api, real_now)  # mới hơn 30 phút: giữ
    assert _keys(api, prefix) == [prefix + "level_0.png"]

    assert _purge(api, real_now + AGE + timedelta(minutes=1)) >= 1
    assert _keys(api, prefix) == []


def test_live_quick_try_objects_kept(api: Any, tool_worker: ToolWorker) -> None:
    quick_try_id = _live_quick_try(api)
    prefix = f"quick-tries/{quick_try_id}/"
    assert _keys(api, prefix)  # ảnh gốc đã lưu khi tạo
    _purge(api, datetime.now(UTC) + AGE + timedelta(minutes=1))
    assert _keys(api, prefix)


def test_late_object_of_purged_quick_try_removed(api: Any, tool_worker: ToolWorker) -> None:
    from backend.app.services.quick_tries import purge_expired  # R2 Group 4

    quick_try_id = _live_quick_try(api)
    prefix = f"quick-tries/{quick_try_id}/"
    api.clock.advance(24 * 3600 + 1)
    with Session(api.engine) as session, session.begin():
        assert purge_expired(session, api.buckets, api.clock()) >= 1
    assert _keys(api, prefix) == []

    # Worker PUT muộn qua presigned URL còn hạn sau khi purge đã xóa prefix (Chốt ở Group 4 R2).
    _put(api, prefix + "level_1.png")
    later = datetime.now(UTC) + AGE + timedelta(minutes=1)
    assert _purge(api, later) >= 1
    assert _keys(api, prefix) == []
