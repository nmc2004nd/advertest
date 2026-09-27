"""JSON chuẩn hóa theo RFC 8785 (JCS) và các hàm hash dựa trên nó.

Mọi hash trong dự án (fingerprint, spec_sha256, dataset version, ...) là sha256 của
`canonical_json`. JCS được chọn để phía JavaScript tính lại được đúng cùng một chuỗi.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

# Số nguyên lớn hơn giá trị này không biểu diễn chính xác được bằng IEEE 754 double.
_MAX_SAFE_INT = 2**53 - 1

_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


def canonical_json(value: Any) -> str:
    """Trả chuỗi JSON chuẩn hóa theo RFC 8785.

    Nhận kiểu JSON thuần (dict, list, tuple, str, int, float, bool, None) hoặc model Pydantic
    (được chuyển bằng `model_dump(mode="json")`). NaN, vô cực và số nguyên vượt 2**53 - 1
    bị từ chối vì không có biểu diễn JSON ổn định.
    """
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    parts: list[str] = []
    _write(value, parts)
    return "".join(parts)


def sha256_of(value: Any) -> str:
    """sha256 (hex, chữ thường) của `canonical_json(value)`."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def compute_fingerprint(fingerprint_inputs: Any) -> str:
    """Fingerprint của run: sha256 của `fingerprint_inputs` đã chuẩn hóa.

    Chỉ nhận phần `fingerprint_inputs` của manifest; `environment` (máy chạy, GPU) không
    thuộc fingerprint để kết quả dùng lại được giữa các máy.
    """
    return sha256_of(fingerprint_inputs)


def _write(value: Any, parts: list[str]) -> None:
    if value is None:
        parts.append("null")
    elif value is True:
        parts.append("true")
    elif value is False:
        parts.append("false")
    elif isinstance(value, str):
        parts.append(_string(value))
    elif isinstance(value, int):
        if abs(value) > _MAX_SAFE_INT:
            raise ValueError(f"Số nguyên vượt 2**53 - 1, không chuẩn hóa được: {value}")
        parts.append(str(value))
    elif isinstance(value, float):
        parts.append(_number(value))
    elif isinstance(value, Mapping):
        for key in value:
            if not isinstance(key, str):
                raise TypeError(f"Key của object phải là str, nhận {type(key).__name__}")
        parts.append("{")
        for i, key in enumerate(sorted(value, key=_utf16_key)):
            if i:
                parts.append(",")
            parts.append(_string(key))
            parts.append(":")
            _write(value[key], parts)
        parts.append("}")
    elif isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        parts.append("[")
        for i, item in enumerate(value):
            if i:
                parts.append(",")
            _write(item, parts)
        parts.append("]")
    else:
        raise TypeError(f"Kiểu không thuộc JSON: {type(value).__name__}")


def _utf16_key(key: str) -> bytes:
    # RFC 8785 sắp key theo đơn vị mã UTF-16, khác thứ tự code point ở ký tự ngoài BMP.
    return key.encode("utf-16-be")


def _string(value: str) -> str:
    out = ['"']
    for ch in value:
        if ch in _ESCAPES:
            out.append(_ESCAPES[ch])
        elif ch < " ":
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _number(value: float) -> str:
    """Định dạng số theo Number.prototype.toString của ECMAScript (RFC 8785 mục 3.2.2.3)."""
    if not math.isfinite(value):
        raise ValueError(f"Không chuẩn hóa được số không hữu hạn: {value}")
    if value == 0:
        return "0"
    sign = "-" if value < 0 else ""
    # repr cho chuỗi chữ số ngắn nhất khôi phục đúng giá trị, giống thuật toán của ECMAScript.
    _, digit_tuple, exponent = Decimal(repr(abs(value))).normalize().as_tuple()
    assert isinstance(exponent, int)
    digits = "".join(map(str, digit_tuple))
    k = len(digits)
    n = k + exponent  # giá trị = 0.digits * 10**n
    if k <= n <= 21:
        body = digits + "0" * (n - k)
    elif 0 < n <= 21:
        body = f"{digits[:n]}.{digits[n:]}"
    elif -6 < n <= 0:
        body = "0." + "0" * (-n) + digits
    else:
        exp = n - 1
        exp_str = f"e+{exp}" if exp >= 0 else f"e-{-exp}"
        mantissa = digits if k == 1 else f"{digits[0]}.{digits[1:]}"
        body = mantissa + exp_str
    return sign + body
