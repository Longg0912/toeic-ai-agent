
"""Pydantic schemas for student login and JWT responses."""

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
)


class UserLoginRequest(BaseModel):
    """Validate email and password for login."""

    model_config = ConfigDict(
        extra="forbid",
        hide_input_in_errors=True,
    )

    email: EmailStr = Field(
        max_length=254,
        description="Registered email address",
    )

    password: SecretStr = Field(
        min_length=1,
        max_length=128,
        exclude=True,
        repr=False,
        description="Account password",
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        """Normalize email for account lookup."""
        return value.lower()


class TokenResponse(BaseModel):
    """JWT access token returned after successful login."""

    model_config = ConfigDict(
        extra="forbid",
    )

    access_token: str = Field(
        min_length=1,
        description="Signed JWT access token",
    )

    token_type: Literal["bearer"] = "bearer"

    expires_in: int = Field(
        gt=0,
        description="Access token lifetime in seconds",
    )
