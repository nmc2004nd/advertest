"""Fixture cho test nghiệm thu Phase R3 (validation.md Phase R3, Automated Tests).

Dùng lại hạ tầng có sẵn thay vì chép lại:
- Phase 5 (qua Phase 8): DB tạm đã migrate và seed, MinIO, API thật qua TestClient (đồng hồ giả),
  worker CPU thật, slice KITTI 5 ảnh, YOLOv8n.
- Phase 8: `Flow` (protocol → experiment → gửi duyệt → review → approve → report) và kho report.
- Phase R2: DB dựng sạch bằng `DROP OWNED BY`, worker công cụ giả lập qua API nội bộ, upload model.

Interface mà test gọi trực tiếp ghi ở requirements.md Phase R3, mục "Chốt ở Group 0".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import Engine

from backend.app.api import public
from backend.app.storage import Buckets

from ._load import load

P8 = load("phase_08")
R2 = load("phase_r2")
P5 = P8.P5

# Fixture dùng chung (gán lại để pytest thấy trong thư mục này).
alembic_config = P5.alembic_config
app_engine = P5.app_engine
cli_env = P5.cli_env
world = P5.world
fresh_fingerprint = P5.fresh_fingerprint
owner_engine = R2.owner_engine
buckets = R2.buckets
tool_worker = R2.tool_worker
report_stores = P8.report_stores
flow = P8.flow

# Hàm tiện ích.
post = P5.post
ok = P5.ok
error = P5.error
csrf = P5.csrf
DEV_OPEN = P5.DEV_OPEN
Flow = P8.Flow
detail = P8.detail
ToolWorker = R2.ToolWorker
audit_entries = R2.audit_entries
count_rows = R2.count_rows
unique = R2.unique
spec_of = R2.spec_of
create_protocol = R2.create_protocol
required_grid = R2.required_grid
max_drop = R2.max_drop
register_onnx = R2.register_onnx
finish_model_check = R2.finish_model_check
spec_check_report = R2.spec_check_report
KITTI_IMAGE = R2.KITTI_IMAGE
ONNX_WEIGHTS = R2.ONNX_WEIGHTS


@pytest.fixture
def report_app(monkeypatch: pytest.MonkeyPatch, report_stores: dict[str, Any]) -> None:
    """Như `report_app` của Phase 8 nhưng không autouse (R3 có test không cần DB): nối kho report
    vào app mà `P5.Api.app()` dựng."""
    original = P5.create_app

    def create_app() -> FastAPI:
        app: FastAPI = original()
        app.dependency_overrides[public.get_report_stores] = lambda: report_stores["current"]
        return app

    monkeypatch.setattr(P5, "create_app", create_app)


@pytest.fixture
def api(
    report_app: None,
    app_engine: Engine,
    buckets: Buckets,
    cli_env: dict[str, str],
    world: Any,
    tmp_path: Path,
) -> Any:
    return P5.Api(app_engine, buckets, cli_env, world, tmp_path)
