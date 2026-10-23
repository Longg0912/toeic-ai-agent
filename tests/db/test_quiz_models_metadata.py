"""Metadata tests for the TOEIC Quiz ORM models."""

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import configure_mappers

from backend.app.db.base import Base
from backend.app.db.models import (
    Attempt,
    QuizItem,
    QuizSession,
)


def test_quiz_tables_registered() -> None:
    """All three Quiz tables must be registered."""

    expected = {
        "quiz_sessions",
        "quiz_items",
        "attempts",
    }

    actual = set(Base.metadata.tables.keys())

    assert expected.issubset(actual)


def test_quiz_relationships_configured() -> None:
    """SQLAlchemy must configure all ORM relationships."""

    configure_mappers()

    assert QuizSession.__tablename__ == "quiz_sessions"
    assert QuizItem.__tablename__ == "quiz_items"
    assert Attempt.__tablename__ == "attempts"


def test_quiz_foreign_keys() -> None:
    """Foreign keys must reference the expected parent tables."""

    expected = {
        "quiz_sessions.user_id": "users.id",
        "quiz_items.quiz_session_id": "quiz_sessions.id",
        "quiz_items.question_id": "questions.id",
        "attempts.user_id": "users.id",
        "attempts.quiz_item_id": "quiz_items.id",
    }

    for source, destination in expected.items():
        table_name, column_name = source.split(".")

        column = Base.metadata.tables[table_name].c[column_name]

        targets = {
            fk.target_fullname
            for fk in column.foreign_keys
        }

        assert destination in targets


def test_quiz_unique_constraints() -> None:
    """Prevent duplicate positions, questions, and attempt numbers."""

    expected = {
        "quiz_items": {
            ("quiz_session_id", "position"),
            ("quiz_session_id", "question_id"),
        },
        "attempts": {
            ("quiz_item_id", "attempt_number"),
        },
    }

    for table_name, required_constraints in expected.items():
        table = Base.metadata.tables[table_name]

        actual_constraints = {
            tuple(column.name for column in constraint.columns)
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }

        assert required_constraints.issubset(actual_constraints)