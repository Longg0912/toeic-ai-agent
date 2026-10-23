
"""Student registration business logic.

This module:
- Checks whether an email is already registered.
- Hashes passwords using Argon2id.
- Creates accounts with the student role.
- Handles database uniqueness conflicts.
- Returns only public user information.

It does not define HTTP endpoints.
"""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.models import User
from backend.app.schemas.auth import (
    UserPublic,
    UserRegisterRequest,
)
from backend.app.security.password import hash_password


class EmailAlreadyRegisteredError(Exception):
    """Raised when a registration email is already in use."""


def find_user_by_email(
    session: Session,
    email: str,
) -> User | None:
    """Find an account by email, ignoring ASCII letter case."""

    normalized_email = email.lower()

    statement = select(User).where(
        func.lower(User.email) == normalized_email
    )

    return session.scalar(statement)


def register_student(
    session: Session,
    registration_data: UserRegisterRequest,
) -> UserPublic:
    """Create a new student account.

    Args:
        session:
            SQLAlchemy session dedicated to the request.
        registration_data:
            Validated registration information.

    Returns:
        Public information of the newly created user.

    Raises:
        EmailAlreadyRegisteredError:
            When the email already exists.
        IntegrityError:
            For other database integrity failures.

    Transaction policy:
        This service commits on success and rolls back
        when a database write fails.

        The caller should provide a dedicated session
        with no unrelated pending changes.
    """

    email = registration_data.email.lower()

    # Step 1: Check whether the email already exists.
    existing_user = find_user_by_email(
        session,
        email,
    )

    if existing_user is not None:
        raise EmailAlreadyRegisteredError(
            "Email is already registered."
        )

    # Step 2: Retrieve the validated plaintext password.
    # Never log or persist this plaintext value.
    plain_password = (
        registration_data.password.get_secret_value()
    )

    # Step 3: Hash the password with Argon2id.
    password_hash = hash_password(plain_password)

    # Step 4: Create a student account.
    # Never accept role or is_active from the client.
    user = User(
        email=email,
        password_hash=password_hash,
        role="student",
        is_active=True,
    )

    session.add(user)

    # Step 5: Persist the new account.
    try:
        session.commit()

    except IntegrityError:
        session.rollback()

        # Another request may have registered the same email
        # between the initial check and the INSERT.
        if find_user_by_email(session, email) is not None:
            raise EmailAlreadyRegisteredError(
                "Email is already registered."
            ) from None

        # Do not disguise unrelated database errors
        # as duplicate-email errors.
        raise

    except Exception:
        session.rollback()
        raise

    # Step 6: Load the generated primary key and defaults.
    session.refresh(user)

    # Step 7: Never return the password hash.
    return UserPublic.model_validate(user)
