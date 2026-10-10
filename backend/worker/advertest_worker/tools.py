"""Worker công cụ `advertest-worker --tools` (requirements.md Phase R2, mục Job công cụ).

Process riêng, chỉ lease job công cụ, để thử nhanh không phải chờ experiment đang chạy.
`ToolRunner.run_next()`: lease → bundle → chạy → gửi `ToolJobResult`; trả `False` khi không còn
job. Heartbeat chạy ở luồng riêng (lease 60 giây); mất lease (`409`) thì bỏ kết quả, không gửi gì.

- `spec_check`: `spec_check.run_spec_check` (tiến trình con, cắt cứng khi quá giờ).
- `model_check`: tải weights vào file tạm, `ml_core.models.check.check_model`.
- `quick_try`: weights vào cache (kiểm sha256), adapter qua `ModelProvider` (LRU), tính mọi level
  (`quick_try.run_quick_try`), PUT ảnh đã làm mờ lên presigned URL, rồi gửi report.

Kiểm tra fail vẫn là `report` với `passed = false`; ngoại lệ (tải file, nạp tài nguyên, lỗi bất
ngờ) là `error`.

`worker_target_id` trong kết quả kiểm tra do API ghi theo target đã lease job (worker không biết id
của target mình, người duyệt chốt ở Group 5); worker gửi `UNKNOWN_TARGET`.
"""

from __future__ import annotations

import logging
import tempfile
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx

from advertest_contracts.models import (
    GradientCheck,
    InferenceParams,
    ModelCard,
    ModelCheckPayload,
    ModelCheckReport,
    QuickTryPayload,
    QuickTryReport,
    SpecCheckPayload,
    SpecCheckReport,
    ToolJobResult,
    ToolLease,
    ToolModel,
    ToolPayload,
    ToolReport,
)
from advertest_worker.cache import JobCache
from advertest_worker.client import LeaseLost, WorkerClient
from advertest_worker.config import HEARTBEAT_INTERVAL_S
from advertest_worker.quick_try import run_quick_try
from advertest_worker.spec_check import run_spec_check
from attacks.builders import DEFAULT_REGISTRY, PerturbationRegistry
from attacks.selfcheck import DEFAULT_TIMEOUT_S
from ml_core.models.adapter import ModelProvider
from ml_core.models.check import check_model
from ml_core.models.register import lib_versions
from ml_core.models.wrapper import DEFAULT_INFERENCE_PARAMS
from ml_core.runner.perturbations import ModelSource

logger = logging.getLogger(__name__)

UNKNOWN_TARGET = UUID(int=0)  # API thay bằng target đã lease job
MAX_ERROR_CHARS = 4000  # `ToolJobResult.error`


def utcnow() -> datetime:
    return datetime.now(UTC)


def tool_card(model: ToolModel, checked_at: datetime) -> ModelCard:
    """Model card trong bộ nhớ của worker công cụ (không ghi đi đâu).

    `ToolModel` không có `supports_gradients`: đặt `framework != "onnx"`, vì API đã từ chối thử
    nhanh khi model không hỗ trợ gradient gặp attack cần gradient (người duyệt chốt ở Group 5).
    """
    gradients = model.framework != "onnx"
    return ModelCard(
        id=model.model_version_id,
        name=str(model.model_version_id),
        framework=model.framework,
        architecture=model.architecture,
        weights_sha256=model.weights_sha256,
        class_names=model.class_names,
        input_size=model.input_size,
        supports_gradients=gradients,
        gradient_check=GradientCheck(
            passed=gradients,
            checked_at=checked_at,
            details=None if gradients else "Model ONNX không hỗ trợ gradient",
        ),
        lib_versions=lib_versions(),
    )


def _params(model: ToolModel) -> InferenceParams:
    return DEFAULT_INFERENCE_PARAMS.model_copy(update={"input_size": model.input_size})


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:MAX_ERROR_CHARS]


class ToolHeartbeat(threading.Thread):
    def __init__(self, client: WorkerClient, lease: ToolLease, interval_s: float) -> None:
        super().__init__(daemon=True, name="tool-heartbeat")
        self.client = client
        self.lease = lease
        self.interval_s = interval_s
        self.lost = threading.Event()
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.wait(self.interval_s):
            try:
                self.client.tool_heartbeat(self.lease.job_id, self.lease.lease_id)
            except LeaseLost:
                self.lost.set()
                return
            except Exception:  # mạng chập chờn: client đã retry; lần sau thử tiếp
                logger.warning("Heartbeat job công cụ thất bại", exc_info=True)

    def stop(self) -> None:
        self._stop_event.set()
        if self.is_alive():
            self.join(timeout=self.interval_s + 5)


class ToolRunner:
    def __init__(
        self,
        client: WorkerClient,
        cache: JobCache,
        device: str,
        *,
        url_http: httpx.Client | None = None,
        clock: Callable[[], datetime] = utcnow,
        heartbeat_interval_s: float = HEARTBEAT_INTERVAL_S,
        registry: PerturbationRegistry = DEFAULT_REGISTRY,
        model_provider: ModelSource | None = None,
        selfcheck_timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self.client = client
        self.cache = cache
        self.device = device
        self.url_http = url_http or httpx.Client(timeout=120.0)
        self.clock = clock
        self.heartbeat_interval_s = heartbeat_interval_s
        self.registry = registry
        self.models = model_provider or ModelProvider(cache.store)
        self.selfcheck_timeout_s = selfcheck_timeout_s

    def run_next(self) -> bool:
        """Lease và chạy một job công cụ; `False` khi không còn job."""
        lease = self.client.tool_lease()
        if lease is None:
            return False
        logger.info("Nhận job %s %s", lease.kind, lease.job_id)
        self.run_lease(lease)
        return True

    def run_lease(self, lease: ToolLease) -> None:
        heartbeat = ToolHeartbeat(self.client, lease, self.heartbeat_interval_s)
        heartbeat.start()
        try:
            result = self._result(lease)
            if heartbeat.lost.is_set():
                logger.warning("Mất lease của job %s; bỏ kết quả", lease.job_id)
                return
            self.client.tool_result(lease.job_id, result)
        except LeaseLost:
            logger.warning("Mất lease của job %s; dừng", lease.job_id)
        finally:
            heartbeat.stop()

    def _result(self, lease: ToolLease) -> ToolJobResult:
        try:
            payload = self.client.tool_bundle(lease.job_id).payload
            return ToolJobResult(lease_id=lease.lease_id, report=self._run(payload))
        except LeaseLost:
            raise
        except (
            Exception
        ) as exc:  # lỗi hạ tầng: gửi `error`, đối tượng của job chuyển trạng thái lỗi
            logger.exception("Job %s %s lỗi", lease.kind, lease.job_id)
            return ToolJobResult(lease_id=lease.lease_id, error=_describe(exc))

    def _run(self, payload: ToolPayload) -> ToolReport:
        if isinstance(payload, SpecCheckPayload):
            return self._spec_check(payload)
        if isinstance(payload, ModelCheckPayload):
            return self._model_check(payload)
        return self._quick_try(payload)

    # ------------------------------------------------------------------ từng loại job

    def _spec_check(self, payload: SpecCheckPayload) -> SpecCheckReport:
        outcome = run_spec_check(payload.spec, timeout_s=self.selfcheck_timeout_s)
        result = outcome.to_result(
            payload.spec.id, checked_at=self.clock(), worker_target_id=UNKNOWN_TARGET
        )
        return SpecCheckReport(result=result)

    def _model_check(self, payload: ModelCheckPayload) -> ModelCheckReport:
        model = payload.model
        with tempfile.TemporaryDirectory(prefix="model-check-") as tmp:
            path = Path(tmp) / "weights"
            response = self.url_http.get(model.weights_url)
            response.raise_for_status()
            path.write_bytes(response.content)
            # sha256 do `check_model` so (lệch là kiểm tra fail, không phải lỗi hạ tầng).
            result = check_model(
                tool_card(model, self.clock()),
                path,
                worker_target_id=UNKNOWN_TARGET,
                device=self.device,
                params=_params(model),
            )
        return ModelCheckReport(result=result)

    def _quick_try(self, payload: QuickTryPayload) -> QuickTryReport:
        model = payload.model
        self.cache.ensure_weights(model.weights_sha256, model.weights_url)
        params = _params(model)
        adapter = self.models.get(tool_card(model, self.clock()), params, self.device)
        image = self.url_http.get(payload.image_url).raise_for_status().content
        output = run_quick_try(image, adapter, payload.spec, payload.levels, params, self.registry)
        uploads = [
            (payload.clean_upload_url, output.clean_png),
            *zip(payload.level_upload_urls, output.level_pngs, strict=True),
        ]
        for url, data in uploads:
            self.url_http.put(url, content=data).raise_for_status()
        return QuickTryReport(levels=output.levels)
