
"""Security regression tests for authentication and authorization.

Covers:
- Broken Object Level Authorization (BOLA / IDOR).
- Unauthorized database writes.
- Request parameter tampering.
- JWT claim and signing-algorithm attacks.
- Role changes and account deactivation.
- Consistent error responses.

Uses temporary SQLite, test-only JWT secrets,
and test-only FastAPI routes.

No production database is accessed.
"""

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import jwt
import pytest

from alembic import command
from alembic.config import Config

from fastapi import Body, Depends, FastAPI
from fastapi.testclient import TestClient

from sqlalchemy import Engine
from sqlalchemy.orm import Session

import backend.app.api.auth_deps as auth_deps

from backend.app.api.authorization import require_role
from backend.app.api.deps import get_db
from backend.app.api.ownership import (
    get_owned_quiz_session,
)

from backend.app.db.models import QuizSession, User
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

TEST_PASSWORD = "SecurePassword@2026"

TEST_JWT_SETTINGS = JWTSettings(
    secret_key="security-regression-test-" + ("x" * 48),
)


@pytest.fixture
def security_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, Engine]]:
    """Create an isolated test application and database."""

    database_path = tmp_path / "authorization_security.sqlite3"

    database_url = (
        f"sqlite+pysqlite:///{database_path.as_posix()}"
    )

    engine = make_engine(database_url)

    alembic_config = Config(str(ALEMBIC_CONFIG))

    try:
        # 1. Create the temporary database schema.
        with engine.begin() as connection:
            alembic_config.attributes["connection"] = connection
            command.upgrade(alembic_config, "head")

        # 2. Create an application only for these tests.
        test_app = FastAPI()

        # 3. Redirect all database dependencies to SQLite temp.
        def override_get_db() -> Iterator[Session]:
            with Session(engine) as session:
                yield session

        test_app.dependency_overrides[get_db] = (
            override_get_db
        )

        # 4. Verify tokens with a test-only secret.
        real_decoder = decode_access_token

        def decode_test_jwt(token: str) -> int:
            return real_decoder(
                token,
                settings=TEST_JWT_SETTINGS,
            )

        monkeypatch.setattr(
            auth_deps,
            "decode_access_token",
            decode_test_jwt,
        )

        # 5. Test route for reading an owned QuizSession.
        @test_app.get(
            "/_security/quiz-sessions/{quiz_session_id}"
        )
        def read_quiz(
            quiz: Annotated[
                QuizSession,
                Depends(get_owned_quiz_session),
            ],
        ) -> dict:
            return {
                "id": quiz.id,
                "user_id": quiz.user_id,
                "status": quiz.status,
            }

        # 6. Test route for modifying an owned QuizSession.
        @test_app.patch(
            "/_security/quiz-sessions/{quiz_session_id}"
        )
        def submit_quiz(
            payload: Annotated[
                dict[str, object],
                Body(),
            ],
            quiz: Annotated[
                QuizSession,
                Depends(get_owned_quiz_session),
            ],
            db: Annotated[
                Session,
                Depends(get_db),
            ],
        ) -> dict:
            # Deliberately ignore client-supplied user_id.
            # Only update the already-authorized QuizSession.
            quiz.status = "submitted"
            quiz.finished_at = datetime.now(
                timezone.utc
            ).replace(tzinfo=None)

            db.commit()

            return {
                "id": quiz.id,
                "status": quiz.status,
            }

        # 7. Test route that requires the admin role.
        @test_app.get("/_security/admin")
        def admin_operation(
            current_user: Annotated[
                User,
                Depends(require_role("admin")),
            ],
        ) -> dict:
            return {
                "user_id": current_user.id,
                "role": current_user.role,
            }

        with TestClient(test_app) as client:
            yield client, engine

    finally:
        engine.dispose()


def create_user(
    engine: Engine,
    email: str,
    *,
    role: str = "student",
) -> int:
    """Create a test account with a trusted database role."""

    assert role in {"student", "admin"}

    registration = UserRegisterRequest(
        email=email,
        password=TEST_PASSWORD,
    )

    with Session(engine) as session:
        result = register_student(
            session,
            registration,
        )

        user_id = result.id

        if role == "admin":
            user = session.get(User, user_id)

            assert user is not None
            user.role = "admin"
            session.commit()

    return user_id


def create_quiz(engine: Engine, owner_id: int) -> int:
    """Create a QuizSession in the temporary database."""

    with Session(engine) as session:
        quiz = QuizSession(
            user_id=owner_id,
            status="in_progress",
        )

        session.add(quiz)
        session.commit()
        session.refresh(quiz)

        return quiz.id


def set_role(
    engine: Engine,
    user_id: int,
    role: str,
) -> None:
    """Update a test account's role directly in SQLite."""

    assert role in {"student", "admin"}

    with Session(engine) as session:
        user = session.get(User, user_id)

        assert user is not None

        user.role = role
        session.commit()


def disable_user(engine: Engine, user_id: int) -> None:
    """Disable a test account in temporary SQLite."""

    with Session(engine) as session:
        user = session.get(User, user_id)

        assert user is not None

        user.is_active = False
        session.commit()


def read_quiz_state(
    engine: Engine,
    quiz_id: int,
) -> tuple[str, int, object]:
    """Read the stored state after an HTTP request."""

    with Session(engine) as session:
        quiz = session.get(QuizSession, quiz_id)

        assert quiz is not None

        return (
            quiz.status,
            quiz.user_id,
            quiz.finished_at,
        )


def make_token(user_id: int) -> str:
    """Create a real signed JWT with test configuration."""

    return create_access_token(
        user_id,
        settings=TEST_JWT_SETTINGS,
    )


def claims_for(user_id: int) -> dict:
    """Decode a valid test JWT for security mutation tests."""

    return jwt.decode(
        make_token(user_id),
        TEST_JWT_SETTINGS.secret_key,
        algorithms=["HS256"],
        issuer=TEST_JWT_SETTINGS.issuer,
        audience=TEST_JWT_SETTINGS.audience,
    )


def sign_test_claims(
    claims: dict,
    *,
    secret: str | None = None,
    algorithm: str = "HS256",
) -> str:
    """Sign deliberately modified claims for isolated tests."""

    return jwt.encode(
        claims,
        secret or TEST_JWT_SETTINGS.secret_key,
        algorithm=algorithm,
    )


def auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
    }


def quiz_url(quiz_id: int | str) -> str:
    return f"/_security/quiz-sessions/{quiz_id}"


def assert_status_401(response) -> None:
    assert response.status_code == 401
    assert response.json() == {
        "detail": "Could not validate credentials.",
    }
    assert response.headers["www-authenticate"] == "Bearer"


def assert_status_403(response) -> None:
    assert response.status_code == 403
    assert response.json() == {
        "detail": "Insufficient permissions.",
    }


def assert_status_404(response) -> None:
    assert response.status_code == 404
    assert response.json() == {
        "detail": "Quiz session not found.",
    }


# -----------------------------------------------------
# Group A - Object ownership and unauthorized writes
# -----------------------------------------------------


def test_foreign_quiz_read_is_blocked(
    security_client,
) -> None:
    """Student A cannot read Student B's QuizSession."""

    client, engine = security_client

    student_a = create_user(engine, "a@example.com")
    student_b = create_user(engine, "b@example.com")
    quiz_b = create_quiz(engine, student_b)

    response = client.get(
        quiz_url(quiz_b),
        headers=auth_headers(make_token(student_a)),
    )

    assert_status_404(response)

    assert "user_id" not in response.text
    assert "password_hash" not in response.text


def test_foreign_quiz_write_changes_nothing(
    security_client,
) -> None:
    """An unauthorized PATCH cannot change another user's quiz."""

    client, engine = security_client

    student_a = create_user(engine, "a@example.com")
    student_b = create_user(engine, "b@example.com")
    quiz_b = create_quiz(engine, student_b)

    before = read_quiz_state(engine, quiz_b)

    response = client.patch(
        quiz_url(quiz_b),
        json={
            "status": "submitted",
            "user_id": student_a,
        },
        headers=auth_headers(make_token(student_a)),
    )

    assert_status_404(response)

    after = read_quiz_state(engine, quiz_b)

    assert after == before


def test_foreign_and_missing_quiz_have_same_response(
    security_client,
) -> None:
    """Do not disclose whether a foreign quiz exists."""

    client, engine = security_client

    student_a = create_user(engine, "a@example.com")
    student_b = create_user(engine, "b@example.com")
    quiz_b = create_quiz(engine, student_b)

    headers = auth_headers(make_token(student_a))

    foreign = client.get(
        quiz_url(quiz_b),
        headers=headers,
    )

    missing = client.get(
        quiz_url(999999),
        headers=headers,
    )

    assert_status_404(foreign)
    assert_status_404(missing)

    assert foreign.json() == missing.json()


def test_query_and_body_cannot_override_owner(
    security_client,
) -> None:
    """Client parameters cannot replace the JWT-derived owner."""

    client, engine = security_client

    student_a = create_user(engine, "a@example.com")
    student_b = create_user(engine, "b@example.com")

    quiz_a = create_quiz(engine, student_a)
    quiz_b = create_quiz(engine, student_b)

    token_a = make_token(student_a)
    headers = auth_headers(token_a)

    # Attempt to read B's quiz using spoofed query fields.
    read_response = client.get(
        quiz_url(quiz_b),
        params={
            "user_id": student_b,
            "owner_id": student_b,
            "role": "admin",
        },
        headers=headers,
    )

    assert_status_404(read_response)

    # Attempt to change A's owner through the body.
    update_response = client.patch(
        quiz_url(quiz_a),
        json={
            "status": "submitted",
            "user_id": student_b,
            "owner_id": student_b,
            "role": "admin",
        },
        headers=headers,
    )

    assert update_response.status_code == 200

    own_state = read_quiz_state(engine, quiz_a)
    foreign_state = read_quiz_state(engine, quiz_b)

    assert own_state[0] == "submitted"
    assert own_state[1] == student_a

    assert foreign_state[0] == "in_progress"
    assert foreign_state[1] == student_b


# -----------------------------------------------------
# Group B - Privilege escalation and JWT forgery
# -----------------------------------------------------


def test_signed_role_claim_cannot_grant_admin(
    security_client,
) -> None:
    """A JWT role claim cannot override User.role in SQLite."""

    client, engine = security_client

    student_id = create_user(
        engine,
        "student@example.com",
    )

    claims = claims_for(student_id)

    # Test-only signature: the real account is still student.
    claims["role"] = "admin"

    token = sign_test_claims(claims)

    response = client.get(
        "/_security/admin",
        headers=auth_headers(token),
    )

    assert_status_403(response)


def test_signed_owner_claim_cannot_grant_quiz_access(
    security_client,
) -> None:
    """Extra JWT ownership claims cannot bypass SQL filtering."""

    client, engine = security_client

    student_a = create_user(engine, "a@example.com")
    student_b = create_user(engine, "b@example.com")

    quiz_b = create_quiz(engine, student_b)

    claims = claims_for(student_a)

    claims["user_id"] = student_b
    claims["owner_id"] = student_b
    claims["role"] = "admin"

    token = sign_test_claims(claims)

    response = client.get(
        quiz_url(quiz_b),
        headers=auth_headers(token),
    )

    assert_status_404(response)


def test_forged_subject_with_wrong_signature_is_rejected(
    security_client,
) -> None:
    """Changing sub cannot impersonate the quiz's owner."""

    client, engine = security_client

    student_a = create_user(engine, "a@example.com")
    student_b = create_user(engine, "b@example.com")

    quiz_b = create_quiz(engine, student_b)

    claims = claims_for(student_a)
    claims["sub"] = str(student_b)

    attacker_secret = (
        "attacker-test-secret-" + ("z" * 48)
    )

    forged_token = sign_test_claims(
        claims,
        secret=attacker_secret,
    )

    response = client.get(
        quiz_url(quiz_b),
        headers=auth_headers(forged_token),
    )

    assert_status_401(response)


@pytest.mark.parametrize(
    "claim,new_value",
    [
        ("exp", None),
        ("iss", None),
        ("aud", None),
        ("jti", None),
        ("nbf", None),
        ("type", "refresh"),
        ("sub", "not-a-valid-user-id"),
        ("aud", "another-api"),
    ],
)
def test_invalid_security_claims_are_rejected(
    security_client,
    claim: str,
    new_value: str | None,
) -> None:
    """Required and security-sensitive JWT claims are verified."""

    client, engine = security_client

    student_id = create_user(
        engine,
        "student@example.com",
    )

    quiz_id = create_quiz(engine, student_id)

    claims = claims_for(student_id)

    if new_value is None:
        claims.pop(claim)
    else:
        claims[claim] = new_value

    token = sign_test_claims(claims)

    response = client.get(
        quiz_url(quiz_id),
        headers=auth_headers(token),
    )

    assert_status_401(response)


@pytest.mark.parametrize(
    "algorithm",
    ["none", "HS384"],
)
def test_unapproved_jwt_algorithms_are_rejected(
    security_client,
    algorithm: str,
) -> None:
    """Only the explicitly permitted HS256 algorithm is accepted."""

    client, engine = security_client

    student_id = create_user(
        engine,
        "student@example.com",
    )

    quiz_id = create_quiz(engine, student_id)

    claims = claims_for(student_id)

    if algorithm == "none":
        token = jwt.encode(
            claims,
            key=None,
            algorithm="none",
        )
    else:
        token = sign_test_claims(
            claims,
            algorithm="HS384",
        )

    response = client.get(
        quiz_url(quiz_id),
        headers=auth_headers(token),
    )

    assert_status_401(response)


# -----------------------------------------------------
# Group C - Account state and role changes
# -----------------------------------------------------


def test_disabled_account_loses_existing_access(
    security_client,
) -> None:
    """An already-issued JWT stops working for an inactive user."""

    client, engine = security_client

    student_id = create_user(
        engine,
        "student@example.com",
    )

    quiz_id = create_quiz(engine, student_id)

    token = make_token(student_id)

    before = client.get(
        quiz_url(quiz_id),
        headers=auth_headers(token),
    )

    assert before.status_code == 200

    disable_user(engine, student_id)

    after = client.get(
        quiz_url(quiz_id),
        headers=auth_headers(token),
    )

    assert_status_401(after)


def test_role_promotion_does_not_bypass_ownership(
    security_client,
) -> None:
    """Promotion to admin cannot bypass student-only ownership."""

    client, engine = security_client

    student_a = create_user(engine, "a@example.com")
    student_b = create_user(engine, "b@example.com")

    quiz_b = create_quiz(engine, student_b)

    token_a = make_token(student_a)
    headers = auth_headers(token_a)

    before = client.get(
        "/_security/admin",
        headers=headers,
    )

    assert_status_403(before)

    set_role(engine, student_a, "admin")

    admin_response = client.get(
        "/_security/admin",
        headers=headers,
    )

    assert admin_response.status_code == 200

    # Admin has no automatic access to student-owned quizzes.
    foreign_quiz = client.get(
        quiz_url(quiz_b),
        headers=headers,
    )

    assert_status_403(foreign_quiz)


def test_role_demotion_removes_admin_privileges(
    security_client,
) -> None:
    """Existing JWTs use the current role, not a cached role."""

    client, engine = security_client

    user_id = create_user(
        engine,
        "admin@example.com",
        role="admin",
    )

    token = make_token(user_id)
    headers = auth_headers(token)

    before = client.get(
        "/_security/admin",
        headers=headers,
    )

    assert before.status_code == 200

    set_role(engine, user_id, "student")

    after = client.get(
        "/_security/admin",
        headers=headers,
    )

    assert_status_403(after)


def test_anonymous_patch_cannot_modify_quiz(
    security_client,
) -> None:
    """A missing JWT cannot be used for a database write."""

    client, engine = security_client

    owner_id = create_user(
        engine,
        "owner@example.com",
    )

    quiz_id = create_quiz(engine, owner_id)

    before = read_quiz_state(engine, quiz_id)

    response = client.patch(
        quiz_url(quiz_id),
        json={"status": "submitted"},
    )

    assert_status_401(response)

    after = read_quiz_state(engine, quiz_id)

    assert after == before


# -----------------------------------------------------
# Group D - Invalid resource identifiers
# -----------------------------------------------------


@pytest.mark.parametrize(
    "quiz_id",
    ["0", "-1", "not-an-integer"],
)
def test_invalid_quiz_identifiers_are_rejected(
    security_client,
    quiz_id: str,
) -> None:
    """Invalid resource IDs cannot reach the ownership query."""

    client, engine = security_client

    student_id = create_user(
        engine,
        "student@example.com",
    )

    response = client.get(
        quiz_url(quiz_id),
        headers=auth_headers(make_token(student_id)),
    )

    assert response.status_code == 422
    assert "password_hash" not in response.text
    assert "access_token" not in response.text
