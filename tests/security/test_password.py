
"""Tests for password hashing and verification."""

import pytest

from backend.app.security.password import (
    hash_password,
    verify_password,
)


def test_hash_password_uses_argon2id() -> None:
    """Passwords must be hashed with Argon2id."""

    password = "ExamplePass@2026"

    hashed = hash_password(password)

    assert isinstance(hashed, str)
    assert hashed != password
    assert hashed.startswith("$argon2id$")


def test_verify_password_correct() -> None:
    """The correct password must be accepted."""

    password = "SecurePassword@123"

    hashed = hash_password(password)

    assert verify_password(password, hashed) is True


def test_verify_password_wrong() -> None:
    """An incorrect password must be rejected."""

    hashed = hash_password("CorrectPassword@123")

    result = verify_password(
        "WrongPassword@123",
        hashed,
    )

    assert result is False


def test_same_password_generates_different_hashes() -> None:
    """Random salts should produce different hashes."""

    password = "SamePassword@2026"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash != second_hash

    assert verify_password(password, first_hash) is True
    assert verify_password(password, second_hash) is True


def test_unicode_and_whitespace_are_preserved() -> None:
    """Unicode and surrounding spaces are meaningful."""

    password = "  MậtKhẩuTiếngViệt@2026  "

    hashed = hash_password(password)

    assert verify_password(password, hashed) is True

    assert verify_password(
        password.strip(),
        hashed,
    ) is False


def test_hash_rejects_empty_password() -> None:
    """Empty plaintext passwords must be rejected."""

    with pytest.raises(
        ValueError,
        match="Password cannot be empty",
    ):
        hash_password("")


def test_verify_rejects_invalid_hash() -> None:
    """Unrecognized stored hashes must fail safely."""

    assert verify_password(
        "AnyPassword@2026",
        "not-a-valid-hash",
    ) is False


def test_verify_rejects_empty_inputs() -> None:
    """Empty password or stored hash must fail."""

    hashed = hash_password("ValidPassword@2026")

    assert verify_password("", hashed) is False

    assert verify_password(
        "ValidPassword@2026",
        "",
    ) is False
