
"""Tests for login request and token response schemas."""

import pytest
from pydantic import ValidationError

from backend.app.schemas.login import (
    TokenResponse,
    UserLoginRequest,
)


EMAIL = "student@example.com"
PASSWORD = "ExamplePassword@2026"


def test_login_normalizes_email() -> None:
    """Login email is normalized to lowercase."""

    data = UserLoginRequest(
        email="Student@Example.COM",
        password=PASSWORD,
    )

    assert data.email == EMAIL
    assert data.password.get_secret_value() == PASSWORD


def test_login_accepts_nonempty_short_password() -> None:
    """Login accepts nonempty input for credential verification."""

    data = UserLoginRequest(
        email=EMAIL,
        password="x",
    )

    assert data.password.get_secret_value() == "x"


def test_login_rejects_invalid_email() -> None:
    """Invalid email syntax is rejected."""

    with pytest.raises(ValidationError):
        UserLoginRequest(
            email="invalid-email",
            password=PASSWORD,
        )


@pytest.mark.parametrize(
    "password",
    ["", None],
)
def test_login_rejects_empty_password(
    password: str | None,
) -> None:
    """Empty or null passwords are rejected."""

    with pytest.raises(ValidationError):
        UserLoginRequest.model_validate(
            {
                "email": EMAIL,
                "password": password,
            }
        )


def test_login_requires_email() -> None:
    """An email is required."""

    with pytest.raises(ValidationError):
        UserLoginRequest.model_validate(
            {"password": PASSWORD}
        )


def test_login_rejects_extra_fields() -> None:
    """Users cannot set roles through login."""

    with pytest.raises(ValidationError):
        UserLoginRequest.model_validate(
            {
                "email": EMAIL,
                "password": PASSWORD,
                "role": "admin",
            }
        )


def test_login_password_not_serialized() -> None:
    """Login password is excluded from serialized data."""

    data = UserLoginRequest(
        email=EMAIL,
        password=PASSWORD,
    )

    assert "password" not in data.model_dump()
    assert PASSWORD not in data.model_dump_json()
    assert PASSWORD not in repr(data)


def test_token_response_schema() -> None:
    """Token responses contain exactly the expected fields."""

    response = TokenResponse(
        access_token="test.token.value",
        token_type="bearer",
        expires_in=1800,
    )

    assert response.model_dump() == {
        "access_token": "test.token.value",
        "token_type": "bearer",
        "expires_in": 1800,
    }
