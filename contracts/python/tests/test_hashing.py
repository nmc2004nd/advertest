import hashlib
import math
from uuid import UUID

import pytest
from pydantic import BaseModel

from advertest_contracts.hashing import canonical_json, compute_fingerprint, sha256_of
from advertest_contracts.ids import ADVERTEST_NAMESPACE, content_id


def test_key_order_does_not_matter() -> None:
    a = {"b": 1, "a": {"y": [1, 2], "x": None}}
    b = {"a": {"x": None, "y": [1, 2]}, "b": 1}
    assert canonical_json(a) == canonical_json(b) == '{"a":{"x":null,"y":[1,2]},"b":1}'


def test_no_whitespace_and_literals() -> None:
    assert canonical_json([True, False, None, "x"]) == '[true,false,null,"x"]'


def test_integral_float_equals_int() -> None:
    assert canonical_json({"level": 4.0}) == canonical_json({"level": 4}) == '{"level":4}'


# Giá trị kỳ vọng lấy từ JSON.stringify của Node (cùng thuật toán ECMAScript mà RFC 8785 dùng).
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.0, "0"),
        (-0.0, "0"),
        (5e-324, "5e-324"),
        (-5e-324, "-5e-324"),
        (1.7976931348623157e308, "1.7976931348623157e+308"),
        (9007199254740992.0, "9007199254740992"),
        (2.9514790517935283e20, "295147905179352830000"),
        (9.999999999999997e22, "9.999999999999997e+22"),
        (1e23, "1e+23"),
        (1e21, "1e+21"),
        (999999999999999700000.0, "999999999999999700000"),
        (1e-6, "0.000001"),
        (1e-7, "1e-7"),
        (333333333.3333332, "333333333.3333332"),
        (0.1, "0.1"),
        (123.456, "123.456"),
    ],
)
def test_number_format_matches_ecmascript(value: float, expected: str) -> None:
    assert canonical_json(value) == expected


def test_string_escaping() -> None:
    assert canonical_json('a"b\\c\n\t\x01/é€') == '"a\\"b\\\\c\\n\\t\\u0001/é€"'


def test_keys_sorted_by_utf16_code_units() -> None:
    # "\U0001f600" (UTF-16: D83D DE00) đứng trước "ﬁ" (FB01) theo UTF-16,
    # dù code point của nó lớn hơn.
    assert canonical_json({"ﬁ": 1, "\U0001f600": 2}) == '{"\U0001f600":2,"ﬁ":1}'


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, 2**53])
def test_rejects_values_without_stable_json(bad: float) -> None:
    with pytest.raises(ValueError):
        canonical_json({"x": bad})


def test_rejects_non_json_types() -> None:
    with pytest.raises(TypeError):
        canonical_json({1: "a"})
    with pytest.raises(TypeError):
        canonical_json({"a": {1, 2}})
    with pytest.raises(TypeError):
        canonical_json(b"bytes")


class _Sample(BaseModel):
    b: float
    a: str


def test_accepts_pydantic_model() -> None:
    assert canonical_json(_Sample(b=2, a="x")) == '{"a":"x","b":2}'


def test_sha256_of_is_hash_of_canonical_json() -> None:
    expected = hashlib.sha256(b'{"a":1,"b":"\xc3\xa9"}').hexdigest()
    assert sha256_of({"b": "é", "a": 1}) == expected


def test_compute_fingerprint_is_sha256_of_inputs() -> None:
    inputs = {"seed": 42, "params": {"eps": 4}}
    assert compute_fingerprint(inputs) == sha256_of(inputs)
    assert compute_fingerprint(inputs) != compute_fingerprint({**inputs, "seed": 43})


def test_content_id_is_deterministic_uuid5() -> None:
    sha = hashlib.sha256(b"x").hexdigest()
    first = content_id(sha)
    assert first == content_id(sha)
    assert first.version == 5
    assert first != content_id(hashlib.sha256(b"y").hexdigest())
    assert isinstance(ADVERTEST_NAMESPACE, UUID)


@pytest.mark.parametrize("bad", ["", "ABC", "g" * 64, "A" * 64, "a" * 63])
def test_content_id_rejects_non_sha256(bad: str) -> None:
    with pytest.raises(ValueError):
        content_id(bad)
