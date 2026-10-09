"""validation.md Phase R2, Group 5 — Worker công cụ (`test_tool_worker.py`, marker `db`).

- `spec_check`, `model_check`, `quick_try` chạy hết vòng qua worker thật (`ToolRunner`, chế độ
  `advertest-worker --tools`) trên fixture; kết quả ghi qua endpoint worker.
- Thứ tự lease: `quick_try` trước job kiểm tra đã xếp trước đó.
- Mất lease → xếp lại, quá 2 lần → `failed`.
- Ảnh kết quả thử nhanh đi qua làm mờ: trong vùng `rule_v1` (mặt người, biển số) ảnh sạch trả về
  khác ảnh letterbox gốc; ngoài vùng gần như giữ nguyên.
- `ModelProvider.get` lỗi trong kiểm gradient → run cần gradient `failed` (`error`), run
  corruption cùng experiment `completed` (tồn đọng R1 Group 5).

Interface (requirements.md Phase R2, Chốt ở Group 0, "Interface cho test nghiệm thu"):
`advertest_worker.tools.ToolRunner(client, cache, device, *, url_http, clock)`, `run_next()`.
"""

from __future__ import annotations

import io
import json
import uuid
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from advertest_contracts.models import AttackSpecAdminView, ModelSummary, QuickTryView
from advertest_worker.cache import JobCache
from advertest_worker.client import WorkerClient
from advertest_worker.job import JobRunner
from ml_core.models.adapter import ModelProvider
from ml_core.preprocess.letterbox import letterbox
from ml_core.privacy.regions import Detection, rule_v1_regions

from .conftest import (
    KITTI_IMAGE,
    ONNX_WEIGHTS,
    P5,
    TORCHVISION_WEIGHTS,
    ToolWorker,
    coco80,
    csrf,
    ok,
    post,
    spec_of,
    unique,
    upload,
)

pytestmark = pytest.mark.db

MOCKS = Path(__file__).resolve().parents[3] / "contracts" / "mocks"
SNOW_LIGHT: dict[str, Any] = json.loads(
    (MOCKS / "attack_spec_create" / "snow_light.json").read_text()
)


def _runner(api: Any, target: Any) -> Any:
    from advertest_worker.tools import ToolRunner  # Group 5

    client = WorkerClient(TestClient(api.app()), target.token, sleep=lambda _s: None)
    return ToolRunner(
        client,
        JobCache(api.tmp / f"tools-{uuid.uuid4().hex[:6]}"),
        "cpu",
        url_http=httpx.Client(timeout=300),
        clock=api.clock,
    )


@pytest.fixture
def setup(api: Any, tool_worker: ToolWorker) -> dict[str, Any]:
    """`tool_worker` dọn job còn sót của test trước; worker thật dùng target riêng."""
    _, _, admin = api.user("admin")
    _, _, engineer = api.user("engineer")
    target = api.target()
    return {"admin": admin, "engineer": engineer, "target": target, "runner": _runner(api, target)}


def _create_spec(admin: TestClient, name: str) -> str:
    body = {"body": {**SNOW_LIGHT["body"], "name": name}, "metadata": SNOW_LIGHT["metadata"]}
    response = post(admin, "/admin/attack-specs", body)
    assert response.status_code == 201, response.text
    spec_id: str = response.json()["id"]
    return spec_id


def _spec_status(admin: TestClient, spec_id: str) -> AttackSpecAdminView:
    page = admin.get("/admin/attack-specs", params={"limit": 200}).json()
    while True:
        for item in page["items"]:
            if item["id"] == spec_id:
                return AttackSpecAdminView.model_validate(item)
        assert page["next_cursor"], spec_id
        page = admin.get(
            "/admin/attack-specs", params={"limit": 200, "cursor": page["next_cursor"]}
        ).json()


def _quick_try(client: TestClient, api: Any, spec: str = "fgsm") -> str:
    response = client.post(
        "/quick-tries",
        data={"model_version_id": api.world.model_id, "attack_spec_id": str(spec_of(spec).id)},
        files={"image": ("anh.png", KITTI_IMAGE.read_bytes(), "image/png")},
        headers=csrf(client),
    )
    assert response.status_code == 202, response.text
    quick_try_id: str = response.json()["id"]
    return quick_try_id


# ---------------------------------------------------------------- spec_check


def test_spec_check_end_to_end(setup: dict[str, Any]) -> None:
    spec_id = _create_spec(setup["admin"], unique("snow_light"))
    assert setup["runner"].run_next()
    view = _spec_status(setup["admin"], spec_id)
    assert view.status == "pending_approval", view.check
    assert view.check is not None and view.check.passed
    assert [i.name.value for i in view.check.items] == [
        "runs", "value_range", "pad_unchanged", "identity", "batch_invariant", "norm_bound",
        "deterministic",
    ]  # fmt: skip
    assert str(view.check.worker_target_id) == setup["target"].id
    assert setup["runner"].run_next() is False  # hết job


# ---------------------------------------------------------------- model_check


def _register(admin: TestClient, path: Path, framework: str, architecture: str, names: list[str],
              content: bytes | None = None) -> str:  # fmt: skip
    data = content if content is not None else path.read_bytes()
    body = {
        "name": unique(framework), "framework": framework, "architecture": architecture,
        "upload_id": upload(admin, path.name, data), "class_names": names, "input_size": 640,
    }  # fmt: skip
    response = post(admin, "/models", body)
    assert response.status_code == 201, response.text
    model_id: str = response.json()["id"]
    return model_id


def _model(client: TestClient, model_id: str) -> ModelSummary:
    return ModelSummary.model_validate(client.get(f"/models/{model_id}").json())


def test_model_check_onnx_and_torchvision(setup: dict[str, Any]) -> None:
    admin, runner = setup["admin"], setup["runner"]
    onnx_id = _register(admin, ONNX_WEIGHTS, "onnx", "yolov8n onnx", coco80())
    assert runner.run_next()
    onnx = _model(admin, onnx_id)
    assert onnx.status == "ready", onnx.check
    assert onnx.check is not None and onnx.check.gradient_check is None
    assert onnx.supports_gradients is False

    from safetensors import safe_open

    with safe_open(str(TORCHVISION_WEIGHTS), "pt") as f:
        raw = json.loads(f.metadata()["class_names"])
    names = [f"{n}_{i}" if raw.count(n) > 1 else n for i, n in enumerate(raw)]
    tv_id = _register(admin, TORCHVISION_WEIGHTS, "torchvision", "fcos_resnet50_fpn", names)
    assert runner.run_next()
    tv = _model(admin, tv_id)
    assert tv.status == "ready", tv.check
    assert tv.check is not None and tv.check.gradient_check is not None
    assert tv.supports_gradients is tv.check.gradient_check.passed


def test_model_check_failures(setup: dict[str, Any]) -> None:
    admin, runner = setup["admin"], setup["runner"]
    garbage = _register(
        admin, ONNX_WEIGHTS, "onnx", "khong phai onnx", ["car"], content=b"\x08\x01rac" * 100
    )
    assert runner.run_next()
    failed = _model(admin, garbage)
    assert failed.status == "check_failed"
    assert failed.check is not None and failed.check.details


# ---------------------------------------------------------------- quick_try


def test_quick_try_end_to_end_and_blur(api: Any, setup: dict[str, Any]) -> None:
    engineer, runner = setup["engineer"], setup["runner"]
    quick_try_id = _quick_try(engineer, api)
    assert runner.run_next()
    view = QuickTryView.model_validate(engineer.get(f"/quick-tries/{quick_try_id}").json())
    assert view.status == "completed", view.error
    assert [lv.level for lv in view.levels] == [4.0, 8.0, 16.0, 24.0, 32.0]
    assert view.not_a_test_result is True
    assert view.clean_image_url is not None
    statuses = {o.status for lv in view.levels for o in lv.objects}
    assert statuses <= {"kept", "lost", "new"} and statuses

    response = engineer.get(view.clean_image_url)
    assert response.status_code == 200
    served = np.asarray(Image.open(io.BytesIO(response.content)).convert("RGB"), dtype=np.float32)
    original, _ = letterbox(Image.open(KITTI_IMAGE))
    original_hwc = original.transpose(1, 2, 0) * 255
    clean = [
        Detection((o.bbox[0], o.bbox[1], o.bbox[2], o.bbox[3]), o.class_name, o.clean_score)
        for o in view.levels[0].objects
        if o.clean_score is not None
    ]
    regions = rule_v1_regions(
        ground_truth=[], clean=clean, attacked=[], ignore_boxes=[], width=640, height=640
    )
    assert regions, "ảnh fixture phải có người hoặc xe để làm mờ"
    inside = np.zeros((640, 640), dtype=bool)
    for x1, y1, x2, y2 in regions:
        inside[int(y1) : int(y2), int(x1) : int(x2)] = True
    diff = np.abs(served - original_hwc).mean(axis=2)
    assert diff[inside].mean() > 2.0  # đã làm mờ (thang 0-255)
    assert diff[~inside].mean() < 2.0  # ngoài vùng gần như giữ nguyên


def test_quick_try_leased_before_earlier_checks(api: Any, setup: dict[str, Any]) -> None:
    spec_id = _create_spec(setup["admin"], unique("snow_light"))
    quick_try_id = _quick_try(setup["engineer"], api, "fog")
    assert setup["runner"].run_next()
    view = QuickTryView.model_validate(setup["engineer"].get(f"/quick-tries/{quick_try_id}").json())
    assert view.status == "completed"
    assert _spec_status(setup["admin"], spec_id).status == "checking"
    assert setup["runner"].run_next()
    assert _spec_status(setup["admin"], spec_id).status == "pending_approval"


def test_lost_lease_requeued_twice_then_failed(api: Any, tool_worker: ToolWorker) -> None:
    _, _, engineer = api.user("engineer")
    quick_try_id = _quick_try(engineer, api, "fog")
    job_id = None
    for _ in range(3):
        lease = tool_worker.lease()
        assert lease is not None and lease["kind"] == "quick_try"
        job_id = job_id or lease["job_id"]
        assert lease["job_id"] == job_id
        api.clock.advance(180)  # quá hạn lease, không heartbeat
    assert tool_worker.lease() is None
    assert job_id is not None and lease is not None
    view = QuickTryView.model_validate(engineer.get(f"/quick-tries/{quick_try_id}").json())
    assert view.status == "failed" and view.error
    assert tool_worker.heartbeat(job_id, lease["lease_id"]).status_code == 409


# ---------------------------------------------------------------- tồn đọng R1: ModelProvider.get


class _FlakyProvider:
    """Báo lỗi đúng một lần, ở lần `get` đầu tiên sau khi bắt đầu một run cần gradient."""

    def __init__(self, inner: ModelProvider) -> None:
        self.inner = inner
        self.armed = False
        self.raised = 0

    def get(self, card: Any, params: Any, device: str) -> Any:
        if self.armed:
            self.armed = False
            self.raised += 1
            raise RuntimeError("Giả lập lỗi nạp model khi kiểm gradient")
        return self.inner.get(card, params, device)


def test_provider_error_fails_only_gradient_runs(api: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    _, _, engineer = api.user("engineer")
    target = api.target()
    body = api.body(target, [P5.attack("fgsm", [2.0]), P5.attack("fog", [1.0])])
    experiment_id = ok(post(engineer, "/experiments", body)).json()["id"]
    runs = engineer.get(f"/experiments/{experiment_id}/runs").json()
    gradient_runs = {
        UUID(r["run_id"]) for r in runs if r["attack_spec_id"] == str(spec_of("fgsm").id)
    }

    cache = JobCache(api.tmp / f"cache-{uuid.uuid4().hex[:6]}")
    provider = _FlakyProvider(ModelProvider(cache.store))
    original = WorkerClient.start

    def start(self: Any, run_id: UUID, request: Any) -> Any:
        response = original(self, run_id, request)
        if run_id in gradient_runs and response.action != "skip_cached":
            provider.armed = True
        return response

    monkeypatch.setattr(WorkerClient, "start", start)
    runner = JobRunner(
        WorkerClient(TestClient(api.app()), target.token, sleep=lambda _s: None),
        cache,
        "cpu",
        url_http=httpx.Client(timeout=120),
        heartbeat_interval_s=3600,
        clock=api.clock,
        model_provider=provider,
    )
    lease = runner.client.lease()
    assert lease is not None and str(lease.experiment_id) == experiment_id
    runner.run_lease(lease)

    assert provider.raised == 1
    detail = engineer.get(f"/experiments/{experiment_id}").json()
    assert detail["status"] == "completed"
    by_spec = {
        r["attack_spec_id"]: r for r in engineer.get(f"/experiments/{experiment_id}/runs").json()
    }
    fgsm_run = by_spec[str(spec_of("fgsm").id)]
    assert fgsm_run["status"] == "failed"
    assert fgsm_run["status_reason"]["code"] == "error"
    assert by_spec[str(spec_of("fog").id)]["status"] == "completed"
