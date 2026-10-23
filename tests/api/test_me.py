
"""Integration tests for GET /auth/me.

Tests the real FastAPI application using:
- Temporary SQLite databases.
- Real Alembic migrations.
- Test-only JWT secrets.
- Real registration and login endpoints.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.db.models import User
from backend.app.db.session import make_engine
from backend.app.main import app
from backend.app.security.jwt_tokens import (
    JWTSettings,
    create_access_token,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = PROJECT_ROOT / "alembic.ini"

TEST_EMAIL = "student@example.com"
TEST_PASSWORD = "ExamplePassword@2026"

TEST_SECRET = (
    "test-only-auth-me-secret-" + ("x" * 48)
)

TEST_JWT_SETTINGS = JWTSettings(
    secret_key=TEST_SECRET,
)


@pytest.fixture
def me_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, Engine]]:
    """Create an API client with isolated database and JWT key."""

    database_path = tmp_path / "auth_me.sqlite3"

    database_url = (
        f"sqlite+pysqlite:///{database_path.as_posix()}"
    )

    test_engine = make_engine(database_url)

    config = Config(str(ALEMBIC_CONFIG))

    previous_overrides = (
        app.dependency_overrides.copy()
    )

    try:
        # 1. Create temporary tables with Alembic.
        with test_engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        # 2. Override the database dependency.
        def override_get_db() -> Iterator[Session]:
            with Session(test_engine) as session:
                yield session

        app.dependency_overrides[get_db] = (
            override_get_db
        )

        # 3. Use a test-only JWT secret.
        # This overrides the process environment only
        # for the lifetime of this pytest test.
        monkeypatch.setenv(
            "JWT_SECRET_KEY",
            TEST_SECRET,
        )

        # 4. Run the actual FastAPI application.
        with TestClient(app) as client:
            yield client, test_engine

    finally:
        # Restore other tests' dependency overrides.
        app.dependency_overrides.clear()
        app.dependency_overrides.update(
            previous_overrides
        )

        test_engine.dispose()


def register_test_user(
    client: TestClient,
    email: str = TEST_EMAIL,
) -> int:
    """Register one student through the HTTP API."""

    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": TEST_PASSWORD,
        },
    )

    assert response.status_code == 201

    return response.json()["id"]


def login_and_get_token(
    client: TestClient,
    email: str = TEST_EMAIL,
) -> str:
    """Login through HTTP and return the JWT."""

    response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": TEST_PASSWORD,
        },
    )

    assert response.status_code == 200

    return response.json()["access_token"]


def bearer_header(token: str) -> dict[str, str]:
    """Construct the Authorization header."""

    return {
        "Authorization": f"Bearer {token}",
    }


def assert_unauthorized(response: Response) -> None:
    """Check the standard authentication error response."""

    assert response.status_code == 401

    assert response.json() == {
        "detail": "Could not validate credentials.",
    }

    assert response.headers[
        "www-authenticate"
    ] == "Bearer"

    assert "password_hash" not in response.text
    assert "access_token" not in response.text


def test_me_after_registration_and_login_returns_public_user(
    me_client: tuple[TestClient, Engine],
) -> None:
    """Register, login, then get the authenticated profile."""

    client, _ = me_client

    user_id = register_test_user(client)

    token = login_and_get_token(client)

    response = client.get(
        "/auth/me",
        headers=bearer_header(token),
    )

    assert response.status_code == 200

    assert response.json() == {
        "id": user_id,
        "email": TEST_EMAIL,
        "role": "student",
        "is_active": True,
    }

    assert TEST_PASSWORD not in response.text
    assert "password_hash" not in response.text
    assert token not in response.text


def test_me_uses_token_owner_not_another_account(
    me_client: tuple[TestClient, Engine],
) -> None:
    """An access token identifies its own user."""

    client, _ = me_client

    first_id = register_test_user(
        client,
        email="first@example.com",
    )

    second_id = register_test_user(
        client,
        email="second@example.com",
    )

    token = login_and_get_token(
        client,
        email="second@example.com",
    )

    response = client.get(
        "/auth/me",
        headers=bearer_header(token),
    )

    assert response.status_code == 200

    assert response.json()["id"] == second_id
    assert response.json()["id"] != first_id

    assert response.json()["email"] == (
        "second@example.com"
    )


def test_me_without_authorization_returns_401(
    me_client: tuple[TestClient, Engine],
) -> None:
    """A request without JWT must fail."""

    client, _ = me_client

    response = client.get("/auth/me")

    assert_unauthorized(response)


def test_me_wrong_scheme_returns_401(
    me_client: tuple[TestClient, Engine],
) -> None:
    """Basic authentication is not accepted."""

    client, _ = me_client

    response = client.get(
        "/auth/me",
        headers={
            "Authorization": "Basic abc123",
        },
    )

    assert_unauthorized(response)


def test_me_empty_bearer_returns_401(
    me_client: tuple[TestClient, Engine],
) -> None:
    """A Bearer header without a token is rejected."""

    client, _ = me_client

    response = client.get(
        "/auth/me",
        headers={
            "Authorization": "Bearer",
        },
    )

    assert_unauthorized(response)


def test_me_malformed_token_returns_401(
    me_client: tuple[TestClient, Engine],
) -> None:
    """Malformed JWT data must fail."""

    client, _ = me_client

    response = client.get(
        "/auth/me",
        headers=bearer_header("not.a.valid.jwt"),
    )

    assert_unauthorized(response)


def test_me_expired_token_returns_401(
    me_client: tuple[TestClient, Engine],
) -> None:
    """An expired JWT must not access /auth/me."""

    client, _ = me_client

    expired_at = (
        datetime.now(timezone.utc)
        - timedelta(hours=2)
    )

    token = create_access_token(
        1,
        settings=TEST_JWT_SETTINGS,
        now=expired_at,
    )

    response = client.get(
        "/auth/me",
        headers=bearer_header(token),
    )

    assert_unauthorized(response)


def test_me_wrong_signing_secret_returns_401(
    me_client: tuple[TestClient, Engine],
) -> None:
    """Tokens signed by another secret must fail."""

    client, _ = me_client

    other_settings = JWTSettings(
        secret_key=(
            "another-test-secret-" + ("z" * 48)
        ),
    )

    token = create_access_token(
        1,
        settings=other_settings,
    )

    response = client.get(
        "/auth/me",
        headers=bearer_header(token),
    )

    assert_unauthorized(response)


def test_me_nonexistent_user_returns_401(
    me_client: tuple[TestClient, Engine],
) -> None:
    """A valid JWT for a missing user must fail."""

    client, _ = me_client

    token = create_access_token(
        999999,
        settings=TEST_JWT_SETTINGS,
    )

    response = client.get(
        "/auth/me",
        headers=bearer_header(token),
    )

    assert_unauthorized(response)


def test_me_inactive_account_returns_401(
    me_client: tuple[TestClient, Engine],
) -> None:
    """Disabled users cannot reuse previously issued JWTs."""

    client, engine = me_client

    user_id = register_test_user(client)

    token = login_and_get_token(client)

    # Disable the account after issuing its token.
    with Session(engine) as session:
        user = session.get(User, user_id)

        assert user is not None

        user.is_active = False
        session.commit()

    response = client.get(
        "/auth/me",
        headers=bearer_header(token),
    )

    assert_unauthorized(response)


def test_me_tampered_token_returns_401(
    me_client: tuple[TestClient, Engine],
) -> None:
    """Changing a JWT payload invalidates its signature."""

    client, _ = me_client

    token = create_access_token(
        1,
        settings=TEST_JWT_SETTINGS,
    )

    header, payload, signature = token.split(".")

    changed_payload = (
        ("A" if payload[0] != "A" else "B")
        + payload[1:]
    )

    tampered = (
        f"{header}.{changed_payload}.{signature}"
    )

    response = client.get(
        "/auth/me",
        headers=bearer_header(tampered),
    )

    assert_unauthorized(response)


def test_me_refresh_type_token_returns_401(
    me_client: tuple[TestClient, Engine],
) -> None:
    """Tokens with type=refresh cannot act as access tokens."""

    client, _ = me_client

    original_token = create_access_token(
        1,
        settings=TEST_JWT_SETTINGS,
    )

    payload = jwt.decode(
        original_token,
        TEST_SECRET,
        algorithms=["HS256"],
        issuer=TEST_JWT_SETTINGS.issuer,
        audience=TEST_JWT_SETTINGS.audience,
    )

    payload["type"] = "refresh"

    modified_token = jwt.encode(
        payload,
        TEST_SECRET,
        algorithm="HS256",
    )

    response = client.get(
        "/auth/me",
        headers=bearer_header(modified_token),
    )

    assert_unauthorized(response)


def test_me_does_not_change_user_record(
    me_client: tuple[TestClient, Engine],
) -> None:
    """A profile read must not modify the account."""

    client, engine = me_client

    user_id = register_test_user(client)

    token = login_and_get_token(client)

    with Session(engine) as session:
        user = session.get(User, user_id)

        assert user is not None
        original_hash = user.password_hash

    response = client.get(
        "/auth/me",
        headers=bearer_header(token),
    )

    assert response.status_code == 200

    with Session(engine) as session:
        user = session.get(User, user_id)

        assert user is not None
        assert user.password_hash == original_hash
        assert user.is_active is True


def test_me_security_declared_in_openapi(
    me_client: tuple[TestClient, Engine],
) -> None:
    """Swagger documents /auth/me as Bearer-protected."""

    client, _ = me_client

    response = client.get("/openapi.json")

    assert response.status_code == 200

    schema = response.json()

    assert "/auth/me" in schema["paths"]
    assert "get" in schema["paths"]["/auth/me"]

    get_operation = schema["paths"][
        "/auth/me"
    ]["get"]

    assert get_operation["security"] == [
        {"BearerAuth": []}
    ]

    assert "/auth/register" in schema["paths"]
    assert "/auth/login" in schema["paths"]
    assert "/health" in schema["paths"]
