"""Job `spec_check`: tự kiểm tra attack spec trong một tiến trình con (requirements.md Phase R2,
mục Tự kiểm tra spec).

`attacks.selfcheck.run_selfcheck` chỉ kiểm giới hạn thời gian giữa các bước, không cắt ngang một
lần `apply`; cắt cứng là việc của tiến trình gọi (quyết định Group 2). Vì vậy kiểm tra chạy trong
tiến trình con (`spawn`):

1. Tiến trình con dựng đầu vào bằng `attacks.selfcheck.fixture_inputs`, dùng chung với CLI selfcheck
   (4 ảnh KITTI letterbox, target đã map, estimator ART của YOLOv8n trên CPU khi spec cần gradient;
   fixture ở `ml_core.fixtures.FIXTURES_DIR`, image worker chép sẵn) rồi báo `ready`. Không dựng
   được trong `LOAD_TIMEOUT_S` là lỗi hạ tầng (`SpecCheckUnavailable`), không phải lỗi của spec.
2. Sau `ready`, tiến trình cha chờ tối đa `timeout_s + GRACE_S`. Quá giờ thì giết tiến trình con và
   trả kết quả có `error` (spec chuyển `check_failed`); các mục đã chạy bị mất.
"""

from __future__ import annotations

import multiprocessing
from collections.abc import Callable
from multiprocessing.connection import Connection
from typing import Any, Literal

from advertest_contracts.models import AttackSpec, SpecCheckItem
from attacks.selfcheck import DEFAULT_TIMEOUT_S, SelfcheckOutcome, fixture_inputs, run_selfcheck

LOAD_TIMEOUT_S = 300.0  # import torch, nạp fixture và model YOLO
GRACE_S = 15.0  # selfcheck tự dừng ở `timeout_s` nếu không kẹt trong một lần `apply`


class SpecCheckUnavailable(RuntimeError):
    """Không dựng được môi trường kiểm tra (thiếu fixture, tiến trình con chết khi nạp)."""


def _child(spec_json: str, timeout_s: float, conn: Connection) -> None:
    """Thân tiến trình con: `("ready", None)`, rồi `("done", (items, error))`; lỗi bất kỳ là
    `("crash", mô tả)`."""
    try:
        spec = AttackSpec.model_validate_json(spec_json)
        inputs = fixture_inputs(with_estimator=spec.requires_gradients)
        conn.send(("ready", None))
        outcome = run_selfcheck(spec, inputs, timeout_s=timeout_s)
        items = [item.model_dump(mode="json") for item in outcome.items]
        conn.send(("done", (items, outcome.error)))
    except BaseException as exc:  # gửi về tiến trình cha thay vì chết im lặng
        conn.send(("crash", f"{type(exc).__name__}: {exc}"))
    finally:
        conn.close()


def _receive(conn: Connection, process: Any, timeout_s: float) -> tuple[str, Any] | None:
    """Thông điệp kế tiếp; `None` khi quá giờ, `("crash", ...)` khi tiến trình con đã thoát."""
    if not conn.poll(timeout_s):
        return None
    try:
        message: tuple[str, Any] = conn.recv()
    except EOFError:
        process.join(timeout=5)
        return ("crash", f"tiến trình kiểm tra thoát với mã {process.exitcode}")
    return message


def run_spec_check(
    spec: AttackSpec,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    load_timeout_s: float = LOAD_TIMEOUT_S,
    child: Callable[[str, float, Connection], None] = _child,
    start_method: Literal["spawn", "fork"] = "spawn",
) -> SelfcheckOutcome:
    """`child`, `start_method`: test thay thân tiến trình con (với `fork`, vì pytest chạy
    `--import-mode=importlib` nên tiến trình `spawn` không import được hàm trong file test)."""
    ctx = (
        multiprocessing.get_context("fork")
        if start_method == "fork"
        else multiprocessing.get_context("spawn")
    )
    receiver, sender = ctx.Pipe(duplex=False)
    process = ctx.Process(
        target=child, args=(spec.model_dump_json(), timeout_s, sender), name="spec-check"
    )
    process.start()
    sender.close()
    try:
        message = _receive(receiver, process, load_timeout_s)
        if message is None:
            raise SpecCheckUnavailable(
                f"Không dựng được đầu vào kiểm tra trong {load_timeout_s:g} giây"
            )
        if message[0] == "crash":
            raise SpecCheckUnavailable(f"Không dựng được đầu vào kiểm tra: {message[1]}")
        message = _receive(receiver, process, timeout_s + GRACE_S)
        if message is None:
            return SelfcheckOutcome(
                items=[], error=f"Quá {timeout_s:g} giây; đã dừng tiến trình kiểm tra"
            )
        if message[0] == "crash":
            return SelfcheckOutcome(items=[], error=f"Lỗi khi kiểm tra: {message[1]}")
        items, error = message[1]
        return SelfcheckOutcome(
            items=[SpecCheckItem.model_validate(item) for item in items], error=error
        )
    finally:
        receiver.close()
        if process.is_alive():
            process.kill()
        process.join()
