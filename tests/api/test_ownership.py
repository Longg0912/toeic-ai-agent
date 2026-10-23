
"""Integration tests for QuizSession resource ownership.

Tests:
- Students may access their own QuizSessions.
- Students cannot read or modify other students' data.
- Unauthenticated requests return HTTP 401.
- Wrong roles return HTTP 403.
- Missing or non-owned resources return HTTP 404.

No test touches the production SQLite database.
"""

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import pytest

from alembic import command
from alembic.config import Config
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine
from sqlalchemy.orm import Session

import backend.app.api.auth_deps as auth_deps

from backend.app.api.deps import get_db
from backend.app.api.ownership import (
    get_owned_quiz_session,
)
from backend.app.db.models import (
    QuizSession,
    User,
)
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

TEST_JWT_SETTINGS = JWTSettings(
    secret_key="test-only-ownership-key-" + ("x" * 48),
)


@pytest.fixture
def ownership_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, Engine]]:
    """Create an isolated test API and temporary database."""

    database_path = tmp_path / "ownership_test.sqlite3"

    database_url = (
        f"sqlite+pysqlite:///{database_path.as_posix()}"
    )

    test_engine = make_engine(database_url)

    config = Config(str(ALEMBIC_CONFIG))

    try:
        # 1. Apply real Alembic migrations.
        with test_engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        # 2. Create a test-only FastAPI application.
        test_app = FastAPI()

        # 3. Override the database dependency.
        def override_get_db() -> Iterator[Session]:
            with Session(test_engine) as session:
                yield session

        test_app.dependency_overrides[get_db] = (
            override_get_db
        )

        # 4. Validate JWTs with a test-only secret.
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

        # 5. Test-only endpoint: read an owned quiz.
        @test_app.get(
            "/_test/quiz-sessions/{quiz_session_id}"
        )
        def read_quiz_session(
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

        # 6. Test-only endpoint: submit an owned quiz.
        @test_app.patch(
            "/_test/quiz-sessions/{quiz_session_id}/submit"
        )
        def submit_quiz_session(
            quiz: Annotated[
                QuizSession,
                Depends(get_owned_quiz_session),
            ],
            db: Annotated[
                Session,
                Depends(get_db),
            ],
        ) -> dict:
            quiz.status = "submitted"

            # Store a UTC datetime compatible with the
            # current SQLite DateTime convention.
            quiz.finished_at = datetime.now(
                timezone.utc
            ).replace(tzinfo=None)

            db.commit()
            db.refresh(quiz)

            return {
                "id": quiz.id,
                "status": quiz.status,
            }

        # 7. Execute HTTP requests against the test app.
        with TestClient(test_app) as client:
            yield client, test_engine

    finally:
        test_engine.dispose()


def create_student(
    engine: Engine,
    email: str,
    *,
    role: str = "student",
) -> int:
    """Create a user in temporary SQLite.

    Admin promotion here is test-only and performed
    directly through a trusted database session.
    """

    if role not in {"student", "admin"}:
        raise ValueError("Unsupported test role.")

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


def create_quiz_session(
    engine: Engine,
    owner_id: int,
) -> int:
    """Insert a QuizSession owned by one user."""

    with Session(engine) as session:
        quiz = QuizSession(
            user_id=owner_id,
            status="in_progress",
        )

        session.add(quiz)
        session.commit()
        session.refresh(quiz)

        return quiz.id


def make_token(user_id: int) -> str:
    """Generate a signed test-only access token."""

    return create_access_token(
        user_id,
        settings=TEST_JWT_SETTINGS,
    )


def bearer_header(
    token: str,
) -> dict[str, str]:
    """Create an HTTP Bearer Authorization header."""

    return {
        "Authorization": f"Bearer {token}",
    }


def quiz_url(quiz_session_id: int) -> str:
    return (
        f"/_test/quiz-sessions/{quiz_session_id}"
    )


def submit_url(quiz_session_id: int) -> str:
    return quiz_url(quiz_session_id) + "/submit"


def assert_not_found(response: Response) -> None:
    """Non-owned and nonexistent quizzes look identical."""

    assert response.status_code == 404

    assert response.json() == {
        "detail": "Quiz session not found.",
    }

    assert "user_id" not in response.text
    assert "password_hash" not in response.text


def assert_unauthorized(response: Response) -> None:
    """Invalid authentication must produce HTTP 401."""

    assert response.status_code == 401

    assert response.json() == {
        "detail": "Could not validate credentials.",
    }

    assert (
        response.headers["www-authenticate"]
        == "Bearer"
    )


def test_owner_can_read_own_quiz(
    ownership_client: tuple[TestClient, Engine],
) -> None:
    """Student A may read their own quiz."""

    client, engine = ownership_client

    owner_id = create_student(
        engine,
        "student-a@example.com",
    )

    quiz_id = create_quiz_session(
        engine,
        owner_id,
    )

    response = client.get(
        quiz_url(quiz_id),
        headers=bearer_header(make_token(owner_id)),
    )

    assert response.status_code == 200

    assert response.json() == {
        "id": quiz_id,
        "user_id": owner_id,
        "status": "in_progress",
    }


def test_owner_can_read_multiple_own_quizzes(
    ownership_client: tuple[TestClient, Engine],
) -> None:
    """A student may read several sessions they own."""

    client, engine = ownership_client

    owner_id = create_student(
        engine,
        "student-a@example.com",
    )

    first_quiz = create_quiz_session(
        engine,
        owner_id,
    )

    second_quiz = create_quiz_session(
        engine,
        owner_id,
    )

    headers = bearer_header(
        make_token(owner_id)
    )

    for quiz_id in (first_quiz, second_quiz):
        response = client.get(
            quiz_url(quiz_id),
            headers=headers,
        )

        assert response.status_code == 200
        assert response.json()["user_id"] == owner_id


def test_student_cannot_read_another_users_quiz(
    ownership_client: tuple[TestClient, Engine],
) -> None:
    """Student A cannot read a quiz owned by Student B."""

    client, engine = ownership_client

    student_a = create_student(
        engine,
        "student-a@example.com",
    )

    student_b = create_student(
        engine,
        "student-b@example.com",
    )

    quiz_b = create_quiz_session(
        engine,
        student_b,
    )

    response = client.get(
        quiz_url(quiz_b),
        headers=bearer_header(make_token(student_a)),
    )

    assert_not_found(response)


def test_nonexistent_quiz_returns_404(
    ownership_client: tuple[TestClient, Engine],
) -> None:
    """A missing quiz does not leak account information."""

    client, engine = ownership_client

    student_id = create_student(
        engine,
        "student@example.com",
    )

    response = client.get(
        quiz_url(999999),
        headers=bearer_header(make_token(student_id)),
    )

    assert_not_found(response)


def test_foreign_and_missing_quiz_responses_match(
    ownership_client: tuple[TestClient, Engine],
) -> None:
    """A non-owned resource is indistinguishable from missing."""

    client, engine = ownership_client

    student_a = create_student(
        engine,
        "student-a@example.com",
    )

    student_b = create_student(
        engine,
        "student-b@example.com",
    )

    quiz_b = create_quiz_session(
        engine,
        student_b,
    )

    headers = bearer_header(
        make_token(student_a)
    )

    foreign_response = client.get(
        quiz_url(quiz_b),
        headers=headers,
    )

    missing_response = client.get(
        quiz_url(999999),
        headers=headers,
    )

    assert_not_found(foreign_response)
    assert_not_found(missing_response)

    assert (
        foreign_response.json()
        == missing_response.json()
    )


def test_missing_token_returns_401(
    ownership_client: tuple[TestClient, Engine],
) -> None:
    """Ownership checks still require authentication."""

    client, engine = ownership_client

    student_id = create_student(
        engine,
        "student@example.com",
    )

    quiz_id = create_quiz_session(
        engine,
        student_id,
    )

    response = client.get(quiz_url(quiz_id))

    assert_unauthorized(response)


def test_invalid_token_returns_401(
    ownership_client: tuple[TestClient, Engine],
) -> None:
    """Malformed JWTs cannot reach owned resources."""

    client, engine = ownership_client

    student_id = create_student(
        engine,
        "student@example.com",
    )

    quiz_id = create_quiz_session(
        engine,
        student_id,
    )

    response = client.get(
        quiz_url(quiz_id),
        headers=bearer_header(
            "not.a.valid.jwt"
        ),
    )

    assert_unauthorized(response)


def test_inactive_owner_returns_401(
    ownership_client: tuple[TestClient, Engine],
) -> None:
    """An inactive user cannot access their own old quizzes."""

    client, engine = ownership_client

    student_id = create_student(
        engine,
        "student@example.com",
    )

    quiz_id = create_quiz_session(
        engine,
        student_id,
    )

    token = make_token(student_id)

    with Session(engine) as session:
        user = session.get(User, student_id)

        assert user is not None

        user.is_active = False
        session.commit()

    response = client.get(
        quiz_url(quiz_id),
        headers=bearer_header(token),
    )

    assert_unauthorized(response)


def test_admin_has_no_automatic_ownership_bypass(
    ownership_client: tuple[TestClient, Engine],
) -> None:
    """An admin is not automatically authorized as a student."""

    client, engine = ownership_client

    admin_id = create_student(
        engine,
        "admin@example.com",
        role="admin",
    )

    quiz_id = create_quiz_session(
        engine,
        admin_id,
    )

    response = client.get(
        quiz_url(quiz_id),
        headers=bearer_header(make_token(admin_id)),
    )

    assert response.status_code == 403

    assert response.json() == {
        "detail": "Insufficient permissions.",
    }


def test_query_parameter_cannot_override_owner(
    ownership_client: tuple[TestClient, Engine],
) -> None:
    """A client-supplied user_id cannot override JWT identity."""

    client, engine = ownership_client

    student_a = create_student(
        engine,
        "student-a@example.com",
    )

    student_b = create_student(
        engine,
        "student-b@example.com",
    )

    quiz_b = create_quiz_session(
        engine,
        student_b,
    )

    response = client.get(
        quiz_url(quiz_b),
        params={"user_id": student_b},
        headers=bearer_header(make_token(student_a)),
    )

    assert_not_found(response)


def test_owner_can_submit_own_quiz(
    ownership_client: tuple[TestClient, Engine],
) -> None:
    """An owner may execute a protected write operation."""

    client, engine = ownership_client

    owner_id = create_student(
        engine,
        "student@example.com",
    )

    quiz_id = create_quiz_session(
        engine,
        owner_id,
    )

    response = client.patch(
        submit_url(quiz_id),
        headers=bearer_header(make_token(owner_id)),
    )

    assert response.status_code == 200

    assert response.json() == {
        "id": quiz_id,
        "status": "submitted",
    }

    with Session(engine) as session:
        quiz = session.get(QuizSession, quiz_id)

        assert quiz is not None
        assert quiz.status == "submitted"


def test_other_student_cannot_modify_quiz(
    ownership_client: tuple[TestClient, Engine],
) -> None:
    """Student A cannot submit a quiz belonging to Student B."""

    client, engine = ownership_client

    student_a = create_student(
        engine,
        "student-a@example.com",
    )

    student_b = create_student(
        engine,
        "student-b@example.com",
    )

    quiz_b = create_quiz_session(
        engine,
        student_b,
    )

    response = client.patch(
        submit_url(quiz_b),
        headers=bearer_header(make_token(student_a)),
    )

    assert_not_found(response)

    # Confirm the unauthorized request changed nothing.
    with Session(engine) as session:
        quiz = session.get(QuizSession, quiz_b)

        assert quiz is not None
        assert quiz.status == "in_progress"
        assert quiz.user_id == student_b
        assert quiz.finished_at is None


def test_ownership_change_takes_effect_immediately(
    ownership_client: tuple[TestClient, Engine],
) -> None:
    """Ownership is determined from the current database state."""

    client, engine = ownership_client

    student_a = create_student(
        engine,
        "student-a@example.com",
    )

    student_b = create_student(
        engine,
        "student-b@example.com",
    )

    quiz_id = create_quiz_session(
        engine,
        student_a,
    )

    token_a = make_token(student_a)
    token_b = make_token(student_b)

    before = client.get(
        quiz_url(quiz_id),
        headers=bearer_header(token_a),
    )

    assert before.status_code == 200

    # Simulate a trusted ownership correction in test DB.
    with Session(engine) as session:
        quiz = session.get(QuizSession, quiz_id)

        assert quiz is not None

        quiz.user_id = student_b
        session.commit()

    after_a = client.get(
        quiz_url(quiz_id),
        headers=bearer_header(token_a),
    )

    after_b = client.get(
        quiz_url(quiz_id),
        headers=bearer_header(token_b),
    )

    assert_not_found(after_a)

    assert after_b.status_code == 200
    assert after_b.json()["user_id"] == student_b


def test_ownership_route_declares_bearer_security(
    ownership_client: tuple[TestClient, Engine],
) -> None:
    """Protected test routes appear as Bearer secured in OpenAPI."""

    client, _ = ownership_client

    response = client.get("/openapi.json")

    assert response.status_code == 200

    schema = response.json()

    read_operation = schema["paths"][
        "/_test/quiz-sessions/{quiz_session_id}"
    ]["get"]

    submit_operation = schema["paths"][
        "/_test/quiz-sessions/{quiz_session_id}/submit"
    ]["patch"]

    assert read_operation["security"] == [
        {"BearerAuth": []}
    ]

    assert submit_operation["security"] == [
        {"BearerAuth": []}
    ]
