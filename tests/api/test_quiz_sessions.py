
"""Integration tests for POST /quiz-sessions."""

from collections.abc import Iterator
from hashlib import sha256
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.db.models import (
    Question,
    QuestionOption,
    QuestionSkill,
    QuizItem,
    QuizSession,
    Skill,
    User,
)
from backend.app.db.session import make_engine
from backend.app.main import app
from backend.app.security.jwt_tokens import (
    JWTSettings,
    create_access_token,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = PROJECT_ROOT / "alembic.ini"

TEST_SECRET = "test-secret-key-that-is-at-least-32-bytes-long"
GRAMMAR_CODE = "TEST_QUIZ_GRAMMAR"
VOCABULARY_CODE = "TEST_QUIZ_VOCABULARY"


def _insert_question(
    session: Session,
    *,
    content: str,
    skill_code: str,
    review_status: str = "approved",
    permission_status: str = "granted",
    option_keys: tuple[str, ...] = ("A", "B", "C", "D"),
) -> Question:
    """Insert a synthetic question for testing."""

    skill = session.scalar(
        select(Skill).where(Skill.code == skill_code)
    )
    assert skill is not None

    question = Question(
        part=5,
        content=content,
        explanation=f"Private explanation for {content}",
        correct_option_key="B",
        difficulty=2,
        review_status=review_status,
        source_type="ai_generated",
        source_name="quiz-session-test",
        source_reference=f"test:quiz-session:{content}",
        usage_permission_status=permission_status,
        visibility="public",
        content_hash=sha256(
            content.encode("utf-8")
        ).hexdigest(),
    )

    session.add(question)
    session.flush()

    for key in option_keys:
        session.add(
            QuestionOption(
                question_id=question.id,
                option_key=key,
                content=f"{key} option for {content}",
            )
        )

    session.add(
        QuestionSkill(
            question_id=question.id,
            skill_id=skill.id,
        )
    )

    session.flush()
    return question


@pytest.fixture
def quiz_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, Engine, dict[str, str]]]:
    """Create an isolated database and an authenticated test client."""

    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET)

    database_path = tmp_path / "quiz_sessions.sqlite3"
    database_url = (
        f"sqlite+pysqlite:///{database_path.as_posix()}"
    )
    test_engine = make_engine(database_url)

    config = Config(str(ALEMBIC_CONFIG))
    previous_overrides = app.dependency_overrides.copy()

    try:
        # Apply the real migrations to a temporary database.
        with test_engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        with Session(test_engine) as session:
            user = User(
                email="quiz-student@example.com",
                password_hash="test-only-hash",
                role="student",
                is_active=True,
            )
            session.add(user)
            session.flush()
            user_id = user.id

            session.add_all(
                [
                    Skill(
                        code=GRAMMAR_CODE,
                        name="Test Grammar",
                        category="grammar",
                    ),
                    Skill(
                        code=VOCABULARY_CODE,
                        name="Test Vocabulary",
                        category="vocabulary",
                    ),
                ]
            )
            session.flush()

            # Five eligible grammar questions.
            for number in range(1, 6):
                _insert_question(
                    session,
                    content=f"Eligible grammar question {number}",
                    skill_code=GRAMMAR_CODE,
                )

            # Two eligible vocabulary questions.
            for number in range(1, 3):
                _insert_question(
                    session,
                    content=f"Eligible vocabulary question {number}",
                    skill_code=VOCABULARY_CODE,
                )

            # Pending questions must not enter a practice session.
            _insert_question(
                session,
                content="Pending question",
                skill_code=GRAMMAR_CODE,
                review_status="pending_review",
            )

            # Incomplete questions must not enter a practice session.
            _insert_question(
                session,
                content="Incomplete question",
                skill_code=GRAMMAR_CODE,
                option_keys=("A", "B", "C"),
            )

            session.commit()

        token = create_access_token(
            user_id,
            settings=JWTSettings(secret_key=TEST_SECRET),
        )
        headers = {
            "Authorization": f"Bearer {token}",
        }

        def override_get_db() -> Iterator[Session]:
            with Session(test_engine) as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as client:
            yield client, test_engine, headers

    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        test_engine.dispose()


def test_create_quiz_session_saves_items_and_hides_answers(
    quiz_client: tuple[TestClient, Engine, dict[str, str]],
) -> None:
    """A session and its items are saved without leaking answers."""

    client, engine, headers = quiz_client

    response = client.post(
        "/quiz-sessions",
        json={"question_count": 3},
        headers=headers,
    )

    assert response.status_code == 201

    data = response.json()
    assert data["status"] == "in_progress"
    assert data["question_count"] == 3
    assert len(data["items"]) == 3

    items = data["items"]
    assert [item["position"] for item in items] == [1, 2, 3]
    assert len({item["question_id"] for item in items}) == 3

    for item in items:
        assert set(item) == {
            "id",
            "question_id",
            "position",
            "content",
            "difficulty",
            "options",
            "skill_codes",
        }
        assert len(item["options"]) == 4
        assert [
            option["option_key"]
            for option in item["options"]
        ] == ["A", "B", "C", "D"]

        assert "correct_option_key" not in item
        assert "answer_key_snapshot" not in item
        assert "explanation" not in item

    assert "Private explanation" not in response.text
    assert "answer_key_snapshot" not in response.text
    assert "correct_option_key" not in response.text

    # Confirm that the session and answer-key snapshots were saved.
    with Session(engine) as session:
        saved_session = session.get(QuizSession, data["id"])
        assert saved_session is not None
        assert saved_session.user_id > 0
        assert saved_session.status == "in_progress"

        saved_items = session.scalars(
            select(QuizItem)
            .where(QuizItem.quiz_session_id == data["id"])
            .order_by(QuizItem.position)
        ).all()

        assert len(saved_items) == 3
        assert [item.position for item in saved_items] == [1, 2, 3]
        assert all(
            item.answer_key_snapshot == "B"
            for item in saved_items
        )

        for item in saved_items:
            assert "correct_option_key" not in item.question_snapshot
            assert "answer_key_snapshot" not in item.question_snapshot
            assert "explanation" not in item.question_snapshot


def test_create_quiz_session_filters_by_skill(
    quiz_client: tuple[TestClient, Engine, dict[str, str]],
) -> None:
    """Only questions matching the requested skill are selected."""

    client, _, headers = quiz_client

    response = client.post(
        "/quiz-sessions",
        json={
            "question_count": 2,
            "skill_code": VOCABULARY_CODE,
        },
        headers=headers,
    )

    assert response.status_code == 201

    data = response.json()
    assert data["question_count"] == 2

    assert all(
        item["skill_codes"] == [VOCABULARY_CODE]
        for item in data["items"]
    )
    assert all(
        item["content"].startswith("Eligible vocabulary")
        for item in data["items"]
    )


def test_insufficient_questions_do_not_create_session(
    quiz_client: tuple[TestClient, Engine, dict[str, str]],
) -> None:
    """An insufficient question bank returns HTTP 409 without writes."""

    client, engine, headers = quiz_client

    response = client.post(
        "/quiz-sessions",
        json={"question_count": 50},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "message": "Not enough eligible TOEIC Part 5 questions.",
        "requested": 50,
        "available": 7,
    }

    with Session(engine) as session:
        session_count = session.scalar(
            select(func.count()).select_from(QuizSession)
        )
        item_count = session.scalar(
            select(func.count()).select_from(QuizItem)
        )

        assert session_count == 0
        assert item_count == 0


def test_create_quiz_session_requires_authentication(
    quiz_client: tuple[TestClient, Engine, dict[str, str]],
) -> None:
    """Unauthenticated requests cannot create sessions."""

    client, engine, _ = quiz_client

    response = client.post(
        "/quiz-sessions",
        json={"question_count": 1},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"

    with Session(engine) as session:
        count = session.scalar(
            select(func.count()).select_from(QuizSession)
        )
        assert count == 0


@pytest.mark.parametrize("question_count", [0, 51])
def test_invalid_question_count_is_rejected(
    quiz_client: tuple[TestClient, Engine, dict[str, str]],
    question_count: int,
) -> None:
    """Question counts outside the permitted range are rejected."""

    client, _, headers = quiz_client

    response = client.post(
        "/quiz-sessions",
        json={"question_count": question_count},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Invalid request data.",
    }


def test_create_quiz_session_is_documented(
    quiz_client: tuple[TestClient, Engine, dict[str, str]],
) -> None:
    """The endpoint is included in OpenAPI."""

    client, _, _ = quiz_client

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/quiz-sessions" in paths
    assert "post" in paths["/quiz-sessions"]
