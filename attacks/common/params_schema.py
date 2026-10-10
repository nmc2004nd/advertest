"""Kiểm `fixed_params` theo `params_schema` của builder (requirements.md Phase R2, Catalog attack).

`params_schema` là JSON Schema (draft 2020-12) trả qua `GET /attack-adapters`. `jsonschema` không có
trong `tech-stack.md`, nên đây là bộ kiểm cho tập con từ khóa mà builder dùng. Schema có từ khóa
ngoài tập này thì báo `SchemaError` thay vì bỏ qua, để không có ràng buộc nào bị lặng lẽ bỏ qua.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = ["SchemaError", "schema_errors"]

_KEYWORDS = frozenset(
    {
        "$schema",
        "title",
        "description",
        "type",
        "properties",
        "required",
        "additionalProperties",
        "enum",
        "minimum",
        "exclusiveMinimum",
        "maximum",
        "exclusiveMaximum",
        "items",
        "minItems",
        "maxItems",
    }
)


class SchemaError(ValueError):
    """Schema dùng từ khóa mà bộ kiểm không hỗ trợ."""


def _is_type(value: Any, name: str) -> bool:
    # bool là int trong Python nhưng không phải number/integer trong JSON Schema.
    if name == "object":
        return isinstance(value, Mapping)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "null":
        return value is None
    if name == "integer":
        return (isinstance(value, int) and not isinstance(value, bool)) or (
            isinstance(value, float) and value.is_integer()
        )
    if name == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    raise SchemaError(f"type {name!r} không hỗ trợ")


def _same(a: Any, b: Any) -> bool:
    """So sánh theo JSON: 2 == 2.0, nhưng true khác 1."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    return bool(a == b)


def schema_errors(value: Any, schema: Mapping[str, Any], path: str = "fixed_params") -> list[str]:
    """Danh sách lỗi của `value` theo `schema`; rỗng khi hợp lệ."""
    unknown = set(schema) - _KEYWORDS
    if unknown:
        raise SchemaError(f"từ khóa schema không hỗ trợ: {', '.join(sorted(unknown))}")

    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is_type(value, name) for name in types):
            return [f"{path}: cần kiểu {' | '.join(types)}, nhận {value!r}"]

    errors: list[str] = []
    if "enum" in schema and not any(_same(value, option) for option in schema["enum"]):
        errors.append(f"{path}: {value!r} không thuộc {schema['enum']!r}")

    if _is_type(value, "number"):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {value} < {schema['minimum']}")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            errors.append(f"{path}: {value} ≤ {schema['exclusiveMinimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: {value} > {schema['maximum']}")
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            errors.append(f"{path}: {value} ≥ {schema['exclusiveMaximum']}")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: cần ít nhất {schema['minItems']} phần tử")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: cần nhiều nhất {schema['maxItems']} phần tử")
        if "items" in schema:
            for index, item in enumerate(value):
                errors += schema_errors(item, schema["items"], f"{path}[{index}]")

    if isinstance(value, Mapping):
        properties: Mapping[str, Any] = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: thiếu {key!r}")
        for key, item in value.items():
            if key in properties:
                errors += schema_errors(item, properties[key], f"{path}.{key}")
            elif schema.get("additionalProperties", True) is False:
                errors.append(f"{path}: không nhận khóa {key!r}")
            elif isinstance(schema.get("additionalProperties"), Mapping):
                errors += schema_errors(item, schema["additionalProperties"], f"{path}.{key}")
    return errors
