"""Mật khẩu: argon2id (`argon2-cffi`) và chính sách mật khẩu (requirements.md Phase 4).

Độ dài tối thiểu 10 ký tự đã được kiểm tra ở contract (`NewPassword`); ở đây kiểm tra thêm luật
cần biết email của người dùng.
"""

from __future__ import annotations

from functools import cache

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError

_HASHER = PasswordHasher(type=Type.ID)


def hash_password(password: str) -> str:
    return _HASHER.hash(password)


@cache
def _dummy_hash() -> str:
    return _HASHER.hash("mat-khau-gia-de-can-thoi-gian")


def verify_password(password_hash: str | None, password: str) -> bool:
    """Đúng mật khẩu → True. Không có hash (email không tồn tại) vẫn tốn cùng thời gian băm để
    không lộ email nào đã có tài khoản."""
    try:
        return _HASHER.verify(password_hash or _dummy_hash(), password) and bool(password_hash)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _HASHER.check_needs_rehash(password_hash)


def violates_policy(password: str, email: str) -> str | None:
    """Thông điệp lỗi nếu mật khẩu vi phạm chính sách, ngược lại None."""
    if len(password) < 10:
        return "Mật khẩu phải có ít nhất 10 ký tự"
    if password.strip().lower() == email.strip().lower():
        return "Mật khẩu không được trùng email"
    return None
