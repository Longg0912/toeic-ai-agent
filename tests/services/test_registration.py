
"""Tests for the student registration service."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.models import User
from backend.app.db.session import make_engine
from backend.app.schemas.auth import UserRegisterRequest
from backend.app.security.password import verify_password

from backend.app.services.registration import (
    EmailAlreadyRegisteredError,
    find_user_by_email,
    register_student,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = PROJECT_ROOT / "alembic.ini"

TEST_PASSWORD = "SecurePassword@2026"


@pytest.fixture
def registration_engine(
    tmp_path: Path,
) -> Iterator[Engine]:
    """Create a temporary, migrated SQLite database."""

    database_path = tmp_path / "registration_test.sqlite3"

    database_url = (
        f"sqlite+pysqlite:///{database_path.as_posix()}"
    )

    test_engine = make_engine(database_url)

    config = Config(str(ALEMBIC_CONFIG))

    try:
        with test_engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        yield test_engine

    finally:
        test_engine.dispose()


def make_registration(
    email: str = "student@example.com",
) -> UserRegisterRequest:
    """Build valid registration data."""

    return UserRegisterRequest(
        email=email,
        password=TEST_PASSWORD,
    )


def count_users(engine: Engine) -> int:
    """Count users in the temporary database."""

    with Session(engine) as session:
        return session.scalar(
            select(func.count()).select_from(User)
        ) or 0


def test_register_student_success(
    registration_engine: Engine,
) -> None:
    """Registration must create a student account."""

    data = make_registration()

    with Session(registration_engine) as session:
        result = register_student(
            session,
            data,
        )

    assert result.id > 0
    assert result.email == "student@example.com"
    assert result.role == "student"
    assert result.is_active is True

    assert count_users(registration_engine) == 1


def test_registration_hashes_password(
    registration_engine: Engine,
) -> None:
    """Only a password hash may be stored in SQLite."""

    data = make_registration()

    with Session(registration_engine) as session:
        result = register_student(session, data)

    with Session(registration_engine) as session:
        user = session.get(User, result.id)

        assert user is not None

        assert user.password_hash != TEST_PASSWORD
        assert user.password_hash.startswith("$argon2id$")

        assert verify_password(
            TEST_PASSWORD,
            user.password_hash,
        ) is True


def test_duplicate_email_is_rejected(
    registration_engine: Engine,
) -> None:
    """Duplicate registrations must not create another user."""

    with Session(registration_engine) as session:
        register_student(
            session,
            make_registration(),
        )

    with Session(registration_engine) as session:
        with pytest.raises(
            EmailAlreadyRegisteredError,
        ):
            register_student(
                session,
                make_registration(),
            )

    assert count_users(registration_engine) == 1


def test_duplicate_email_case_insensitive(
    registration_engine: Engine,
) -> None:
    """Emails must be compared without case sensitivity."""

    with Session(registration_engine) as session:
        register_student(
            session,
            make_registration("Student@Example.COM"),
        )

    with Session(registration_engine) as session:
        with pytest.raises(
            EmailAlreadyRegisteredError,
        ):
            register_student(
                session,
                make_registration("student@example.com"),
            )

    assert count_users(registration_engine) == 1


def test_registration_returns_no_sensitive_data(
    registration_engine: Engine,
) -> None:
    """Public responses must not expose stored password hashes."""

    with Session(registration_engine) as session:
        result = register_student(
            session,
            make_registration(),
        )

    response_data = result.model_dump()

    assert "password" not in response_data
    assert "password_hash" not in response_data

    assert TEST_PASSWORD not in str(response_data)

    assert set(response_data) == {
        "id",
        "email",
        "role",
        "is_active",
    }


def test_find_user_by_email(
    registration_engine: Engine,
) -> None:
    """Email lookup must find an existing account."""

    with Session(registration_engine) as session:
        created = register_student(
            session,
            make_registration(),
        )

    with Session(registration_engine) as session:
        found = find_user_by_email(
            session,
            "STUDENT@EXAMPLE.COM",
        )

        assert found is not None
        assert found.id == created.id


def test_unique_constraint_rejects_duplicate_insert(
    registration_engine: Engine,
) -> None:
    """The database must prevent duplicate email inserts."""

    with Session(registration_engine) as session:
        register_student(
            session,
            make_registration(),
        )

    with Session(registration_engine) as session:
        duplicate = User(
            email="STUDENT@EXAMPLE.COM",
            password_hash="test-only-hash",
            role="student",
            is_active=True,
        )

        session.add(duplicate)

        with pytest.raises(IntegrityError):
            session.commit()

        session.rollback()

    assert count_users(registration_engine) == 1
