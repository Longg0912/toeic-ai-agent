
"""Authentication business logic for TOEIC AI Tutor.

Responsibilities:
- Find a user by email.
- Verify the stored Argon2id password hash.
- Reject inactive accounts.
- Generate a JWT after successful authentication.

This module does not define HTTP endpoints.
"""

from sqlalchemy.orm import Session

from backend.app.schemas.login import (
    TokenResponse,
    UserLoginRequest,
)
from backend.app.security.jwt_tokens import (
    JWTSettings,
    create_access_token,
    get_jwt_settings,
)
from backend.app.security.password import (
    hash_password,
    verify_password,
)
from backend.app.services.registration import (
    find_user_by_email,
)


class InvalidCredentialsError(Exception):
    """Raised when login credentials cannot be authenticated."""


# A valid synthetic hash for checking nonexistent accounts.
# It is not associated with any real user or usable account.
#
# This reduces obvious timing differences between:
# - An email that does not exist.
# - An email with an incorrect password.
#
# It does not replace API rate limiting.
_DUMMY_PASSWORD_HASH = hash_password(
    "dummy-password-for-nonexistent-account"
)


def login_user(
    session: Session,
    login_data: UserLoginRequest,
    *,
    jwt_settings: JWTSettings | None = None,
) -> TokenResponse:
    """Authenticate a user and return an access token.

    Args:
        session:
            SQLAlchemy session used for account lookup.

        login_data:
            Validated email and password.

        jwt_settings:
            Optional JWT configuration.
            Tests can inject a test-only signing secret.

    Returns:
        TokenResponse containing a signed access token.

    Raises:
        InvalidCredentialsError:
            If the account does not exist, the password
            is incorrect, or the account is inactive.

    Database behavior:
        This function does not create, modify,
        or delete users.
    """

    # 1. Read normalized email and plaintext password.
    email = login_data.email

    plain_password = (
        login_data.password.get_secret_value()
    )

    # 2. Find an existing user.
    user = find_user_by_email(
        session,
        email,
    )

    # 3. Verify a hash even when the user does not exist.
    stored_hash = (
        user.password_hash
        if user is not None
        else _DUMMY_PASSWORD_HASH
    )

    password_matches = verify_password(
        plain_password,
        stored_hash,
    )

    # 4. Reject invalid credentials and inactive accounts.
    # Use one generic error to avoid account enumeration.
    if (
        user is None
        or not password_matches
        or not user.is_active
    ):
        raise InvalidCredentialsError(
            "Invalid email or password."
        )

    # 5. Obtain JWT configuration only after authentication.
    config = (
        jwt_settings
        if jwt_settings is not None
        else get_jwt_settings()
    )

    # 6. Create an access token for the authenticated user.
    access_token = create_access_token(
        user_id=user.id,
        settings=config,
    )

    # 7. Return only the token and related metadata.
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=(
            config.access_token_expire_minutes * 60
        ),
    )
