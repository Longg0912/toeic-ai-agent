
"""Tests for JWT Bearer authentication dependency.

All tests use:
- Temporary SQLite.
- Real Alembic migrations.
- Test-only JWT signing secret.
- Test-only protected FastAPI route.

The production database is never used.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

import jwt
import pytest

from alembic import command
from alembic.config import Config
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine
from sqlalchemy.orm import Session

import backend.app.api.auth_deps as auth_deps

from backend.app.api.auth_deps import get_current_user
from backend.app.api.deps import get_db
from backend.app.db.models import User
from backend.app.db.session import make_engine
from backend.app.schemas.auth import UserRegisterRequest
from backend.app.schemas.login import UserLoginRequest
from backend.app.security.jwt_tokens import (
    JWTSettings,
    create_access_token,
    decode_access_token,
)
from backend.app.services.authentication import login_user
from backend.app.services.registration import register_student


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = PROJECT_ROOT / "alembic.ini"

TEST_EMAIL = "student@example.com"
TEST_PASSWORD = "ExamplePassword@2026"

TEST_JWT_SETTINGS = JWTSettings(
    secret_key="test-only-auth-deps-secret-" + ("x" * 48),
)


@pytest.fixture
def auth_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, Engine]]:
    """Create a protected test API with temporary SQLite."""

    database_path = tmp_path / "auth_deps.sqlite3"

    database_url = (
        f"sqlite+pysqlite:///{database_path.as_posix()}"
    )

    test_engine = make_engine(database_url)
    config = Config(str(ALEMBIC_CONFIG))

    try:
        # 1. Create tables using actual Alembic migrations.
        with test_engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        # 2. Create an isolated FastAPI application.
        test_app = FastAPI()

        # 3. Redirect get_db to temporary SQLite.
        def override_get_db() -> Iterator[Session]:
            with Session(test_engine) as session:
                yield session

        test_app.dependency_overrides[get_db] = (
            override_get_db
        )

        # 4. Patch only the dependency's JWT decoder,
        # not the global JWT module.
        real_decoder = decode_access_token

        def decode_test_token(token: str) -> int:
            return real_decoder(
                token,
                settings=TEST_JWT_SETTINGS,
            )

        monkeypatch.setattr(
            auth_deps,
            "decode_access_token",
            decode_test_token,
        )

        # 5. This route exists only in tests.
        @test_app.get("/_test/protected")
        def protected_endpoint(
            current_user: Annotated[
                User,
                Depends(get_current_user),
            ],
        ) -> dict:
            return {
                "id": current_user.id,
                "email": current_user.email,
            }

        # 6. Test requests against the isolated app.
        with TestClient(test_app) as client:
            yield client, test_engine

    finally:
        test_engine.dispose()


def create_student(engine: Engine) -> int:
    """Create one real ORM user in temporary SQLite."""

    registration = UserRegisterRequest(
        email=TEST_EMAIL,
        password=TEST_PASSWORD,
    )

    with Session(engine) as session:
        user = register_student(
            session,
            registration,
        )

    return user.id


def make_token(
    user_id: int,
    *,
    settings: JWTSettings = TEST_JWT_SETTINGS,
    now: datetime | None = None,
) -> str:
    """Create a JWT using test-only signing settings."""

    return create_access_token(
        user_id,
        settings=settings,
        now=now,
    )


def bearer_header(token: str) -> dict[str, str]:
    """Construct an Authorization header."""

    return {
        "Authorization": f"Bearer {token}",
    }


def assert_unauthorized(response: Response) -> None:
    """Verify a consistent HTTP 401 response."""

    assert response.status_code == 401

    assert response.json() == {
        "detail": "Could not validate credentials.",
    }

    assert (
        response.headers["www-authenticate"]
        == "Bearer"
    )

    assert "access_token" not in response.text
    assert "password_hash" not in response.text


def test_valid_bearer_token_returns_current_user(
    auth_client: tuple[TestClient, Engine],
) -> None:
    """A valid JWT resolves to the correct active user."""

    client, engine = auth_client
    user_id = create_student(engine)

    token = make_token(user_id)

    response = client.get(
        "/_test/protected",
        headers=bearer_header(token),
    )

    assert response.status_code == 200

    assert response.json() == {
        "id": user_id,
        "email": TEST_EMAIL,
    }

    assert "password" not in response.text
    assert "password_hash" not in response.text


def test_login_service_token_can_access_protected_route(
    auth_client: tuple[TestClient, Engine],
) -> None:
    """A token issued by login_user works with the dependency."""

    client, engine = auth_client
    user_id = create_student(engine)

    with Session(engine) as session:
        login_result = login_user(
            session,
            UserLoginRequest(
                email=TEST_EMAIL,
                password=TEST_PASSWORD,
            ),
            jwt_settings=TEST_JWT_SETTINGS,
        )

    response = client.get(
        "/_test/protected",
        headers=bearer_header(
            login_result.access_token
        ),
    )

    assert response.status_code == 200
    assert response.json()["id"] == user_id


def test_missing_authorization_header_returns_401(
    auth_client: tuple[TestClient, Engine],
) -> None:
    """Requests without Authorization must be rejected."""

    client, _ = auth_client

    response = client.get("/_test/protected")

    assert_unauthorized(response)


def test_wrong_authentication_scheme_returns_401(
    auth_client: tuple[TestClient, Engine],
) -> None:
    """Basic credentials are not accepted as Bearer JWTs."""

    client, _ = auth_client

    response = client.get(
        "/_test/protected",
        headers={
            "Authorization": "Basic abc123",
        },
    )

    assert_unauthorized(response)


def test_bearer_without_token_returns_401(
    auth_client: tuple[TestClient, Engine],
) -> None:
    """Bearer without credentials must be rejected."""

    client, _ = auth_client

    response = client.get(
        "/_test/protected",
        headers={
            "Authorization": "Bearer",
        },
    )

    assert_unauthorized(response)


def test_malformed_jwt_returns_401(
    auth_client: tuple[TestClient, Engine],
) -> None:
    """Malformed JWT strings must not be accepted."""

    client, _ = auth_client

    response = client.get(
        "/_test/protected",
        headers=bearer_header("not.a.valid.jwt"),
    )

    assert_unauthorized(response)


def test_expired_jwt_returns_401(
    auth_client: tuple[TestClient, Engine],
) -> None:
    """Expired JWTs must be rejected."""

    client, engine = auth_client
    user_id = create_student(engine)

    past = datetime.now(timezone.utc) - timedelta(
        hours=2
    )

    token = make_token(
        user_id,
        now=past,
    )

    response = client.get(
        "/_test/protected",
        headers=bearer_header(token),
    )

    assert_unauthorized(response)


def test_wrong_signing_secret_returns_401(
    auth_client: tuple[TestClient, Engine],
) -> None:
    """JWTs signed with another secret must be rejected."""

    client, engine = auth_client
    user_id = create_student(engine)

    wrong_settings = JWTSettings(
        secret_key="wrong-test-signing-key-" + ("z" * 48),
    )

    token = make_token(
        user_id,
        settings=wrong_settings,
    )

    response = client.get(
        "/_test/protected",
        headers=bearer_header(token),
    )

    assert_unauthorized(response)


def test_nonexistent_user_returns_401(
    auth_client: tuple[TestClient, Engine],
) -> None:
    """A valid JWT for a missing account is insufficient."""

    client, _ = auth_client

    token = make_token(999999)

    response = client.get(
        "/_test/protected",
        headers=bearer_header(token),
    )

    assert_unauthorized(response)


def test_inactive_user_returns_401(
    auth_client: tuple[TestClient, Engine],
) -> None:
    """A disabled account cannot keep using its JWT."""

    client, engine = auth_client
    user_id = create_student(engine)

    token = make_token(user_id)

    # Disable the account after the token was issued.
    with Session(engine) as session:
        user = session.get(User, user_id)

        assert user is not None

        user.is_active = False
        session.commit()

    response = client.get(
        "/_test/protected",
        headers=bearer_header(token),
    )

    assert_unauthorized(response)


def test_wrong_token_type_returns_401(
    auth_client: tuple[TestClient, Engine],
) -> None:
    """A signed token with type=refresh is not an access token."""

    client, engine = auth_client
    user_id = create_student(engine)

    original_token = make_token(user_id)

    payload = jwt.decode(
        original_token,
        TEST_JWT_SETTINGS.secret_key,
        algorithms=["HS256"],
        issuer=TEST_JWT_SETTINGS.issuer,
        audience=TEST_JWT_SETTINGS.audience,
    )

    payload["type"] = "refresh"

    invalid_token = jwt.encode(
        payload,
        TEST_JWT_SETTINGS.secret_key,
        algorithm="HS256",
    )

    response = client.get(
        "/_test/protected",
        headers=bearer_header(invalid_token),
    )

    assert_unauthorized(response)


def test_tampered_jwt_returns_401(
    auth_client: tuple[TestClient, Engine],
) -> None:
    """Modified JWT payloads must fail signature verification."""

    client, engine = auth_client
    user_id = create_student(engine)

    original_token = make_token(user_id)

    header, payload, signature = (
        original_token.split(".")
    )

    changed_payload = (
        ("A" if payload[0] != "A" else "B")
        + payload[1:]
    )

    tampered_token = (
        f"{header}.{changed_payload}.{signature}"
    )

    response = client.get(
        "/_test/protected",
        headers=bearer_header(tampered_token),
    )

    assert_unauthorized(response)


def test_bearer_security_scheme_appears_in_openapi(
    auth_client: tuple[TestClient, Engine],
) -> None:
    """Swagger must identify the route as Bearer-protected."""

    client, _ = auth_client

    response = client.get("/openapi.json")

    assert response.status_code == 200

    schema = response.json()

    security_scheme = schema["components"][
        "securitySchemes"
    ]["BearerAuth"]

    assert security_scheme["type"] == "http"
    assert security_scheme["scheme"] == "bearer"

    protected_get = schema["paths"][
        "/_test/protected"
    ]["get"]

    assert protected_get["security"] == [
        {"BearerAuth": []}
    ]
