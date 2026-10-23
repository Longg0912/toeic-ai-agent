
"""Tests for role-based authorization (RBAC).

Uses:
- Temporary SQLite with Alembic migrations.
- Test-only JWT signing settings.
- Test-only protected FastAPI routes.

Does not modify the real application database.
"""

from collections.abc import Iterator
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

from backend.app.api.authorization import require_role
from backend.app.api.deps import get_db
from backend.app.db.models import User
from backend.app.db.session import make_engine
from backend.app.schemas.auth import UserRegisterRequest
from backend.app.security.jwt_tokens import (
    JWTSettings,
    create_access_token,
    decode_access_token,
)
from backend.app.services.registration import (
    register_student,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = PROJECT_ROOT / "alembic.ini"

TEST_PASSWORD = "ExamplePassword@2026"

TEST_SETTINGS = JWTSettings(
    secret_key="rbac-test-only-secret-" + ("x" * 48),
)


@pytest.fixture
def rbac_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, Engine]]:
    """Create a test app using isolated SQLite and JWT."""

    database_path = tmp_path / "rbac_test.sqlite3"

    database_url = (
        f"sqlite+pysqlite:///{database_path.as_posix()}"
    )

    test_engine = make_engine(database_url)
    config = Config(str(ALEMBIC_CONFIG))

    try:
        # 1. Apply existing migrations to temporary SQLite.
        with test_engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        # 2. Use an isolated FastAPI application.
        test_app = FastAPI()

        # 3. Override database access.
        def override_get_db() -> Iterator[Session]:
            with Session(test_engine) as session:
                yield session

        test_app.dependency_overrides[get_db] = (
            override_get_db
        )

        # 4. Validate test JWTs with a test-only secret.
        real_decoder = decode_access_token

        def decode_test_token(token: str) -> int:
            return real_decoder(
                token,
                settings=TEST_SETTINGS,
            )

        monkeypatch.setattr(
            auth_deps,
            "decode_access_token",
            decode_test_token,
        )

        # 5. Test-only route requiring student role.
        @test_app.get("/_test/student")
        def student_route(
            current_user: Annotated[
                User,
                Depends(require_role("student")),
            ],
        ) -> dict:
            return {
                "user_id": current_user.id,
                "role": current_user.role,
            }

        # 6. Test-only route requiring admin role.
        @test_app.get("/_test/admin")
        def admin_route(
            current_user: Annotated[
                User,
                Depends(require_role("admin")),
            ],
        ) -> dict:
            return {
                "user_id": current_user.id,
                "role": current_user.role,
            }

        # 7. Test-only route accepting either role.
        @test_app.get("/_test/shared")
        def shared_route(
            current_user: Annotated[
                User,
                Depends(
                    require_role("student", "admin")
                ),
            ],
        ) -> dict:
            return {
                "user_id": current_user.id,
                "role": current_user.role,
            }

        with TestClient(test_app) as client:
            yield client, test_engine

    finally:
        test_engine.dispose()


def create_user(
    engine: Engine,
    email: str,
    role: str = "student",
) -> int:
    """Register a test user and set a trusted database role."""

    if role not in {"student", "admin"}:
        raise ValueError("Unsupported test role.")

    registration = UserRegisterRequest(
        email=email,
        password=TEST_PASSWORD,
    )

    with Session(engine) as session:
        registered_user = register_student(
            session,
            registration,
        )

        user_id = registered_user.id

        if role == "admin":
            db_user = session.get(User, user_id)

            assert db_user is not None

            # This is a trusted test-only database operation.
            db_user.role = "admin"
            session.commit()

    return user_id


def set_user_role(
    engine: Engine,
    user_id: int,
    role: str,
) -> None:
    """Change a test user's role in temporary SQLite."""

    if role not in {"student", "admin"}:
        raise ValueError("Unsupported test role.")

    with Session(engine) as session:
        user = session.get(User, user_id)

        assert user is not None

        user.role = role
        session.commit()


def make_token(user_id: int) -> str:
    """Create an access token with the test-only secret."""

    return create_access_token(
        user_id,
        settings=TEST_SETTINGS,
    )


def bearer_header(token: str) -> dict[str, str]:
    """Build an Authorization header."""

    return {
        "Authorization": f"Bearer {token}",
    }


def assert_forbidden(response: Response) -> None:
    """An authenticated user without permission gets 403."""

    assert response.status_code == 403

    assert response.json() == {
        "detail": "Insufficient permissions.",
    }

    assert "password_hash" not in response.text
    assert "access_token" not in response.text


def assert_unauthorized(response: Response) -> None:
    """Unauthenticated requests get the existing 401 format."""

    assert response.status_code == 401

    assert response.json() == {
        "detail": "Could not validate credentials.",
    }

    assert (
        response.headers["www-authenticate"]
        == "Bearer"
    )


def test_student_can_access_student_route(
    rbac_client: tuple[TestClient, Engine],
) -> None:
    """Students may access student-only operations."""

    client, engine = rbac_client

    user_id = create_user(
        engine,
        email="student@example.com",
    )

    response = client.get(
        "/_test/student",
        headers=bearer_header(make_token(user_id)),
    )

    assert response.status_code == 200

    assert response.json() == {
        "user_id": user_id,
        "role": "student",
    }


def test_student_cannot_access_admin_route(
    rbac_client: tuple[TestClient, Engine],
) -> None:
    """Student JWTs cannot access admin-only operations."""

    client, engine = rbac_client

    user_id = create_user(
        engine,
        email="student@example.com",
    )

    response = client.get(
        "/_test/admin",
        headers=bearer_header(make_token(user_id)),
    )

    assert_forbidden(response)


def test_admin_can_access_admin_route(
    rbac_client: tuple[TestClient, Engine],
) -> None:
    """Administrators may access admin-only operations."""

    client, engine = rbac_client

    user_id = create_user(
        engine,
        email="admin@example.com",
        role="admin",
    )

    response = client.get(
        "/_test/admin",
        headers=bearer_header(make_token(user_id)),
    )

    assert response.status_code == 200

    assert response.json() == {
        "user_id": user_id,
        "role": "admin",
    }


def test_admin_not_automatically_student(
    rbac_client: tuple[TestClient, Engine],
) -> None:
    """Admin does not inherit student-only permissions."""

    client, engine = rbac_client

    user_id = create_user(
        engine,
        email="admin@example.com",
        role="admin",
    )

    response = client.get(
        "/_test/student",
        headers=bearer_header(make_token(user_id)),
    )

    assert_forbidden(response)


def test_student_can_access_shared_route(
    rbac_client: tuple[TestClient, Engine],
) -> None:
    """A shared operation accepts a student."""

    client, engine = rbac_client

    user_id = create_user(
        engine,
        email="student@example.com",
    )

    response = client.get(
        "/_test/shared",
        headers=bearer_header(make_token(user_id)),
    )

    assert response.status_code == 200
    assert response.json()["role"] == "student"


def test_admin_can_access_shared_route(
    rbac_client: tuple[TestClient, Engine],
) -> None:
    """A shared operation accepts an admin."""

    client, engine = rbac_client

    user_id = create_user(
        engine,
        email="admin@example.com",
        role="admin",
    )

    response = client.get(
        "/_test/shared",
        headers=bearer_header(make_token(user_id)),
    )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"


def test_missing_token_returns_401(
    rbac_client: tuple[TestClient, Engine],
) -> None:
    """Authentication happens before role authorization."""

    client, _ = rbac_client

    response = client.get("/_test/admin")

    assert_unauthorized(response)


def test_invalid_token_returns_401(
    rbac_client: tuple[TestClient, Engine],
) -> None:
    """Invalid JWTs must not reach role authorization."""

    client, _ = rbac_client

    response = client.get(
        "/_test/admin",
        headers=bearer_header("not.a.valid.jwt"),
    )

    assert_unauthorized(response)


def test_inactive_admin_returns_401(
    rbac_client: tuple[TestClient, Engine],
) -> None:
    """Even admins need an active account."""

    client, engine = rbac_client

    user_id = create_user(
        engine,
        email="admin@example.com",
        role="admin",
    )

    token = make_token(user_id)

    with Session(engine) as session:
        user = session.get(User, user_id)

        assert user is not None

        user.is_active = False
        session.commit()

    response = client.get(
        "/_test/admin",
        headers=bearer_header(token),
    )

    assert_unauthorized(response)


def test_jwt_role_claim_cannot_escalate_permissions(
    rbac_client: tuple[TestClient, Engine],
) -> None:
    """A role claim must not override the database role."""

    client, engine = rbac_client

    user_id = create_user(
        engine,
        email="student@example.com",
    )

    token = make_token(user_id)

    payload = jwt.decode(
        token,
        TEST_SETTINGS.secret_key,
        algorithms=["HS256"],
        issuer=TEST_SETTINGS.issuer,
        audience=TEST_SETTINGS.audience,
    )

    # This modified token is signed with the TEST key.
    # It is deliberately given an admin claim.
    payload["role"] = "admin"

    modified_token = jwt.encode(
        payload,
        TEST_SETTINGS.secret_key,
        algorithm="HS256",
    )

    response = client.get(
        "/_test/admin",
        headers=bearer_header(modified_token),
    )

    # The account is still a student in SQLite.
    assert_forbidden(response)


def test_role_promotion_takes_effect_with_existing_jwt(
    rbac_client: tuple[TestClient, Engine],
) -> None:
    """RBAC reads the current database role on each request."""

    client, engine = rbac_client

    user_id = create_user(
        engine,
        email="student@example.com",
    )

    token = make_token(user_id)

    before = client.get(
        "/_test/admin",
        headers=bearer_header(token),
    )

    assert_forbidden(before)

    # Trusted test-only role change.
    set_user_role(engine, user_id, "admin")

    after = client.get(
        "/_test/admin",
        headers=bearer_header(token),
    )

    assert after.status_code == 200
    assert after.json()["role"] == "admin"


def test_role_demotion_takes_effect_with_existing_jwt(
    rbac_client: tuple[TestClient, Engine],
) -> None:
    """Demoting an admin immediately removes admin access."""

    client, engine = rbac_client

    user_id = create_user(
        engine,
        email="admin@example.com",
        role="admin",
    )

    token = make_token(user_id)

    before = client.get(
        "/_test/admin",
        headers=bearer_header(token),
    )

    assert before.status_code == 200

    # Trusted test-only role change.
    set_user_role(engine, user_id, "student")

    after = client.get(
        "/_test/admin",
        headers=bearer_header(token),
    )

    assert_forbidden(after)


def test_require_role_rejects_empty_configuration() -> None:
    """Protected dependencies must specify allowed roles."""

    with pytest.raises(
        ValueError,
        match="At least one allowed role",
    ):
        require_role()


def test_require_role_rejects_unknown_role() -> None:
    """Misspelled roles fail at dependency configuration."""

    with pytest.raises(
        ValueError,
        match="Unsupported role",
    ):
        require_role("superadmin")


def test_bearer_security_appears_in_openapi(
    rbac_client: tuple[TestClient, Engine],
) -> None:
    """RBAC routes document Bearer authentication."""

    client, _ = rbac_client

    response = client.get("/openapi.json")

    assert response.status_code == 200

    schema = response.json()

    for path in (
        "/_test/student",
        "/_test/admin",
        "/_test/shared",
    ):
        assert schema["paths"][path]["get"][
            "security"
        ] == [
            {"BearerAuth": []}
        ]


def test_nonexistent_user_returns_401(
    rbac_client: tuple[TestClient, Engine],
) -> None:
    """A valid JWT for a missing user is not authorized."""

    client, _ = rbac_client

    token = make_token(999999)

    response = client.get(
        "/_test/admin",
        headers=bearer_header(token),
    )

    assert_unauthorized(response)
