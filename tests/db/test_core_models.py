"""Independent tests for the six Core database models."""

import hashlib
from collections.abc import Iterator

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.models import (
    Question,
    QuestionOption,
    QuestionSkill,
    Skill,
    StudentProfile,
    User,
)
from backend.app.db.session import make_engine


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Create a fresh in-memory SQLite database for each test."""

    test_engine = make_engine(
        "sqlite+pysqlite:///:memory:"
    )

    # Only for isolated unit tests.
    # Application databases will use Alembic migrations.
    Base.metadata.create_all(bind=test_engine)

    try:
        with Session(test_engine) as session:
            yield session
    finally:
        test_engine.dispose()


def make_question(
    content: str = "The company announced its annual results.",
    correct_option_key: str = "B",
    visibility: str = "public",
) -> Question:
    """Build a test question without persisting it."""

    content_hash = hashlib.sha256(
        content.strip().lower().encode("utf-8")
    ).hexdigest()

    return Question(
        part=5,
        content=content,
        correct_option_key=correct_option_key,
        content_hash=content_hash,
        visibility=visibility,
        source_type="original",
        review_status="draft",
        usage_permission_status="granted",
    )


def test_all_core_tables_registered() -> None:
    """All six expected tables are registered in metadata."""

    expected_tables = {
        "users",
        "student_profiles",
        "skills",
        "questions",
        "question_options",
        "question_skills",
    }

    assert expected_tables.issubset(set(Base.metadata.tables.keys()))


def test_sqlite_foreign_keys_enabled(
    db_session: Session,
) -> None:
    """SQLite connections must enforce foreign keys."""

    result = db_session.connection().exec_driver_sql(
        "PRAGMA foreign_keys"
    )

    assert result.scalar_one() == 1


def test_create_user_question_options_and_skills(
    db_session: Session,
) -> None:
    """Persist the primary Core relationships."""

    user = User(
        email="student@example.com",
        password_hash="test-hash-placeholder-not-for-authentication",
    )

    user.profile = StudentProfile(
        target_score=800,
        timezone="Asia/Ho_Chi_Minh",
    )

    skill = Skill(
        code="GRAMMAR_WORD_FORM",
        name="Word Forms",
        category="grammar",
    )

    question = make_question(
        content="The company announced its _____ results."
    )

    question.visibility = "private"
    question.owner = user

    question.options = [
        QuestionOption(option_key="A", content="finance"),
        QuestionOption(option_key="B", content="financial"),
        QuestionOption(option_key="C", content="financially"),
        QuestionOption(option_key="D", content="financing"),
    ]

    question.skill_links = [
        QuestionSkill(skill=skill),
    ]

    db_session.add(question)
    db_session.commit()

    saved_question = db_session.scalar(
        select(Question).where(
            Question.id == question.id
        )
    )

    assert saved_question is not None
    assert saved_question.correct_option_key == "B"
    assert saved_question.owner is not None
    assert saved_question.owner.email == "student@example.com"
    assert saved_question.owner.profile is not None
    assert saved_question.owner.profile.target_score == 800

    assert len(saved_question.options) == 4
    assert len(saved_question.skill_links) == 1
    assert (
        saved_question.skill_links[0].skill.code
        == "GRAMMAR_WORD_FORM"
    )


def test_email_unique_case_insensitive(
    db_session: Session,
) -> None:
    """The database rejects duplicate emails regardless of case."""

    first = User(
        email="Student@Example.com",
        password_hash="hash-placeholder-first",
    )

    second = User(
        email="student@example.com",
        password_hash="hash-placeholder-second",
    )

    db_session.add_all([first, second])

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()


def test_duplicate_option_keys_rejected(
    db_session: Session,
) -> None:
    """A question cannot contain duplicate option labels."""

    question = make_question()

    question.options = [
        QuestionOption(option_key="A", content="First"),
        QuestionOption(option_key="A", content="Duplicate"),
    ]

    db_session.add(question)

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()


def test_invalid_answer_key_rejected(
    db_session: Session,
) -> None:
    """Official answer keys must be A, B, C, or D."""

    question = make_question(
        correct_option_key="E"
    )

    db_session.add(question)

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()


def test_private_question_requires_owner(
    db_session: Session,
) -> None:
    """Private questions must have an owner."""

    question = make_question(
        visibility="private"
    )

    db_session.add(question)

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()


def test_invalid_foreign_key_rejected(
    db_session: Session,
) -> None:
    """An option must refer to an existing question."""

    option = QuestionOption(
        question_id=999999,
        option_key="A",
        content="Invalid parent question",
    )

    db_session.add(option)

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()