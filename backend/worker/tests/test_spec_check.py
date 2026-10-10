"""Job `spec_check` trong tiến trình con: kết quả, quá giờ thì giết tiến trình, lỗi khi nạp."""

from __future__ import annotations

import time
from multiprocessing.connection import Connection
from pathlib import Path

import pytest

from advertest_contracts.models import AttackSpec
from advertest_worker import spec_check
from advertest_worker.spec_check import SpecCheckUnavailable, run_spec_check

MOCKS = Path(__file__).resolve().parents[3] / "contracts" / "mocks"
FOG = AttackSpec.model_validate_json((MOCKS / "attack_spec" / "fog.json").read_text())


# Thân tiến trình con giả (chạy bằng `fork`).
def _hangs(spec_json: str, timeout_s: float, conn: Connection) -> None:
    conn.send(("ready", None))
    time.sleep(60)


def _crashes_while_loading(spec_json: str, timeout_s: float, conn: Connection) -> None:
    conn.send(("crash", "FileNotFoundError: thiếu fixture"))


def _exits_after_ready(spec_json: str, timeout_s: float, conn: Connection) -> None:
    conn.send(("ready", None))
    conn.close()


def _done(spec_json: str, timeout_s: float, conn: Connection) -> None:
    conn.send(("ready", None))
    conn.send(("done", ([{"name": "runs", "passed": True, "details": None}], "dừng sớm")))


def test_hung_check_is_killed_and_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(spec_check, "GRACE_S", 0.5)
    start = time.monotonic()
    outcome = run_spec_check(FOG, timeout_s=0.5, child=_hangs, start_method="fork")
    assert time.monotonic() - start < 30
    assert outcome.items == [] and outcome.error and "Quá 0.5 giây" in outcome.error
    assert not outcome.passed


def test_crash_while_loading_is_infrastructure_error() -> None:
    with pytest.raises(SpecCheckUnavailable, match="thiếu fixture"):
        run_spec_check(FOG, child=_crashes_while_loading, start_method="fork")


def test_child_exit_after_ready_fails_check() -> None:
    outcome = run_spec_check(FOG, child=_exits_after_ready, start_method="fork")
    assert outcome.error and "thoát với mã" in outcome.error


def test_items_and_error_come_back() -> None:
    outcome = run_spec_check(FOG, child=_done, start_method="fork")
    assert [item.name.value for item in outcome.items] == ["runs"]
    assert outcome.error == "dừng sớm"
