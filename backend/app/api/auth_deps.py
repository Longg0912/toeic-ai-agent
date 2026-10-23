
"""Authentication dependencies for protected FastAPI routes.

Responsibilities:
- Read Bearer JWT credentials from HTTP requests.
- Validate JWT access tokens.
- Load the current user from SQLite.
- Reject missing, invalid, expired, or inactive accounts.

No new API endpoints are defined here.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.db.models import User

from backend.app.security.jwt_tokens import (
    InvalidAccessTokenError,
    decode_access_token,
)


# FastAPI extracts the Authorization: Bearer <token> header.
#
# auto_error=False allows get_current_user() to return
# a consistent HTTP 401 response for missing or invalid
# Authorization headers.
bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="BearerAuth",
    bearerFormat="JWT",
    description=(
        "Enter the JWT access token obtained from "
        "POST /auth/login."
    ),
)


def credentials_exception() -> HTTPException:
    """Build a consistent HTTP 401 authentication error."""

    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={
            "WWW-Authenticate": "Bearer",
        },
    )


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> User:
    """Validate a Bearer token and return the active user.

    Args:
        credentials:
            Bearer credentials extracted by FastAPI.

        db:
            SQLAlchemy database session supplied by get_db.

    Returns:
        The authenticated SQLAlchemy User instance.

    Raises:
        HTTPException:
            HTTP 401 if the token is missing, invalid,
            expired, or the user is missing or inactive.

    Security:
        Token claims are verified before the user lookup.
        Client-supplied user IDs are not trusted.
    """

    # 1. Require a Bearer token.
    if credentials is None:
        raise credentials_exception()

    if credentials.scheme.lower() != "bearer":
        raise credentials_exception()

    token = credentials.credentials

    if not token:
        raise credentials_exception()

    # 2. Validate the JWT and extract its User ID.
    try:
        user_id = decode_access_token(token)

    except InvalidAccessTokenError:
        raise credentials_exception() from None

    # 3. Load the current user from the database.
    user = db.get(User, user_id)

    # 4. The account must still exist and be active.
    if user is None or not user.is_active:
        raise credentials_exception()

    # 5. Return the authenticated ORM object.
    return user
