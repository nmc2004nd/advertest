import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "module", ["ml_core.runner.run", "ml_core.runner.config", "ml_core.cli.run", "ml_core.cli"]
)
def test_module_imports_on_its_own(module: str) -> None:
    # Interpreter mới: import vòng chỉ lộ ra khi module được import đầu tiên.
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
