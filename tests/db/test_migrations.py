"""Tests for Alembic migrations on an isolated SQLite database."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from backend.app.db.session import make_engine


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG_PATH = PROJECT_ROOT / "alembic.ini"


@pytest.fixture
def migrated_db(
    tmp_path: Path,
) -> Iterator[Connection]:
    """Upgrade a temporary SQLite database using Alembic."""

    db_path = tmp_path / "migration_test.sqlite3"

    database_url = (
        f"sqlite+pysqlite:///{db_path.as_posix()}"
    )

    test_engine = make_engine(database_url)

    alembic_config = Config(
        str(ALEMBIC_CONFIG_PATH)
    )

    try:
        with test_engine.begin() as connection:
            # Inject the temporary connection into Alembic.
            # The application database is not used.
            alembic_config.attributes["connection"] = connection

            command.upgrade(
                alembic_config,
                "head",
            )

            yield connection
    finally:
        test_engine.dispose()


def test_migration_creates_core_tables(
    migrated_db: Connection,
) -> None:
    """Verify Core, Quiz, and Alembic tables after migrations."""

    inspector = inspect(migrated_db)

    expected_tables = {
        # Core tables
        "users",
        "student_profiles",
        "skills",
        "questions",
        "question_options",
        "question_skills",

        # Quiz tables
        "quiz_sessions",
        "quiz_items",
        "attempts",

        # Alembic version table
        "alembic_version",
    }

    actual_tables = set(inspector.get_table_names())

    assert actual_tables == expected_tables


def test_migration_version_matches_head(
    migrated_db: Connection,
) -> None:
    """Verify that the temporary database is at Alembic head."""

    alembic_config = Config(
        str(ALEMBIC_CONFIG_PATH)
    )

    script = ScriptDirectory.from_config(
        alembic_config
    )

    heads = script.get_heads()

    assert len(heads) == 1

    database_revision = migrated_db.execute(
        text(
            "SELECT version_num "
            "FROM alembic_version"
        )
    ).scalar_one()

    assert database_revision == heads[0]


def test_migration_enforces_foreign_keys(
    migrated_db: Connection,
) -> None:
    """Verify real foreign-key enforcement after migration."""

    foreign_keys_enabled = migrated_db.exec_driver_sql(
        "PRAGMA foreign_keys"
    ).scalar_one()

    assert foreign_keys_enabled == 1

    inspector = inspect(migrated_db)

    option_foreign_keys = inspector.get_foreign_keys(
        "question_options"
    )

    assert any(
        fk["referred_table"] == "questions"
        for fk in option_foreign_keys
    )

    # Question 999999 does not exist.
    # SQLite must reject the orphan option.
    with pytest.raises(IntegrityError):
        migrated_db.execute(
            text(
                "INSERT INTO question_options "
                "(question_id, option_key, content) "
                "VALUES (999999, 'A', 'Invalid option')"
            )
        )