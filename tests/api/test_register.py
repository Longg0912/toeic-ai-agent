
"""Integration tests for POST /auth/register."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.db.models import User
from backend.app.db.session import make_engine
from backend.app.main import app
from backend.app.security.password import verify_password


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = PROJECT_ROOT / "alembic.ini"

TEST_EMAIL = "student@example.com"
TEST_PASSWORD = "ExamplePassword@2026"


@pytest.fixture
def registration_client(
    tmp_path: Path,
) -> Iterator[tuple[TestClient, Engine]]:
    """Provide TestClient with an isolated SQLite database."""

    database_path = tmp_path / "register_api.sqlite3"

    database_url = (
        f"sqlite+pysqlite:///{database_path.as_posix()}"
    )

    test_engine = make_engine(database_url)

    config = Config(str(ALEMBIC_CONFIG))

    previous_overrides = app.dependency_overrides.copy()

    try:
        # Apply actual Alembic migrations to temporary SQLite.
        with test_engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        def override_get_db() -> Iterator[Session]:
            """Use the temporary DB instead of application DB."""

            with Session(test_engine) as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as client:
            yield client, test_engine

    finally:
        # Restore the application's dependencies.
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)

        test_engine.dispose()


def make_payload(
    email: str = TEST_EMAIL,
    password: str = TEST_PASSWORD,
) -> dict[str, str]:
    """Construct a valid registration request."""

    return {
        "email": email,
        "password": password,
    }


def count_users(db_engine: Engine) -> int:
    """Count users in the temporary SQLite database."""

    with Session(db_engine) as session:
        return session.scalar(
            select(func.count()).select_from(User)
        ) or 0


def test_register_success(
    registration_client: tuple[TestClient, Engine],
) -> None:
    """Registration creates a student and returns HTTP 201."""

    client, db_engine = registration_client

    response = client.post(
        "/auth/register",
        json=make_payload(),
    )

    assert response.status_code == 201

    data = response.json()

    assert isinstance(data["id"], int)
    assert data["id"] > 0
    assert data["email"] == TEST_EMAIL
    assert data["role"] == "student"
    assert data["is_active"] is True

    assert set(data) == {
        "id",
        "email",
        "role",
        "is_active",
    }

    assert TEST_PASSWORD not in response.text
    assert "password_hash" not in response.text

    assert count_users(db_engine) == 1

    # Check that SQLite contains a valid password hash.
    with Session(db_engine) as session:
        user = session.scalar(
            select(User).where(User.email == TEST_EMAIL)
        )

        assert user is not None
        assert user.password_hash != TEST_PASSWORD
        assert user.password_hash.startswith("$argon2id$")
        assert verify_password(
            TEST_PASSWORD,
            user.password_hash,
        )


def test_register_duplicate_email(
    registration_client: tuple[TestClient, Engine],
) -> None:
    """Duplicate registration returns HTTP 409."""

    client, db_engine = registration_client

    first = client.post(
        "/auth/register",
        json=make_payload(),
    )

    second = client.post(
        "/auth/register",
        json=make_payload(),
    )

    assert first.status_code == 201
    assert second.status_code == 409

    assert second.json() == {
        "detail": "Email is already registered.",
    }

    assert TEST_PASSWORD not in second.text
    assert count_users(db_engine) == 1


def test_register_duplicate_case_insensitive(
    registration_client: tuple[TestClient, Engine],
) -> None:
    """Email duplicates are rejected regardless of letter case."""

    client, db_engine = registration_client

    first = client.post(
        "/auth/register",
        json=make_payload(email="Student@Example.COM"),
    )

    second = client.post(
        "/auth/register",
        json=make_payload(email=TEST_EMAIL),
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert count_users(db_engine) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {
            "email": "not-an-email",
            "password": TEST_PASSWORD,
        },
        {
            "email": TEST_EMAIL,
            "password": "Short123!",
        },
        {
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "role": "admin",
        },
        {
            "email": TEST_EMAIL,
        },
        {
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "is_active": True,
        },
    ],
)
def test_invalid_registration_does_not_leak_input(
    registration_client: tuple[TestClient, Engine],
    payload: dict,
) -> None:
    """HTTP 422 responses must not echo submitted passwords."""

    client, db_engine = registration_client

    response = client.post(
        "/auth/register",
        json=payload,
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Invalid request data.",
    }

    # None of these attempts may create an account.
    assert count_users(db_engine) == 0

    password = payload.get("password")

    if password is not None:
        assert password not in response.text


def test_malformed_json_does_not_leak_password(
    registration_client: tuple[TestClient, Engine],
) -> None:
    """Malformed JSON must result in a safe HTTP 422 response."""

    client, db_engine = registration_client

    secret = "MalformedPassword@2026"

    malformed_body = (
        '{"email":"student@example.com",'
        f'"password":"{secret}",'
    )

    response = client.post(
        "/auth/register",
        content=malformed_body,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Invalid request data.",
    }

    assert secret not in response.text
    assert count_users(db_engine) == 0
