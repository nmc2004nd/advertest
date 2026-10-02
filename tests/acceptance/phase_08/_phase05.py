"""Nạp conftest của Phase 5 (hạ tầng DB, API, worker thật) đúng một lần, cùng tên module mà pytest
dùng (`phase_05.conftest`, `--import-mode=importlib`), để Phase 8 dùng lại thay vì chép lại
(chép từ Phase 6)."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

PHASE_05 = Path(__file__).resolve().parents[1] / "phase_05"


def load() -> types.ModuleType:
    name = "phase_05.conftest"
    if name in sys.modules:
        return sys.modules[name]
    if "phase_05" not in sys.modules:
        package = types.ModuleType("phase_05")
        package.__path__ = [str(PHASE_05)]
        sys.modules["phase_05"] = package
    spec = importlib.util.spec_from_file_location(name, PHASE_05 / "conftest.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
