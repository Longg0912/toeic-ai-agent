
"""Authentication API endpoints.

Routes:
- POST /auth/register
- POST /auth/login
"""
from backend.app.api.auth_deps import get_current_user
from backend.app.db.models import User
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Response,
    status,
)
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db

from backend.app.schemas.auth import (
    UserPublic,
    UserRegisterRequest,
)
from backend.app.schemas.login import (
    TokenResponse,
    UserLoginRequest,
)

from backend.app.services.registration import (
    EmailAlreadyRegisteredError,
    register_student,
)
from backend.app.services.authentication import (
    InvalidCredentialsError,
    login_user,
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Register a student account",
)
def register_user(
    registration_data: UserRegisterRequest,
    db: Annotated[Session, Depends(get_db)],
) -> UserPublic:
    """Register a student account and return public data."""

    try:
        return register_student(
            session=db,
            registration_data=registration_data,
        )

    except EmailAlreadyRegisteredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered.",
        ) from None


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Log in and obtain an access token",
)
def login_endpoint(
    login_data: UserLoginRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    """Authenticate a student and return a signed JWT.

    HTTP 200: Valid login.
    HTTP 401: Invalid credentials or inactive account.
    HTTP 422: Invalid request data.

    The JWT must not be logged or cached.
    """

    try:
        token_response = login_user(
            session=db,
            login_data=login_data,
        )

    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        ) from None

    # Prevent intermediate HTTP caches from storing tokens.
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"

    return token_response


@router.get(
    "/me",
    response_model=UserPublic,
    status_code=status.HTTP_200_OK,
    summary="Get the current authenticated user",
)
def read_current_user(
    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
) -> UserPublic:
    """Return public information about the authenticated user.

    Authentication:
        Requires a valid Bearer JWT access token.

    HTTP 200:
        Return the authenticated user's public profile.

    HTTP 401:
        Returned automatically by get_current_user()
        for missing, invalid, expired, or inactive accounts.

    Security:
        Never return passwords, password hashes,
        or the JWT access token.
    """

    return UserPublic(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
    )
