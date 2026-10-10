"""Bộ kiểm `params_schema` (`attacks/common/params_schema.py`) và schema của builder mặc định."""

from __future__ import annotations

from typing import Any

import pytest

from attacks.builders import DEFAULT_REGISTRY
from attacks.common.params_schema import SchemaError, schema_errors
from attacks.registry import load_catalog

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "norm": {"enum": ["inf", 2]},
        "steps": {"type": "integer", "minimum": 1, "maximum": 10},
        "ratio": {"type": "number", "exclusiveMinimum": 0, "exclusiveMaximum": 1},
        "flag": {"type": "boolean"},
        "pair": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
    },
    "required": ["norm"],
    "additionalProperties": False,
}


@pytest.mark.parametrize(
    "value",
    [
        {"norm": "inf"},
        {"norm": 2, "steps": 10, "ratio": 0.5, "flag": True, "pair": [0.8, 1.2]},
        {"norm": 2.0, "steps": 3.0},  # JSON không phân biệt 2 và 2.0
    ],
)
def test_valid_values(value: dict[str, Any]) -> None:
    assert schema_errors(value, SCHEMA) == []


@pytest.mark.parametrize(
    ("value", "fragment"),
    [
        ([], "cần kiểu object"),
        ({}, "thiếu 'norm'"),
        ({"norm": 1}, "không thuộc"),
        ({"norm": "inf", "x": 1}, "không nhận khóa 'x'"),
        ({"norm": "inf", "steps": 0}, "0 < 1"),
        ({"norm": "inf", "steps": 11}, "11 > 10"),
        ({"norm": "inf", "steps": 1.5}, "cần kiểu integer"),
        ({"norm": "inf", "steps": True}, "cần kiểu integer"),  # bool không phải số
        ({"norm": "inf", "ratio": 0}, "0 ≤ 0"),
        ({"norm": "inf", "ratio": 1}, "1 ≥ 1"),
        ({"norm": "inf", "ratio": "x"}, "cần kiểu number"),
        ({"norm": "inf", "flag": 1}, "cần kiểu boolean"),
        ({"norm": "inf", "pair": [1]}, "ít nhất 2"),
        ({"norm": "inf", "pair": [1, 2, 3]}, "nhiều nhất 2"),
        ({"norm": "inf", "pair": [1, "a"]}, "fixed_params.pair[1]"),
    ],
)
def test_invalid_values(value: Any, fragment: str) -> None:
    errors = schema_errors(value, SCHEMA)
    assert errors
    assert any(fragment in error for error in errors), errors


def test_true_is_not_one_in_enum() -> None:
    assert schema_errors(True, {"enum": [1]})
    assert schema_errors(1, {"enum": [1]}) == []


def test_unknown_keyword_is_schema_error() -> None:
    with pytest.raises(SchemaError, match="pattern"):
        schema_errors("a", {"type": "string", "pattern": "^a$"})
    with pytest.raises(SchemaError, match="oneOf"):
        schema_errors({"a": 1}, {"properties": {"a": {"oneOf": []}}})


def test_default_schemas_accept_every_seed_spec() -> None:
    schemas = {info.name: info.params_schema for info in DEFAULT_REGISTRY.adapters()}
    for spec in load_catalog():
        schema = schemas[DEFAULT_REGISTRY.resolver(spec)]
        assert schema_errors(spec.fixed_params, schema) == [], spec.name
