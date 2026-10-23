"""Integration tests for Quiz database constraints."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from backend.app.db.session import make_engine


PROJECT_ROOT = Path(__file__).resolve().parents[2]

ALEMBIC_CONFIG = PROJECT_ROOT / "alembic.ini"


@pytest.fixture
def quiz_db(tmp_path: Path) -> Iterator[Engine]:
    """Create and migrate an isolated SQLite test database."""

    db_path = tmp_path / "quiz_constraints.sqlite3"

    database_url = (
        f"sqlite+pysqlite:///{db_path.as_posix()}"
    )

    engine = make_engine(database_url)

    config = Config(str(ALEMBIC_CONFIG))

    try:
        # Apply real Alembic migrations to a temporary DB.
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        # Insert minimal test data.
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(id, email, password_hash) "
                    "VALUES (1, 'student@example.test', 'test-only-hash')"
                )
            )

            connection.execute(
                text(
                    "INSERT INTO questions "
                    "(id, part, content, correct_option_key, content_hash) "
                    "VALUES "
                    "(1, 5, 'Question one', 'B', :hash_one), "
                    "(2, 5, 'Question two', 'A', :hash_two)"
                ),
                {
                    "hash_one": "a" * 64,
                    "hash_two": "b" * 64,
                },
            )

            connection.execute(
                text(
                    "INSERT INTO quiz_sessions "
                    "(id, user_id) VALUES (1, 1)"
                )
            )

            snapshot = json.dumps(
                {
                    "part": 5,
                    "content": "Question one",
                    "options": [
                        {"key": "A", "content": "Option A"},
                        {"key": "B", "content": "Option B"},
                        {"key": "C", "content": "Option C"},
                        {"key": "D", "content": "Option D"},
                    ],
                }
            )

            connection.execute(
                text(
                    "INSERT INTO quiz_items "
                    "(id, quiz_session_id, question_id, "
                    "position, question_snapshot, answer_key_snapshot) "
                    "VALUES (1, 1, 1, 1, :snapshot, 'B')"
                ),
                {"snapshot": snapshot},
            )

        yield engine

    finally:
        engine.dispose()


def assert_integrity_error(
    engine: Engine,
    sql: str,
    parameters: dict[str, Any] | None = None,
) -> None:
    """Assert that SQLite rejects an invalid operation."""

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(sql),
                parameters or {},
            )


def test_quiz_tables_and_foreign_keys(
    quiz_db: Engine,
) -> None:
    """Verify Quiz tables and enabled foreign keys."""

    inspector = inspect(quiz_db)

    actual_tables = set(inspector.get_table_names())

    assert {
        "quiz_sessions",
        "quiz_items",
        "attempts",
    }.issubset(actual_tables)

    with quiz_db.connect() as connection:
        assert (
            connection.exec_driver_sql(
                "PRAGMA foreign_keys"
            ).scalar_one()
            == 1
        )

    attempt_fks = inspector.get_foreign_keys("attempts")

    assert any(
        fk["referred_table"] == "quiz_items"
        for fk in attempt_fks
    )


@pytest.mark.parametrize(
    "question_id, position",
    [
        (2, 1),  # Duplicate position
        (1, 2),  # Duplicate question
    ],
)
def test_duplicate_quiz_items_rejected(
    quiz_db: Engine,
    question_id: int,
    position: int,
) -> None:
    """Reject duplicate question or position within one quiz."""

    assert_integrity_error(
        quiz_db,
        (
            "INSERT INTO quiz_items "
            "(quiz_session_id, question_id, position, "
            "question_snapshot, answer_key_snapshot) "
            "VALUES (1, :question_id, :position, :snapshot, :answer)"
        ),
        {
            "question_id": question_id,
            "position": position,
            "snapshot": json.dumps({"content": "Test"}),
            "answer": "A" if question_id == 2 else "B",
        },
    )


def test_duplicate_attempt_number_rejected(
    quiz_db: Engine,
) -> None:
    """Reject duplicate attempt numbers for the same quiz item."""

    insert_sql = (
        "INSERT INTO attempts "
        "(user_id, quiz_item_id, attempt_number, "
        "selected_option_key, is_correct) "
        "VALUES (1, 1, 1, 'B', 1)"
    )

    with quiz_db.begin() as connection:
        connection.execute(text(insert_sql))

    assert_integrity_error(
        quiz_db,
        insert_sql,
    )


def test_invalid_quiz_answer_key_rejected(
    quiz_db: Engine,
) -> None:
    """Snapshot answer keys must be A, B, C, or D."""

    assert_integrity_error(
        quiz_db,
        (
            "INSERT INTO quiz_items "
            "(quiz_session_id, question_id, position, "
            "question_snapshot, answer_key_snapshot) "
            "VALUES (1, 2, 2, :snapshot, 'E')"
        ),
        {
            "snapshot": json.dumps({"content": "Question two"}),
        },
    )


@pytest.mark.parametrize(
    "selected, number, seconds",
    [
        ("E", 1, 10),  # Invalid option
        ("A", 0, 10),  # Invalid attempt number
        ("A", 1, -1),  # Negative time
    ],
)
def test_invalid_attempt_values_rejected(
    quiz_db: Engine,
    selected: str,
    number: int,
    seconds: int,
) -> None:
    """Reject attempts violating CHECK constraints."""

    assert_integrity_error(
        quiz_db,
        (
            "INSERT INTO attempts "
            "(user_id, quiz_item_id, attempt_number, "
            "selected_option_key, is_correct, time_spent_seconds) "
            "VALUES (1, 1, :number, :selected, 0, :seconds)"
        ),
        {
            "number": number,
            "selected": selected,
            "seconds": seconds,
        },
    )


def test_attempt_invalid_foreign_key_rejected(
    quiz_db: Engine,
) -> None:
    """An attempt cannot refer to a nonexistent quiz item."""

    assert_integrity_error(
        quiz_db,
        (
            "INSERT INTO attempts "
            "(user_id, quiz_item_id, attempt_number, "
            "selected_option_key, is_correct) "
            "VALUES (1, 999999, 1, 'A', 0)"
        ),
    )