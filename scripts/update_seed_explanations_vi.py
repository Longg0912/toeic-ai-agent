"""Safely backfill Vietnamese explanations for the synthetic Part 5 seed.

This script only changes Question.explanation. It never changes review status,
usage permission, visibility, question text, options, answer keys, or attempts.

Run from the project root:
    python -m scripts.update_seed_explanations_vi
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from backend.app.db.models import Question
from backend.app.db.session import engine as application_engine
from scripts.seed_toeic_part5 import (
    QUESTIONS,
    QuestionSeed,
    SEED_REFERENCE_PREFIX,
    check_database_revision,
    validate_existing_question,
    validate_seed_definitions,
)


# Exact English explanation added to Q006 during the initial UI test.
# Only this known legacy value is eligible for replacement. Other non-empty
# explanations are treated as user edits and are preserved.
LEGACY_EXPLANATIONS: dict[str, str] = {
    "Q006": (
        "Use 'since' with a specific starting point such as 2021. "
        "The present perfect 'has worked' describes work that began "
        "in the past and continues to the present."
    ),
}


@dataclass
class ExplanationUpdateResult:
    """Counts for the explanation-only backfill."""

    updated: int = 0
    already_current: int = 0
    preserved_custom: int = 0


def update_seed_explanations_vi(db_engine: Engine) -> ExplanationUpdateResult:
    """Update missing/known legacy explanations without overwriting custom text."""

    validate_seed_definitions()

    if db_engine.url.get_backend_name() != "sqlite":
        raise ValueError("Explanation backfill supports SQLite only.")

    result = ExplanationUpdateResult()

    with Session(db_engine) as session:
        with session.begin():
            check_database_revision(session)

            # Validate every expected seed record before changing any row.
            records: list[tuple[QuestionSeed, Question]] = []

            for definition in QUESTIONS:
                reference = f"{SEED_REFERENCE_PREFIX}{definition.key}"
                matches = session.scalars(
                    select(Question).where(
                        Question.source_reference == reference
                    )
                ).all()

                if len(matches) != 1:
                    raise RuntimeError(
                        "Expected exactly one seed question for "
                        f"{reference}; found {len(matches)}. "
                        "No explanations were changed."
                    )

                question = matches[0]
                validate_existing_question(question, definition)
                records.append((definition, question))

            # Only explanation is changed below. All other fields are preserved.
            for definition, question in records:
                current = (question.explanation or "").strip()

                if current == definition.explanation:
                    result.already_current += 1
                    continue

                legacy_value = LEGACY_EXPLANATIONS.get(definition.key)
                if not current or (
                    legacy_value is not None and current == legacy_value
                ):
                    question.explanation = definition.explanation
                    result.updated += 1
                    continue

                # A different non-empty explanation may be a manual edit.
                result.preserved_custom += 1

    return result


def main() -> None:
    """Run the backfill against the configured application database."""

    database_name = application_engine.url.database

    if database_name is None or database_name == ":memory:":
        raise RuntimeError(
            "Backfill CLI requires a file-based SQLite database."
        )

    database_path = Path(database_name)

    if not database_path.is_file():
        raise RuntimeError(
            "Database file does not exist: "
            f"{database_path}. Run Alembic migrations first."
        )

    result = update_seed_explanations_vi(application_engine)

    print("VIETNAMESE EXPLANATION BACKFILL COMPLETED")
    print(f"Database: {database_path}")
    print(f"Explanations updated: {result.updated}")
    print(f"Already current: {result.already_current}")
    print(f"Custom explanations preserved: {result.preserved_custom}")
    print("Only the explanation field was changed.")


if __name__ == "__main__":
    main()
