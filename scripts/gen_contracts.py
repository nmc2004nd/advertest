"""Sinh artifact từ contract Pydantic (nguồn sự thật duy nhất).

- JSON Schema (chế độ validation) của từng schema → contracts/schemas/<tên>.json
- TypeScript type (chế độ serialization, đúng hình dạng JSON mà API trả) →
  frontend/src/contracts/schemas.ts, qua openapi-typescript.
- OpenAPI của backend (FastAPI) → contracts/openapi.json, rồi TypeScript type của API →
  frontend/src/contracts/api.ts.

Chạy bằng `make contracts`. Chạy lại khi contract không đổi không được tạo ra thay đổi nào.
"""

from __future__ import annotations

import inspect
import json
import subprocess
import tempfile
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter
from pydantic.json_schema import models_json_schema

from advertest_contracts import enums
from advertest_contracts.registry import SCHEMAS

ROOT = Path(__file__).resolve().parents[1]

SCHEMA_DIR = ROOT / "contracts" / "schemas"
TS_OUT = ROOT / "frontend" / "src" / "contracts" / "schemas.ts"
OPENAPI_OUT = ROOT / "contracts" / "openapi.json"
API_TS_OUT = ROOT / "frontend" / "src" / "contracts" / "api.ts"


def _dump(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def write_json_schemas() -> None:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    expected = {f"{name}.json" for name in SCHEMAS}
    for stale in SCHEMA_DIR.glob("*.json"):
        if stale.name not in expected:
            stale.unlink()
    for name, model in SCHEMAS.items():
        (SCHEMA_DIR / f"{name}.json").write_text(_dump(model.model_json_schema(mode="validation")))


def build_openapi_components() -> dict[str, Any]:
    _, defs = models_json_schema(
        [(model, "serialization") for model in SCHEMAS.values()],
        ref_template="#/components/schemas/{model}",
    )
    schemas: dict[str, Any] = dict(defs.get("$defs", {}))
    # Mọi enum dùng chung, kể cả enum chưa có model nào tham chiếu (ví dụ ExperimentStatus).
    for name, enum_cls in inspect.getmembers(enums, inspect.isclass):
        if issubclass(enum_cls, Enum) and enum_cls.__module__ == enums.__name__:
            schemas[name] = TypeAdapter(enum_cls).json_schema()
    return {
        "openapi": "3.1.0",
        "info": {"title": "AdverTest contracts", "version": "1"},
        "paths": {},
        "components": {"schemas": dict(sorted(schemas.items()))},
    }


def _openapi_typescript(spec_path: Path, out: Path, *extra: str) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "pnpm",
            "--dir",
            str(ROOT / "frontend"),
            "exec",
            "openapi-typescript",
            str(spec_path),
            "--output",
            str(out),
            "--root-types",
            "--root-types-no-schema-prefix",
            *extra,
        ],
        check=True,
        capture_output=True,
    )


def write_typescript() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        spec_path = Path(tmp) / "contracts.openapi.json"
        spec_path.write_text(_dump(build_openapi_components()))
        # --enum-values: xuất mảng giá trị của từng enum để frontend kiểm tra đủ trường hợp.
        _openapi_typescript(spec_path, TS_OUT, "--enum-values")


def write_backend_openapi() -> None:
    # Import muộn: app FastAPI chỉ cần khi xuất OpenAPI, không cần khi sinh schema contract.
    from backend.app.main import create_app

    OPENAPI_OUT.write_text(_dump(create_app().openapi()))
    _openapi_typescript(OPENAPI_OUT, API_TS_OUT)


def main() -> None:
    write_json_schemas()
    write_typescript()
    write_backend_openapi()
    print(
        f"Đã sinh {len(SCHEMAS)} JSON Schema, {TS_OUT.relative_to(ROOT)},"
        f" {OPENAPI_OUT.relative_to(ROOT)} và {API_TS_OUT.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
