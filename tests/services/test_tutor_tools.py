
"""Tests for the extensible TOEIC Tutor Tool Registry."""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.db.models import (
    Attempt,
    Question,
    QuestionSkill,
    QuizItem,
    QuizSession,
    Skill,
    StudentProfile,
    User,
)
from backend.app.services.tutor_tools import (
    ToolDefinition,
    ToolInputError,
    ToolRegistry,
    TUTOR_TOOL_REGISTRY,
    UnknownToolError,
)


@pytest.fixture
def db() -> Iterator[Session]:
    """Create an isolated in-memory SQLite database."""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session

    engine.dispose()


def create_user(
    db: Session,
    email: str,
) -> User:
    user = User(
        email=email,
        password_hash="test-only-password-hash",
    )
    db.add(user)
    db.flush()
    return user


def create_question(
    db: Session,
    user_id: int,
    skill: Skill,
    question_number: int,
    correct: bool,
) -> None:
    """Create one question, quiz item, and first attempt."""

    question = Question(
        part=5,
        content=f"Test question {question_number}",
        correct_option_key="A",
        content_hash=f"{question_number:064d}",
    )
    db.add(question)
    db.flush()

    db.add(
        QuestionSkill(
            question_id=question.id,
            skill_id=skill.id,
        )
    )

    quiz_session = QuizSession(user_id=user_id)
    db.add(quiz_session)
    db.flush()

    quiz_item = QuizItem(
        quiz_session_id=quiz_session.id,
        question_id=question.id,
        position=1,
        question_snapshot={
            "content": f"Test question {question_number}",
        },
        answer_key_snapshot="A",
    )
    db.add(quiz_item)
    db.flush()

    db.add(
        Attempt(
            user_id=user_id,
            quiz_item_id=quiz_item.id,
            attempt_number=1,
            selected_option_key="A" if correct else "B",
            is_correct=correct,
            is_retry=False,
        )
    )

    db.flush()


def test_registry_contains_initial_tools() -> None:
    names = {
        definition.name
        for definition in TUTOR_TOOL_REGISTRY.get_all()
    }

    assert names == {
        "get_student_profile",
        "get_weak_skills",
    }


def test_get_student_profile_returns_learning_preferences(
    db: Session,
) -> None:
    user = create_user(db, "student@example.test")

    db.add(
        StudentProfile(
            user_id=user.id,
            target_score=750,
            timezone="Asia/Ho_Chi_Minh",
        )
    )
    db.commit()

    result = TUTOR_TOOL_REGISTRY.execute(
        name="get_student_profile",
        arguments={},
        db=db,
        student_id=user.id,
    )

    assert result == {
        "profile_found": True,
        "target_score": 750,
        "timezone": "Asia/Ho_Chi_Minh",
    }

    assert "email" not in result
    assert "password_hash" not in result


def test_get_student_profile_handles_missing_profile(
    db: Session,
) -> None:
    user = create_user(db, "student@example.test")
    db.commit()

    result = TUTOR_TOOL_REGISTRY.execute(
        name="get_student_profile",
        arguments={},
        db=db,
        student_id=user.id,
    )

    assert result["profile_found"] is False
    assert result["target_score"] is None


def test_get_weak_skills_ranks_high_error_rate_first(
    db: Session,
) -> None:
    user = create_user(db, "student@example.test")

    grammar = Skill(
        code="GRAMMAR_TEST",
        name="Grammar test",
        category="grammar",
    )

    vocabulary = Skill(
        code="VOCAB_TEST",
        name="Vocabulary test",
        category="vocabulary",
    )

    db.add_all([grammar, vocabulary])
    db.flush()

    # Grammar: 2 incorrect out of 2 attempts.
    create_question(db, user.id, grammar, 1, False)
    create_question(db, user.id, grammar, 2, False)

    # Vocabulary: 1 incorrect out of 2 attempts.
    create_question(db, user.id, vocabulary, 3, False)
    create_question(db, user.id, vocabulary, 4, True)

    db.commit()

    result = TUTOR_TOOL_REGISTRY.execute(
        name="get_weak_skills",
        arguments={"limit": 5},
        db=db,
        student_id=user.id,
    )

    skills = result["weak_skills"]

    assert len(skills) == 2

    assert skills[0]["skill_code"] == "GRAMMAR_TEST"
    assert skills[0]["attempt_count"] == 2
    assert skills[0]["incorrect_count"] == 2
    assert skills[0]["accuracy_percent"] == 0.0

    assert skills[1]["skill_code"] == "VOCAB_TEST"
    assert skills[1]["accuracy_percent"] == 50.0



def test_get_weak_skills_ignores_retry_attempts(
    db: Session,
) -> None:
    user = create_user(db, "student@example.test")

    skill = Skill(
        code="RETRY_TEST",
        name="Retry test",
        category="grammar",
    )
    db.add(skill)
    db.flush()

    create_question(db, user.id, skill, 10, False)
    create_question(db, user.id, skill, 11, False)

    # Get the first quiz item using the actual question ID.
    first_question = (
        db.query(Question)
        .filter(Question.content == "Test question 10")
        .one()
    )

    first_item = (
        db.query(QuizItem)
        .filter(QuizItem.question_id == first_question.id)
        .one()
    )

    # Add a retry that is correct.
    db.add(
        Attempt(
            user_id=user.id,
            quiz_item_id=first_item.id,
            attempt_number=2,
            selected_option_key="A",
            is_correct=True,
            is_retry=True,
        )
    )

    db.commit()

    result = TUTOR_TOOL_REGISTRY.execute(
        name="get_weak_skills",
        arguments={},
        db=db,
        student_id=user.id,
    )

    skill_result = result["weak_skills"][0]

    assert skill_result["attempt_count"] == 2
    assert skill_result["incorrect_count"] == 2
    assert skill_result["accuracy_percent"] == 0.0


def test_get_weak_skills_does_not_read_another_student(
    db: Session,
) -> None:
    student_one = create_user(db, "one@example.test")
    student_two = create_user(db, "two@example.test")

    skill = Skill(
        code="PRIVATE_TEST",
        name="Private test",
        category="grammar",
    )
    db.add(skill)
    db.flush()

    create_question(db, student_one.id, skill, 20, False)
    create_question(db, student_one.id, skill, 21, False)

    db.commit()

    result = TUTOR_TOOL_REGISTRY.execute(
        name="get_weak_skills",
        arguments={},
        db=db,
        student_id=student_two.id,
    )

    assert result["has_data"] is False
    assert result["weak_skills"] == []


def test_get_weak_skills_requires_two_first_attempts(
    db: Session,
) -> None:
    user = create_user(db, "student@example.test")

    skill = Skill(
        code="LOW_DATA",
        name="Low data skill",
        category="grammar",
    )
    db.add(skill)
    db.flush()

    create_question(db, user.id, skill, 30, False)
    db.commit()

    result = TUTOR_TOOL_REGISTRY.execute(
        name="get_weak_skills",
        arguments={},
        db=db,
        student_id=user.id,
    )

    assert result["has_data"] is False
    assert result["weak_skills"] == []


@pytest.mark.parametrize(
    "arguments",
    [
        {"limit": 0},
        {"limit": 11},
        {"limit": True},
        {"unexpected": "value"},
    ],
)
def test_get_weak_skills_rejects_invalid_arguments(
    db: Session,
    arguments: dict,
) -> None:
    user = create_user(db, "student@example.test")

    with pytest.raises(ToolInputError):
        TUTOR_TOOL_REGISTRY.execute(
            name="get_weak_skills",
            arguments=arguments,
            db=db,
            student_id=user.id,
        )


def test_profile_tool_rejects_unexpected_student_id(
    db: Session,
) -> None:
    user = create_user(db, "student@example.test")

    with pytest.raises(ToolInputError):
        TUTOR_TOOL_REGISTRY.execute(
            name="get_student_profile",
            arguments={"student_id": user.id},
            db=db,
            student_id=user.id,
        )


def test_registry_rejects_unknown_tool(
    db: Session,
) -> None:
    user = create_user(db, "student@example.test")

    with pytest.raises(UnknownToolError):
        TUTOR_TOOL_REGISTRY.execute(
            name="delete_all_data",
            arguments={},
            db=db,
            student_id=user.id,
        )


def test_registry_rejects_invalid_student_id(
    db: Session,
) -> None:
    with pytest.raises(ToolInputError):
        TUTOR_TOOL_REGISTRY.execute(
            name="get_student_profile",
            arguments={},
            db=db,
            student_id=True,
        )


def test_registry_rejects_duplicate_tool_names() -> None:
    registry = ToolRegistry()

    definition = ToolDefinition(
        name="sample_tool",
        description="A test tool.",
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        handler=lambda db, student_id, arguments: {},
    )

    registry.register(definition)

    with pytest.raises(ValueError):
        registry.register(definition)
