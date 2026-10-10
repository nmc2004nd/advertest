"""validation.md Phase R3, Group 3 — Worker và CLI selfcheck kiểm trên cùng đầu vào
(`test_spec_check_inputs.py`). Không cần DB; chạy selfcheck thật trên fixture (CPU).

- `advertest_worker.spec_check` không còn code dựng fixture riêng, dùng
  `attacks.selfcheck.fixture_inputs` (Group 2).
- `run_spec_check` (tiến trình con của worker) và `run_selfcheck` trên `fixture_inputs` cho cùng
  `items` (tên, đạt/không đạt; `details` của corruption giống hệt) với spec seed `fog` và `fgsm`.
"""

from __future__ import annotations

import inspect

import pytest

from attacks import selfcheck

from .conftest import spec_of


def test_worker_reuses_fixture_inputs() -> None:
    from advertest_worker import spec_check

    shared = getattr(selfcheck, "fixture_inputs", None)
    assert shared is not None, "attacks.selfcheck.fixture_inputs chưa có (Group 2)"
    assert getattr(spec_check, "fixture_inputs", shared) is shared
    assert "SliceLoader" not in inspect.getsource(spec_check)


@pytest.mark.parametrize("name", ["fog", "fgsm"])
def test_worker_and_cli_same_items(name: str) -> None:
    from advertest_worker.spec_check import run_spec_check
    from attacks.selfcheck import (  # type: ignore[attr-defined,unused-ignore]
        fixture_inputs,  # Group 2
    )

    spec = spec_of(name)
    worker = run_spec_check(spec)
    cli = selfcheck.run_selfcheck(spec, fixture_inputs(with_estimator=spec.requires_gradients))
    assert worker.error is None and cli.error is None
    assert [(i.name, i.passed) for i in worker.items] == [(i.name, i.passed) for i in cli.items]
    if not spec.requires_gradients:
        assert [i.details for i in worker.items] == [i.details for i in cli.items]
