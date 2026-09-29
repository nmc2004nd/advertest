from backend.app.auth.passwords import (
    hash_password,
    needs_rehash,
    verify_password,
    violates_policy,
)


def test_hash_is_argon2id_and_verifies() -> None:
    hashed = hash_password("mat-khau-du-dai-1")
    assert hashed.startswith("$argon2id$")
    assert "mat-khau-du-dai-1" not in hashed
    assert verify_password(hashed, "mat-khau-du-dai-1")
    assert not verify_password(hashed, "mat-khau-du-dai-2")
    assert not needs_rehash(hashed)


def test_missing_or_malformed_hash_never_verifies() -> None:
    assert not verify_password(None, "mat-khau-gia-de-can-thoi-gian")
    assert not verify_password("khong-phai-hash", "x")


def test_policy() -> None:
    assert violates_policy("ngan", "a@x.com") is not None
    assert violates_policy(" A@X.com  ", "a@x.com") is not None
    assert violates_policy("a@x.com-khac", "a@x.com") is None
