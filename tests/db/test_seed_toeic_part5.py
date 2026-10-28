"""Tests for idempotent TOEIC Part 5 seed data."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from backend.app.db.models import (
    Attempt,
    Question,
    QuestionOption,
    QuestionSkill,
    QuizSession,
    Skill,
    User,
)
from backend.app.db.session import make_engine

from scripts.seed_toeic_part5 import (
    QUESTIONS,
    SEED_REFERENCE_PREFIX,
    SEED_SOURCE_NAME,
    calculate_content_hash,
    seed_demo_data,
)
from scripts.update_seed_explanations_vi import (
    LEGACY_EXPLANATIONS,
    update_seed_explanations_vi,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

ALEMBIC_CONFIG = PROJECT_ROOT / "alembic.ini"


@pytest.fixture
def seed_engine(tmp_path: Path) -> Iterator[Engine]:
    """Create a temporary SQLite database with Alembic migrations."""

    database_path = tmp_path / "seed_test.sqlite3"

    database_url = (
        f"sqlite+pysqlite:///{database_path.as_posix()}"
    )

    test_engine = make_engine(database_url)

    config = Config(str(ALEMBIC_CONFIG))

    try:
        with test_engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        yield test_engine

    finally:
        test_engine.dispose()


def table_counts(db_engine: Engine) -> dict[str, int]:
    """Return database row counts for relevant tables."""

    tables = {
        "skills": Skill,
        "questions": Question,
        "question_options": QuestionOption,
        "question_skills": QuestionSkill,
        "users": User,
        "quiz_sessions": QuizSession,
        "attempts": Attempt,
    }

    with Session(db_engine) as session:
        return {
            name: session.execute(
                select(func.count()).select_from(model)
            ).scalar_one()
            for name, model in tables.items()
        }


def test_seed_creates_expected_draft_data(
    seed_engine: Engine,
) -> None:
    """Verify all demonstration questions and skills are inserted."""

    result = seed_demo_data(seed_engine)

    assert result.created_skills == 5
    assert result.existing_skills == 0
    assert result.created_questions == 6
    assert result.existing_questions == 0

    counts = table_counts(seed_engine)

    assert counts["skills"] == 17
    assert counts["questions"] == 6
    assert counts["question_options"] == 24
    assert counts["question_skills"] == 7

    # Authentication data and student activity are not seeded.
    assert counts["users"] == 0
    assert counts["quiz_sessions"] == 0
    assert counts["attempts"] == 0

    with Session(seed_engine) as session:
        questions = session.scalars(
            select(Question)
        ).all()

        for question in questions:
            assert question.part == 5
            assert question.review_status == "draft"
            assert question.source_type == "ai_generated"
            assert question.source_name == SEED_SOURCE_NAME
            assert question.owner_user_id is None

            option_keys = {
                option.option_key
                for option in question.options
            }

            assert option_keys == {"A", "B", "C", "D"}

            assert question.correct_option_key in option_keys
            assert question.explanation is not None
            assert question.explanation.strip()

            key = question.source_reference.removeprefix(
                SEED_REFERENCE_PREFIX
            )
            definition = next(
                item for item in QUESTIONS if item.key == key
            )
            assert question.explanation == definition.explanation


def test_seed_is_idempotent(
    seed_engine: Engine,
) -> None:
    """Running the seed twice must not add duplicate rows."""

    first = seed_demo_data(seed_engine)

    counts_after_first = table_counts(seed_engine)

    second = seed_demo_data(seed_engine)

    counts_after_second = table_counts(seed_engine)

    assert first.created_skills == 5
    assert first.created_questions == 6

    assert second.created_skills == 0
    assert second.created_questions == 0

    assert second.existing_skills == 5
    assert second.existing_questions == 6

    assert counts_after_first == counts_after_second


def test_seed_does_not_overwrite_existing_explanation(
    seed_engine: Engine,
) -> None:
    """A repeated seed run must preserve a manually edited explanation."""

    seed_demo_data(seed_engine)
    custom_explanation = "Lời giải đã được biên tập thủ công."

    with Session(seed_engine) as session:
        question = session.scalar(
            select(Question).where(
                Question.source_reference
                == f"{SEED_REFERENCE_PREFIX}Q006"
            )
        )
        assert question is not None
        question.explanation = custom_explanation
        session.commit()

    seed_demo_data(seed_engine)

    with Session(seed_engine) as session:
        question = session.scalar(
            select(Question).where(
                Question.source_reference
                == f"{SEED_REFERENCE_PREFIX}Q006"
            )
        )
        assert question is not None
        assert question.explanation == custom_explanation


def test_backfill_updates_empty_and_known_legacy_explanations(
    seed_engine: Engine,
) -> None:
    """Backfill empty explanations and the known English Q006 explanation."""

    seed_demo_data(seed_engine)

    with Session(seed_engine) as session:
        questions = session.scalars(select(Question)).all()
        for question in questions:
            question.explanation = None

        q006 = session.scalar(
            select(Question).where(
                Question.source_reference
                == f"{SEED_REFERENCE_PREFIX}Q006"
            )
        )
        assert q006 is not None
        q006.explanation = LEGACY_EXPLANATIONS["Q006"]
        session.commit()

    result = update_seed_explanations_vi(seed_engine)

    assert result.updated == 6
    assert result.already_current == 0
    assert result.preserved_custom == 0

    with Session(seed_engine) as session:
        questions = session.scalars(select(Question)).all()
        for question in questions:
            key = question.source_reference.removeprefix(
                SEED_REFERENCE_PREFIX
            )
            definition = next(
                item for item in QUESTIONS if item.key == key
            )
            assert question.explanation == definition.explanation


def test_backfill_preserves_custom_explanation(
    seed_engine: Engine,
) -> None:
    """Backfill must not replace non-empty explanations outside its allowlist."""

    seed_demo_data(seed_engine)

    custom_explanation = "Lời giải riêng do người dùng chỉnh sửa."

    with Session(seed_engine) as session:
        questions = session.scalars(select(Question)).all()
        for question in questions:
            question.explanation = None

        q001 = session.scalar(
            select(Question).where(
                Question.source_reference
                == f"{SEED_REFERENCE_PREFIX}Q001"
            )
        )
        q006 = session.scalar(
            select(Question).where(
                Question.source_reference
                == f"{SEED_REFERENCE_PREFIX}Q006"
            )
        )
        assert q001 is not None
        assert q006 is not None

        q001.explanation = custom_explanation
        q006.explanation = LEGACY_EXPLANATIONS["Q006"]
        session.commit()

    result = update_seed_explanations_vi(seed_engine)

    assert result.updated == 5
    assert result.already_current == 0
    assert result.preserved_custom == 1

    with Session(seed_engine) as session:
        q001 = session.scalar(
            select(Question).where(
                Question.source_reference
                == f"{SEED_REFERENCE_PREFIX}Q001"
            )
        )
        assert q001 is not None
        assert q001.explanation == custom_explanation


def test_seed_does_not_overwrite_modified_question(
    seed_engine: Engine,
) -> None:
    """Reject changes to an existing seed question."""

    seed_demo_data(seed_engine)

    with Session(seed_engine) as session:
        question = session.scalar(
            select(Question).where(
                Question.source_reference
                == "seed:toeic-part5:v1:Q001"
            )
        )

        assert question is not None

        # Simulate a manual modification.
        question.correct_option_key = "A"

        session.commit()

    counts_before = table_counts(seed_engine)

    with pytest.raises(
        ValueError,
        match="differs from its definition",
    ):
        seed_demo_data(seed_engine)

    counts_after = table_counts(seed_engine)

    assert counts_before == counts_after

    with Session(seed_engine) as session:
        question = session.scalar(
            select(Question).where(
                Question.source_reference
                == "seed:toeic-part5:v1:Q001"
            )
        )

        assert question is not None

        # The seed did not silently overwrite the record.
        assert question.correct_option_key == "A"


def test_seed_rolls_back_if_content_already_exists(
    seed_engine: Engine,
) -> None:
    """A conflicting question must roll back newly inserted skills."""

    first_question = QUESTIONS[0]

    with Session(seed_engine) as session:
        existing_question = Question(
            part=5,
            content=first_question.content,
            correct_option_key="B",
            content_hash=calculate_content_hash(
                first_question.content
            ),
            review_status="draft",
            source_type="original",
            visibility="public",
        )

        session.add(existing_question)
        session.commit()

    with pytest.raises(
        ValueError,
        match="already exists outside this seed",
    ):
        seed_demo_data(seed_engine)

    counts = table_counts(seed_engine)

    # The conflicting question remains.
    assert counts["questions"] == 1

    # Skills inserted before the conflict were rolled back.
    assert counts["skills"] == 12

    assert counts["question_options"] == 0
    assert counts["question_skills"] == 0