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
        # AI Tutor Chat tables
        "chat_sessions",
        "chat_messages",
        # Global RAG document tables
        "documents",
        "document_chunks",
        # Study Planner tables
        "study_plans",
        "study_plan_tasks",
    }
    
    actual_tables = set(inspector.get_table_names())
    chunk_columns = {
        column["name"]
        for column in inspector.get_columns("document_chunks")
    }

    assert "page_number" in chunk_columns
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


def test_document_ownership_migration_preserves_existing_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify ownership migration preserves existing documents and chunks."""

    db_path = tmp_path / "document_ownership_migration.sqlite3"

    database_url = (
        f"sqlite+pysqlite:///{db_path.as_posix()}"
    )

    test_engine = make_engine(database_url)

    try:
        # Step 1: Create the database at the previous migration revision.
        with test_engine.connect() as connection:
            alembic_config = Config(
                str(ALEMBIC_CONFIG_PATH)
            )
            alembic_config.attributes["connection"] = connection

            command.upgrade(
                alembic_config,
                "e2f7a6c91d34",
            )
            connection.commit()

        # Step 2: Insert legacy data before the ownership migration.
        legacy_hash = "a" * 64
        legacy_chunk_hash = "b" * 64

        with test_engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO users (
                        id,
                        email,
                        password_hash
                    )
                    VALUES (
                        1001,
                        'personal-rag-test@example.com',
                        'test-password-hash'
                    )
                    """
                )
            )

            connection.execute(
                text(
                    """
                    INSERT INTO documents (
                        id,
                        title,
                        original_filename,
                        document_type,
                        storage_path,
                        content_hash,
                        usage_permission_status,
                        processing_status
                    )
                    VALUES (
                        2001,
                        'Legacy TOEIC document',
                        'legacy-toeic.pdf',
                        'pdf',
                        'documents/legacy-toeic.pdf',
                        :content_hash,
                        'granted',
                        'indexed'
                    )
                    """
                ),
                {"content_hash": legacy_hash},
            )

            connection.execute(
                text(
                    """
                    INSERT INTO document_chunks (
                        id,
                        document_id,
                        chunk_index,
                        content,
                        content_hash,
                        token_count,
                        vector_id
                    )
                    VALUES (
                        3001,
                        2001,
                        0,
                        'Legacy TOEIC reading content',
                        :chunk_hash,
                        12,
                        'legacy-vector-3001'
                    )
                    """
                ),
                {"chunk_hash": legacy_chunk_hash},
            )

        # Step 3: Enable the SQLite FK protection mechanism.
        monkeypatch.setenv(
            "ALEMBIC_SQLITE_FK_OFF",
            "1",
        )

        # Upgrade using a fresh connection without an outer transaction.
        with test_engine.connect() as connection:
            alembic_config = Config(
                str(ALEMBIC_CONFIG_PATH)
            )
            alembic_config.attributes["connection"] = connection

            command.upgrade(
                alembic_config,
                "f1a9c3d7e205",
            )
            connection.commit()

            # Step 4: Verify foreign keys are enabled again.
            fk_status = connection.exec_driver_sql(
                "PRAGMA foreign_keys"
            ).scalar_one()

            assert fk_status == 1

            violations = connection.exec_driver_sql(
                "PRAGMA foreign_key_check"
            ).fetchall()

            assert violations == []

            # Step 5: Verify the old document was preserved.
            document = connection.execute(
                text(
                    """
                    SELECT
                        id,
                        title,
                        content_hash,
                        owner_user_id,
                        processing_status
                    FROM documents
                    WHERE id = 2001
                    """
                )
            ).mappings().one()

            assert document["title"] == "Legacy TOEIC document"
            assert document["content_hash"] == legacy_hash
            assert document["owner_user_id"] is None
            assert document["processing_status"] == "indexed"

            # Step 6: Verify the old chunk was preserved.
            chunk = connection.execute(
                text(
                    """
                    SELECT
                        id,
                        document_id,
                        content,
                        content_hash,
                        vector_id
                    FROM document_chunks
                    WHERE id = 3001
                    """
                )
            ).mappings().one()

            assert chunk["document_id"] == 2001
            assert chunk["content"] == "Legacy TOEIC reading content"
            assert chunk["content_hash"] == legacy_chunk_hash
            assert chunk["vector_id"] == "legacy-vector-3001"

            # Step 7: Verify document foreign keys.
            inspector = inspect(connection)

            document_foreign_keys = inspector.get_foreign_keys(
                "documents"
            )

            assert any(
                fk["referred_table"] == "users"
                and fk["constrained_columns"] == ["owner_user_id"]
                for fk in document_foreign_keys
            )

            chunk_foreign_keys = inspector.get_foreign_keys(
                "document_chunks"
            )

            assert any(
                fk["referred_table"] == "documents"
                and fk["constrained_columns"] == ["document_id"]
                for fk in chunk_foreign_keys
            )

        # Step 8: Verify global and personal uniqueness rules.
        with test_engine.begin() as connection:
            # Two different users can own documents with the same hash.
            # Personal documents can also share a hash with a global one.
            connection.execute(
                text(
                    """
                    INSERT INTO documents (
                        title,
                        original_filename,
                        document_type,
                        storage_path,
                        content_hash,
                        owner_user_id
                    )
                    VALUES (
                        'Personal document user 1',
                        'personal-1.pdf',
                        'pdf',
                        'documents/personal-1.pdf',
                        :content_hash,
                        1001
                    )
                    """
                ),
                {"content_hash": legacy_hash},
            )

            connection.execute(
                text(
                    """
                    INSERT INTO users (
                        id,
                        email,
                        password_hash
                    )
                    VALUES (
                        1002,
                        'personal-rag-test-2@example.com',
                        'test-password-hash'
                    )
                    """
                )
            )

            connection.execute(
                text(
                    """
                    INSERT INTO documents (
                        title,
                        original_filename,
                        document_type,
                        storage_path,
                        content_hash,
                        owner_user_id
                    )
                    VALUES (
                        'Personal document user 2',
                        'personal-2.pdf',
                        'pdf',
                        'documents/personal-2.pdf',
                        :content_hash,
                        1002
                    )
                    """
                ),
                {"content_hash": legacy_hash},
            )

            # Same owner + same hash must be rejected.
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(
                        text(
                            """
                            INSERT INTO documents (
                                title,
                                original_filename,
                                document_type,
                                storage_path,
                                content_hash,
                                owner_user_id
                            )
                            VALUES (
                                'Duplicate personal document',
                                'duplicate.pdf',
                                'pdf',
                                'documents/duplicate.pdf',
                                :content_hash,
                                1001
                            )
                            """
                        ),
                        {"content_hash": legacy_hash},
                    )

            # Two global documents with the same hash must be rejected.
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(
                        text(
                            """
                            INSERT INTO documents (
                                title,
                                original_filename,
                                document_type,
                                storage_path,
                                content_hash
                            )
                            VALUES (
                                'Duplicate global document',
                                'duplicate-global.pdf',
                                'pdf',
                                'documents/duplicate-global.pdf',
                                :content_hash
                            )
                            """
                        ),
                        {"content_hash": legacy_hash},
                    )

    finally:
        test_engine.dispose()

def test_study_plan_migration_creates_expected_schema(
    migrated_db: Connection,
) -> None:
    """Verify Study Plan tables, columns, indexes, and foreign keys."""

    inspector = inspect(migrated_db)

    plan_columns = {
        column["name"]
        for column in inspector.get_columns("study_plans")
    }

    assert {
        "id",
        "user_id",
        "title",
        "target_score",
        "start_date",
        "end_date",
        "daily_minutes",
        "status",
        "created_at",
        "updated_at",
    }.issubset(plan_columns)

    task_columns = {
        column["name"]
        for column in inspector.get_columns("study_plan_tasks")
    }

    assert {
        "id",
        "study_plan_id",
        "skill_id",
        "task_type",
        "scheduled_date",
        "estimated_minutes",
        "target_question_count",
        "status",
        "completed_at",
    }.issubset(task_columns)

    plan_indexes = {
        index["name"]: index
        for index in inspector.get_indexes("study_plans")
    }

    assert "ix_study_plans_user_status" in plan_indexes
    assert "uq_study_plans_one_active_per_user" in plan_indexes

    active_index = plan_indexes[
    "uq_study_plans_one_active_per_user"
    ]

    assert bool(active_index["unique"]) is True
    assert active_index["column_names"] == ["user_id"]

    task_indexes = {
        index["name"]
        for index in inspector.get_indexes("study_plan_tasks")
    }

    assert "ix_study_plan_tasks_plan_date_status" in task_indexes
    assert "ix_study_plan_tasks_skill_id" in task_indexes

    plan_foreign_keys = inspector.get_foreign_keys(
        "study_plans"
    )

    assert any(
        fk["referred_table"] == "users"
        and fk["constrained_columns"] == ["user_id"]
        for fk in plan_foreign_keys
    )

    task_foreign_keys = inspector.get_foreign_keys(
        "study_plan_tasks"
    )

    assert any(
        fk["referred_table"] == "study_plans"
        and fk["constrained_columns"] == ["study_plan_id"]
        for fk in task_foreign_keys
    )

    assert any(
        fk["referred_table"] == "skills"
        and fk["constrained_columns"] == ["skill_id"]
        for fk in task_foreign_keys
    )

def test_study_plan_allows_only_one_active_plan_per_user(
    migrated_db: Connection,
) -> None:
    """A user cannot have two active study plans."""

    migrated_db.execute(
        text(
            """
            INSERT INTO users (
                id,
                email,
                password_hash
            )
            VALUES (
                9001,
                'study-plan-test@example.com',
                'test-password-hash'
            )
            """
        )
    )

    migrated_db.execute(
        text(
            """
            INSERT INTO study_plans (
                user_id,
                title,
                target_score,
                start_date,
                end_date,
                daily_minutes,
                status
            )
            VALUES (
                9001,
                'First plan',
                750,
                '2026-11-10',
                '2026-12-10',
                60,
                'active'
            )
            """
        )
    )

    # A second active plan for the same user must fail.
    with pytest.raises(IntegrityError):
        with migrated_db.begin_nested():
            migrated_db.execute(
                text(
                    """
                    INSERT INTO study_plans (
                        user_id,
                        title,
                        target_score,
                        start_date,
                        end_date,
                        daily_minutes,
                        status
                    )
                    VALUES (
                        9001,
                        'Second active plan',
                        850,
                        '2026-11-10',
                        '2026-12-20',
                        90,
                        'active'
                    )
                    """
                )
            )

    # A historical completed plan must still be allowed.
    migrated_db.execute(
        text(
            """
            INSERT INTO study_plans (
                user_id,
                title,
                target_score,
                start_date,
                end_date,
                daily_minutes,
                status
            )
            VALUES (
                9001,
                'Completed plan',
                650,
                '2026-10-01',
                '2026-11-01',
                45,
                'completed'
            )
            """
        )
    )

    # Changing the first plan to paused allows a new active plan.
    migrated_db.execute(
        text(
            """
            UPDATE study_plans
            SET status = 'paused'
            WHERE user_id = 9001
              AND title = 'First plan'
            """
        )
    )

    migrated_db.execute(
        text(
            """
            INSERT INTO study_plans (
                user_id,
                title,
                target_score,
                start_date,
                end_date,
                daily_minutes,
                status
            )
            VALUES (
                9001,
                'Replacement active plan',
                800,
                '2026-11-10',
                '2026-12-20',
                60,
                'active'
            )
            """
        )
    )