
"""Tests for the login authentication service."""

from collections.abc import Iterator
from pathlib import Path

import jwt
import pytest

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

import backend.app.services.authentication as auth_service

from backend.app.db.models import User
from backend.app.db.session import make_engine
from backend.app.schemas.auth import UserRegisterRequest
from backend.app.schemas.login import UserLoginRequest
from backend.app.security.jwt_tokens import (
    JWTSettings,
    decode_access_token,
)
from backend.app.services.authentication import (
    InvalidCredentialsError,
    login_user,
)
from backend.app.services.registration import register_student


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = PROJECT_ROOT / "alembic.ini"

TEST_EMAIL = "student@example.com"
TEST_PASSWORD = "ExamplePassword@2026"

TEST_JWT_SETTINGS = JWTSettings(
    secret_key="test-only-login-secret-" + ("x" * 48),
)


@pytest.fixture
def login_engine(tmp_path: Path) -> Iterator[Engine]:
    """Create an isolated SQLite database with Alembic."""

    database_path = tmp_path / "login_test.sqlite3"

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


def create_student(
    engine: Engine,
    email: str = TEST_EMAIL,
    password: str = TEST_PASSWORD,
) -> int:
    """Register one test student and return the ID."""

    registration = UserRegisterRequest(
        email=email,
        password=password,
    )

    with Session(engine) as session:
        user = register_student(
            session,
            registration,
        )

    return user.id


def make_login(
    email: str = TEST_EMAIL,
    password: str = TEST_PASSWORD,
) -> UserLoginRequest:
    """Create valid login input."""

    return UserLoginRequest(
        email=email,
        password=password,
    )


def count_users(engine: Engine) -> int:
    """Count users in temporary SQLite."""

    with Session(engine) as session:
        return session.scalar(
            select(func.count()).select_from(User)
        ) or 0


def test_login_success_returns_valid_jwt(
    login_engine: Engine,
) -> None:
    """Correct credentials produce a signed access token."""

    user_id = create_student(login_engine)

    with Session(login_engine) as session:
        result = login_user(
            session,
            make_login(),
            jwt_settings=TEST_JWT_SETTINGS,
        )

    assert result.token_type == "bearer"
    assert result.expires_in == 1800

    assert decode_access_token(
        result.access_token,
        settings=TEST_JWT_SETTINGS,
    ) == user_id

    claims = jwt.decode(
        result.access_token,
        TEST_JWT_SETTINGS.secret_key,
        algorithms=["HS256"],
        issuer=TEST_JWT_SETTINGS.issuer,
        audience=TEST_JWT_SETTINGS.audience,
    )

    assert claims["sub"] == str(user_id)

    assert set(claims) == {
        "sub",
        "type",
        "iss",
        "aud",
        "iat",
        "nbf",
        "exp",
        "jti",
    }

    assert TEST_PASSWORD not in result.model_dump_json()


def test_login_wrong_password_rejected(
    login_engine: Engine,
) -> None:
    """An incorrect password must not receive a JWT."""

    create_student(login_engine)

    with Session(login_engine) as session:
        with pytest.raises(
            InvalidCredentialsError,
            match="Invalid email or password",
        ):
            login_user(
                session,
                make_login(
                    password="WrongPassword@2026"
                ),
                jwt_settings=TEST_JWT_SETTINGS,
            )


def test_login_unknown_email_rejected(
    login_engine: Engine,
) -> None:
    """Unknown accounts must not receive a JWT."""

    with Session(login_engine) as session:
        with pytest.raises(
            InvalidCredentialsError,
            match="Invalid email or password",
        ):
            login_user(
                session,
                make_login(),
                jwt_settings=TEST_JWT_SETTINGS,
            )


def test_login_inactive_account_rejected(
    login_engine: Engine,
) -> None:
    """Inactive accounts cannot authenticate."""

    user_id = create_student(login_engine)

    with Session(login_engine) as session:
        user = session.get(User, user_id)

        assert user is not None

        user.is_active = False
        session.commit()

    with Session(login_engine) as session:
        with pytest.raises(
            InvalidCredentialsError,
            match="Invalid email or password",
        ):
            login_user(
                session,
                make_login(),
                jwt_settings=TEST_JWT_SETTINGS,
            )


def test_login_email_case_insensitive(
    login_engine: Engine,
) -> None:
    """Email lookup must be case insensitive."""

    user_id = create_student(login_engine)

    with Session(login_engine) as session:
        result = login_user(
            session,
            make_login(
                email="STUDENT@EXAMPLE.COM"
            ),
            jwt_settings=TEST_JWT_SETTINGS,
        )

    assert decode_access_token(
        result.access_token,
        settings=TEST_JWT_SETTINGS,
    ) == user_id


def test_login_corrupted_hash_rejected(
    login_engine: Engine,
) -> None:
    """Invalid stored password hashes must fail safely."""

    user_id = create_student(login_engine)

    with Session(login_engine) as session:
        user = session.get(User, user_id)

        assert user is not None

        user.password_hash = "invalid-stored-hash"
        session.commit()

    with Session(login_engine) as session:
        with pytest.raises(InvalidCredentialsError):
            login_user(
                session,
                make_login(),
                jwt_settings=TEST_JWT_SETTINGS,
            )


def test_failed_login_does_not_modify_users(
    login_engine: Engine,
) -> None:
    """A failed login must not create or remove accounts."""

    create_student(login_engine)

    before = count_users(login_engine)

    with Session(login_engine) as session:
        with pytest.raises(InvalidCredentialsError):
            login_user(
                session,
                make_login(
                    password="IncorrectPassword@2026"
                ),
                jwt_settings=TEST_JWT_SETTINGS,
            )

    after = count_users(login_engine)

    assert before == after == 1


def test_login_requires_jwt_configuration(
    login_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful credentials cannot bypass missing JWT config."""

    create_student(login_engine)

    def missing_settings() -> JWTSettings:
        raise RuntimeError("JWT_SECRET_KEY is missing.")

    monkeypatch.setattr(
        auth_service,
        "get_jwt_settings",
        missing_settings,
    )

    with Session(login_engine) as session:
        with pytest.raises(
            RuntimeError,
            match="JWT_SECRET_KEY is missing",
        ):
            login_user(
                session,
                make_login(),
            )
