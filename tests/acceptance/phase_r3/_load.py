"""Nạp conftest của phase khác đúng một lần, cùng tên module mà pytest dùng (`<phase>.conftest`,
`--import-mode=importlib`), để Phase R3 dùng lại hạ tầng thay vì chép lại (như `_phase05.py` của
Phase 8 và R2)."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ACCEPTANCE = Path(__file__).resolve().parents[1]


def load(phase: str) -> types.ModuleType:
    name = f"{phase}.conftest"
    if name in sys.modules:
        return sys.modules[name]
    if phase not in sys.modules:
        package = types.ModuleType(phase)
        package.__path__ = [str(ACCEPTANCE / phase)]
        sys.modules[phase] = package
    spec = importlib.util.spec_from_file_location(name, ACCEPTANCE / phase / "conftest.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
