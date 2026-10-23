
"""Integration tests for POST /auth/login."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

import backend.app.services.authentication as authentication_service

from backend.app.api.deps import get_db
from backend.app.db.models import User
from backend.app.db.session import make_engine
from backend.app.main import app
from backend.app.security.jwt_tokens import (
    JWTSettings,
    decode_access_token,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = PROJECT_ROOT / "alembic.ini"

TEST_EMAIL = "student@example.com"
TEST_PASSWORD = "ExamplePassword@2026"

TEST_JWT_SETTINGS = JWTSettings(
    secret_key="test-only-login-api-secret-" + ("x" * 48),
)


@pytest.fixture
def login_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, Engine]]:
    """Create an isolated API client with temporary SQLite."""

    database_path = tmp_path / "login_api.sqlite3"

    database_url = (
        f"sqlite+pysqlite:///{database_path.as_posix()}"
    )

    test_engine = make_engine(database_url)
    config = Config(str(ALEMBIC_CONFIG))

    previous_overrides = app.dependency_overrides.copy()

    try:
        # Apply real Alembic migrations to a temporary DB.
        with test_engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        def override_get_db() -> Iterator[Session]:
            """Use only the temporary SQLite database."""

            with Session(test_engine) as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db

        # Do not use the real JWT secret during tests.
        monkeypatch.setattr(
            authentication_service,
            "get_jwt_settings",
            lambda: TEST_JWT_SETTINGS,
        )

        with TestClient(app) as client:
            yield client, test_engine

    finally:
        # Restore previous FastAPI dependency overrides.
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)

        test_engine.dispose()


def register_test_user(client: TestClient) -> int:
    """Create a student using the real registration endpoint."""

    response = client.post(
        "/auth/register",
        json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
        },
    )

    assert response.status_code == 201, response.text

    return response.json()["id"]


def make_login_payload(
    email: str = TEST_EMAIL,
    password: str = TEST_PASSWORD,
) -> dict[str, str]:
    """Build a login request."""

    return {
        "email": email,
        "password": password,
    }


def count_users(engine: Engine) -> int:
    """Count users in the temporary database."""

    with Session(engine) as session:
        return session.scalar(
            select(func.count()).select_from(User)
        ) or 0


def assert_invalid_credentials(response) -> None:
    """All credential failures should return the same error."""

    assert response.status_code == 401

    assert response.json() == {
        "detail": "Invalid email or password.",
    }

    assert response.headers["www-authenticate"] == "Bearer"

    assert "access_token" not in response.text
    assert "password_hash" not in response.text


def test_login_success_returns_jwt(
    login_client: tuple[TestClient, Engine],
) -> None:
    """Successful login returns a valid signed JWT."""

    client, engine = login_client

    user_id = register_test_user(client)

    response = client.post(
        "/auth/login",
        json=make_login_payload(),
    )

    assert response.status_code == 200

    data = response.json()

    assert set(data) == {
        "access_token",
        "token_type",
        "expires_in",
    }

    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 1800

    token = data["access_token"]

    assert decode_access_token(
        token,
        settings=TEST_JWT_SETTINGS,
    ) == user_id

    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"

    assert TEST_PASSWORD not in response.text
    assert "password_hash" not in response.text

    assert count_users(engine) == 1


def test_login_wrong_password_returns_401(
    login_client: tuple[TestClient, Engine],
) -> None:
    """Incorrect passwords must be rejected."""

    client, _ = login_client

    register_test_user(client)

    response = client.post(
        "/auth/login",
        json=make_login_payload(
            password="WrongPassword@2026",
        ),
    )

    assert_invalid_credentials(response)


def test_login_unknown_email_returns_401(
    login_client: tuple[TestClient, Engine],
) -> None:
    """Unknown accounts must not receive tokens."""

    client, engine = login_client

    response = client.post(
        "/auth/login",
        json=make_login_payload(),
    )

    assert_invalid_credentials(response)
    assert count_users(engine) == 0


def test_login_inactive_account_returns_401(
    login_client: tuple[TestClient, Engine],
) -> None:
    """Inactive accounts must not receive tokens."""

    client, engine = login_client

    user_id = register_test_user(client)

    with Session(engine) as session:
        user = session.get(User, user_id)

        assert user is not None

        user.is_active = False
        session.commit()

    response = client.post(
        "/auth/login",
        json=make_login_payload(),
    )

    assert_invalid_credentials(response)


def test_login_email_case_insensitive(
    login_client: tuple[TestClient, Engine],
) -> None:
    """Login must allow differently cased emails."""

    client, _ = login_client

    user_id = register_test_user(client)

    response = client.post(
        "/auth/login",
        json=make_login_payload(
            email="STUDENT@EXAMPLE.COM",
        ),
    )

    assert response.status_code == 200

    assert decode_access_token(
        response.json()["access_token"],
        settings=TEST_JWT_SETTINGS,
    ) == user_id


def test_login_corrupted_stored_hash_returns_401(
    login_client: tuple[TestClient, Engine],
) -> None:
    """A corrupted stored password hash must fail safely."""

    client, engine = login_client

    user_id = register_test_user(client)

    with Session(engine) as session:
        user = session.get(User, user_id)

        assert user is not None

        user.password_hash = "invalid-hash"
        session.commit()

    response = client.post(
        "/auth/login",
        json=make_login_payload(),
    )

    assert_invalid_credentials(response)


@pytest.mark.parametrize(
    "payload",
    [
        {
            "email": "not-an-email",
            "password": TEST_PASSWORD,
        },
        {
            "email": TEST_EMAIL,
        },
        {
            "email": TEST_EMAIL,
            "password": "",
        },
        {
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "role": "admin",
        },
        {
            "email": TEST_EMAIL,
            "password": "a" * 129,
        },
    ],
)
def test_invalid_login_returns_safe_422(
    login_client: tuple[TestClient, Engine],
    payload: dict,
) -> None:
    """Request validation must never echo credentials."""

    client, engine = login_client

    response = client.post(
        "/auth/login",
        json=payload,
    )

    assert response.status_code == 422

    assert response.json() == {
        "detail": "Invalid request data.",
    }

    password = payload.get("password")

    if isinstance(password, str) and password:
        assert password not in response.text

    assert "access_token" not in response.text
    assert count_users(engine) == 0


def test_malformed_json_returns_safe_422(
    login_client: tuple[TestClient, Engine],
) -> None:
    """Malformed JSON must not reveal the supplied password."""

    client, engine = login_client

    secret = "MalformedPassword@2026"

    malformed_body = (
        '{"email":"student@example.com",'
        f'"password":"{secret}",'
    )

    response = client.post(
        "/auth/login",
        content=malformed_body,
        headers={
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 422

    assert response.json() == {
        "detail": "Invalid request data.",
    }

    assert secret not in response.text
    assert count_users(engine) == 0


def test_successful_login_does_not_modify_user(
    login_client: tuple[TestClient, Engine],
) -> None:
    """Login should not overwrite user account information."""

    client, engine = login_client

    user_id = register_test_user(client)

    with Session(engine) as session:
        user = session.get(User, user_id)

        assert user is not None
        original_hash = user.password_hash

    response = client.post(
        "/auth/login",
        json=make_login_payload(),
    )

    assert response.status_code == 200

    with Session(engine) as session:
        user = session.get(User, user_id)

        assert user is not None
        assert user.password_hash == original_hash
        assert user.is_active is True

    assert count_users(engine) == 1


def test_login_appears_in_openapi(
    login_client: tuple[TestClient, Engine],
) -> None:
    """The login endpoint must appear in Swagger documentation."""

    client, _ = login_client

    response = client.get("/openapi.json")

    assert response.status_code == 200

    schema = response.json()

    assert "/auth/login" in schema["paths"]
    assert "post" in schema["paths"]["/auth/login"]

    assert "/auth/register" in schema["paths"]
    assert "/health" in schema["paths"]
