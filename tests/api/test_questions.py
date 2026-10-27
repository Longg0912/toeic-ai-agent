
"""Integration tests for GET /questions/part5."""

from collections.abc import Iterator
from hashlib import sha256
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.db.models import (
    Question,
    QuestionOption,
    QuestionSkill,
    Skill,
    User,
)
from backend.app.db.session import make_engine
from backend.app.main import app


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = PROJECT_ROOT / "alembic.ini"


def _insert_question(
    session: Session,
    *,
    content: str,
    skill_code: str,
    review_status: str = "approved",
    permission_status: str = "granted",
    visibility: str = "public",
    owner_user_id: int | None = None,
) -> Question:
    """Insert one synthetic question into the test database."""

    skill = session.scalar(
        select(Skill).where(Skill.code == skill_code)
    )
    assert skill is not None, f"Missing test skill: {skill_code}"

    question = Question(
        part=5,
        content=content,
        explanation="Test-only explanation: option B is correct.",
        correct_option_key="B",
        difficulty=2,
        review_status=review_status,
        source_type="ai_generated",
        source_name="questions-api-test",
        source_reference=f"test:questions-api:{content}",
        usage_permission_status=permission_status,
        visibility=visibility,
        owner_user_id=owner_user_id,
        content_hash=sha256(
            content.encode("utf-8")
        ).hexdigest(),
    )

    session.add(question)
    session.flush()

    for key, option_content in [
        ("A", "Option A"),
        ("B", "Option B"),
        ("C", "Option C"),
        ("D", "Option D"),
    ]:
        session.add(
            QuestionOption(
                question_id=question.id,
                option_key=key,
                content=option_content,
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
def questions_client(
    tmp_path: Path,
) -> Iterator[TestClient]:
    """Use a migrated, isolated SQLite database for API tests."""

    database_path = tmp_path / "questions_api.sqlite3"
    database_url = (
        f"sqlite+pysqlite:///{database_path.as_posix()}"
    )

    test_engine = make_engine(database_url)
    config = Config(str(ALEMBIC_CONFIG))
    previous_overrides = app.dependency_overrides.copy()

    try:
        # Apply the real migrations to the temporary database.
        with test_engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        # Create test data, including ineligible questions.
        with Session(test_engine) as session:
            owner = User(
                email="private-owner@example.com",
                password_hash="test-only-hash",
                role="student",
                is_active=True,
            )
            session.add(owner)
            session.flush()
                    # Create any skills needed by this isolated test database.
            test_skills = [
                ("GRAMMAR_PREPOSITIONS", "Prepositions"),
                ("GRAMMAR_WORD_FORM", "Word Form"),
            ]

            existing_skill_codes = set(
                session.scalars(
                    select(Skill.code)
                ).all()
            )

            for code, name in test_skills:
                if code not in existing_skill_codes:
                    session.add(
                        Skill(
                            code=code,
                            name=f"{name} (test)",
                            category="grammar",
                        )
                    )

            session.flush()
            # Two questions eligible for public practice.
            _insert_question(
                session,
                content="The meeting starts at nine o'clock.",
                skill_code="GRAMMAR_PREPOSITIONS",
            )
            _insert_question(
                session,
                content="The company announced a significant increase.",
                skill_code="GRAMMAR_WORD_FORM",
            )

            # Must be hidden because it has not been approved.
            _insert_question(
                session,
                content="Pending question must not be public.",
                skill_code="GRAMMAR_PREPOSITIONS",
                review_status="pending_review",
            )

            # Must be hidden because usage permission is unknown.
            _insert_question(
                session,
                content="Question with unknown permission.",
                skill_code="GRAMMAR_PREPOSITIONS",
                permission_status="unknown",
            )

            # Must be hidden because permission is restricted.
            _insert_question(
                session,
                content="Question with restricted permission.",
                skill_code="GRAMMAR_PREPOSITIONS",
                permission_status="restricted",
            )

            # Must be hidden because it is private.
            _insert_question(
                session,
                content="Private question must not be public.",
                skill_code="GRAMMAR_PREPOSITIONS",
                visibility="private",
                owner_user_id=owner.id,
            )

            session.commit()

        def override_get_db() -> Iterator[Session]:
            """Use the temporary database for API requests."""

            with Session(test_engine) as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as client:
            yield client

    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        test_engine.dispose()


def test_list_part5_returns_only_eligible_questions(
    questions_client: TestClient,
) -> None:
    """Only approved, permitted, public questions are returned."""

    response = questions_client.get("/questions/part5")

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 2
    assert data["limit"] == 10
    assert data["offset"] == 0
    assert len(data["items"]) == 2

    contents = {
        item["content"]
        for item in data["items"]
    }

    assert contents == {
        "The meeting starts at nine o'clock.",
        "The company announced a significant increase.",
    }


def test_filter_part5_by_skill_code(
    questions_client: TestClient,
) -> None:
    """The skill filter returns only matching questions."""

    response = questions_client.get(
        "/questions/part5",
        params={"skill_code": "GRAMMAR_PREPOSITIONS"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["skill_codes"] == [
        "GRAMMAR_PREPOSITIONS"
    ]


def test_part5_pagination(
    questions_client: TestClient,
) -> None:
    """Pagination limits the returned items but preserves total."""

    response = questions_client.get(
        "/questions/part5",
        params={"limit": 1, "offset": 1},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 2
    assert data["limit"] == 1
    assert data["offset"] == 1
    assert len(data["items"]) == 1


def test_part5_response_does_not_leak_answer(
    questions_client: TestClient,
) -> None:
    """Practice responses must not expose the answer or explanation."""

    response = questions_client.get("/questions/part5")

    assert response.status_code == 200

    data = response.json()
    question = data["items"][0]

    assert {
        "id",
        "content",
        "difficulty",
        "options",
        "skill_codes",
    } == set(question)

    assert "correct_option_key" not in question
    assert "explanation" not in question

    assert [
        option["option_key"]
        for option in question["options"]
    ] == ["A", "B", "C", "D"]

    assert "Test-only explanation" not in response.text


def test_part5_endpoint_is_documented(
    questions_client: TestClient,
) -> None:
    """The endpoint and query parameters appear in OpenAPI."""

    response = questions_client.get("/openapi.json")

    assert response.status_code == 200

    paths = response.json()["paths"]

    assert "/questions/part5" in paths
    assert "get" in paths["/questions/part5"]
