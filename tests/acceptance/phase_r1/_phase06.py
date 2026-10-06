"""Nạp conftest của Phase 6 (world có slice đánh giá 3 ảnh, slice huấn luyện 2 ảnh, spec patch
`max_iter` nhỏ; hạ tầng DB, MinIO, API, worker thật của Phase 5) đúng một lần, cùng cách
`phase_06/_phase05.py` nạp Phase 5, để golden worker dùng lại thay vì chép lại."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

PHASE_06 = Path(__file__).resolve().parents[1] / "phase_06"


def load() -> types.ModuleType:
    name = "phase_06.conftest"
    if name in sys.modules:
        return sys.modules[name]
    if "phase_06" not in sys.modules:
        package = types.ModuleType("phase_06")
        package.__path__ = [str(PHASE_06)]
        sys.modules["phase_06"] = package
    spec = importlib.util.spec_from_file_location(name, PHASE_06 / "conftest.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
