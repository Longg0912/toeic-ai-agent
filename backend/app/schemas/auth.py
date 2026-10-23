
"""Authentication request and response schemas."""

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
)


class UserRegisterRequest(BaseModel):
    """Validate an incoming student registration request."""

    model_config = ConfigDict(
        extra="forbid",
        hide_input_in_errors=True,
    )

    email: EmailStr = Field(
        max_length=254,
        description="Email address of the student",
    )

    password: SecretStr = Field(
        min_length=12,
        max_length=128,
        exclude=True,
        repr=False,
        description="Password with 12-128 characters",
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        """Normalize emails for consistent account lookup."""
        return value.lower()

    @field_validator("password")
    @classmethod
    def reject_blank_password(
        cls,
        value: SecretStr,
    ) -> SecretStr:
        """Reject passwords containing only whitespace."""

        if not value.get_secret_value().strip():
            raise ValueError(
                "Password cannot contain only whitespace."
            )

        return value


class UserPublic(BaseModel):
    """Public user fields returned by the API."""

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    email: EmailStr
    role: str
    is_active: bool
