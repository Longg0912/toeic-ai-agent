
"""JWT access-token creation and verification.

Security rules:
- HS256 is the only permitted algorithm.
- The signing secret comes from the environment.
- Tokens expire after 30 minutes by default.
- Required claims are checked when decoding.
- Passwords and password hashes are never stored in JWTs.
"""

from __future__ import annotations

import os
import secrets

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt

from dotenv import load_dotenv


ALGORITHM = "HS256"

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"


@dataclass(frozen=True)
class JWTSettings:
    """Configuration for access tokens."""

    secret_key: str

    issuer: str = "toeic-ai-agent"
    audience: str = "toeic-ai-agent-api"
    access_token_expire_minutes: int = 30

    def __post_init__(self) -> None:
        """Reject missing or obviously weak configuration."""

        if not isinstance(self.secret_key, str):
            raise ValueError("JWT secret key must be a string.")

        if len(self.secret_key.encode("utf-8")) < 32:
            raise ValueError(
                "JWT secret key must contain at least 32 bytes."
            )

        if self.access_token_expire_minutes <= 0:
            raise ValueError(
                "Access token lifetime must be positive."
            )

        if not self.issuer or not self.audience:
            raise ValueError(
                "JWT issuer and audience are required."
            )


class InvalidAccessTokenError(Exception):
    """Raised when an access token is invalid or expired."""


def get_jwt_settings() -> JWTSettings:
    """Read JWT configuration without hardcoded secrets.

    Existing process environment variables take precedence
    over values stored in the project .env file.
    """

    load_dotenv(
        dotenv_path=ENV_FILE,
        override=False,
    )

    secret_key = os.getenv("JWT_SECRET_KEY")

    if not secret_key:
        raise RuntimeError(
            "JWT_SECRET_KEY is missing. "
            "Configure it in the project .env file."
        )

    return JWTSettings(secret_key=secret_key)


def create_access_token(
    user_id: int,
    *,
    settings: JWTSettings | None = None,
    now: datetime | None = None,
) -> str:
    """Create a signed JWT access token for one user.

    Args:
        user_id: Positive database user ID.
        settings: Optional settings, mainly for testing.
        now: Optional aware datetime, mainly for testing.

    Returns:
        Signed JWT string.
    """

    if type(user_id) is not int or user_id <= 0:
        raise ValueError(
            "user_id must be a positive integer."
        )

    config = (
        settings
        if settings is not None
        else get_jwt_settings()
    )

    issued_at = (
        now
        if now is not None
        else datetime.now(timezone.utc)
    )

    if (
        issued_at.tzinfo is None
        or issued_at.utcoffset() is None
    ):
        raise ValueError(
            "Token datetime must be timezone-aware."
        )

    issued_at = issued_at.astimezone(timezone.utc)

    expires_at = issued_at + timedelta(
        minutes=config.access_token_expire_minutes
    )

    payload = {
        "sub": str(user_id),
        "type": "access",
        "iss": config.issuer,
        "aud": config.audience,
        "iat": issued_at,
        "nbf": issued_at,
        "exp": expires_at,
        "jti": secrets.token_hex(16),
    }

    return jwt.encode(
        payload,
        config.secret_key,
        algorithm=ALGORITHM,
    )


def decode_access_token(
    token: str,
    *,
    settings: JWTSettings | None = None,
) -> int:
    """Verify an access token and return its user ID.

    Raises:
        InvalidAccessTokenError:
            If token is invalid, expired, or has bad claims.
    """

    if not isinstance(token, str) or not token:
        raise InvalidAccessTokenError(
            "Invalid or expired access token."
        )

    config = (
        settings
        if settings is not None
        else get_jwt_settings()
    )

    try:
        payload = jwt.decode(
            token,
            config.secret_key,
            algorithms=[ALGORITHM],
            issuer=config.issuer,
            audience=config.audience,
            options={
                "require": [
                    "sub",
                    "type",
                    "iss",
                    "aud",
                    "iat",
                    "nbf",
                    "exp",
                    "jti",
                ],
            },
        )

    except jwt.InvalidTokenError:
        raise InvalidAccessTokenError(
            "Invalid or expired access token."
        ) from None

    subject = payload.get("sub")
    token_type = payload.get("type")
    token_id = payload.get("jti")

    if token_type != "access":
        raise InvalidAccessTokenError(
            "Invalid or expired access token."
        )

    if (
        not isinstance(subject, str)
        or not subject.isascii()
        or not subject.isdigit()
        or int(subject) <= 0
    ):
        raise InvalidAccessTokenError(
            "Invalid or expired access token."
        )

    if not isinstance(token_id, str) or not token_id:
        raise InvalidAccessTokenError(
            "Invalid or expired access token."
        )

    return int(subject)
