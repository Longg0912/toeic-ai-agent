
"""Tests for registration and public user schemas."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.app.schemas.auth import (
    UserPublic,
    UserRegisterRequest,
)


VALID_EMAIL = "student@example.com"
VALID_PASSWORD = "ExamplePassword@2026"


def test_registration_accepts_valid_data() -> None:
    """Valid registration data is accepted and normalized."""

    data = UserRegisterRequest(
        email="Student@Example.COM",
        password=VALID_PASSWORD,
    )

    assert data.email == VALID_EMAIL
    assert data.password.get_secret_value() == VALID_PASSWORD


def test_registration_rejects_invalid_email() -> None:
    """Invalid email addresses are rejected."""

    with pytest.raises(ValidationError):
        UserRegisterRequest(
            email="not-an-email",
            password=VALID_PASSWORD,
        )


def test_registration_rejects_short_password() -> None:
    """Passwords must have at least 12 characters."""

    with pytest.raises(ValidationError):
        UserRegisterRequest(
            email=VALID_EMAIL,
            password="short",
        )


def test_registration_rejects_long_password() -> None:
    """Passwords exceeding 128 characters are rejected."""

    with pytest.raises(ValidationError):
        UserRegisterRequest(
            email=VALID_EMAIL,
            password="A" * 129,
        )


def test_registration_rejects_whitespace_only() -> None:
    """A password containing only spaces is invalid."""

    with pytest.raises(ValidationError):
        UserRegisterRequest(
            email=VALID_EMAIL,
            password=" " * 12,
        )


def test_registration_preserves_password_content() -> None:
    """Unicode and meaningful spaces must be preserved."""

    password = "  MậtKhẩuAnToàn@2026  "

    data = UserRegisterRequest(
        email=VALID_EMAIL,
        password=password,
    )

    assert data.password.get_secret_value() == password


def test_registration_rejects_role_override() -> None:
    """Students must not choose their own account role."""

    with pytest.raises(ValidationError):
        UserRegisterRequest.model_validate(
            {
                "email": VALID_EMAIL,
                "password": VALID_PASSWORD,
                "role": "admin",
            }
        )


def test_registration_excludes_password_from_dump() -> None:
    """Password must not appear in serialized request data."""

    data = UserRegisterRequest(
        email=VALID_EMAIL,
        password=VALID_PASSWORD,
    )

    assert "password" not in data.model_dump()
    assert "password" not in data.model_dump_json()
    assert VALID_PASSWORD not in repr(data)


def test_user_public_excludes_sensitive_fields() -> None:
    """Public user schemas must never expose password hashes."""

    user = SimpleNamespace(
        id=1,
        email=VALID_EMAIL,
        role="student",
        is_active=True,
        password_hash="secret-hash",
    )

    result = UserPublic.model_validate(user)

    output = result.model_dump()

    assert output == {
        "id": 1,
        "email": VALID_EMAIL,
        "role": "student",
        "is_active": True,
    }

    assert "password_hash" not in output
    assert "password" not in output


def test_registration_requires_password() -> None:
    """A registration request must contain a password."""

    with pytest.raises(ValidationError):
        UserRegisterRequest.model_validate(
            {"email": VALID_EMAIL}
        )
