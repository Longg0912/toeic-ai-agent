"""Idempotent seed for synthetic TOEIC Part 5 demo data.

This script:
- Requires the expected Alembic revision.
- Creates skills and synthetic draft questions.
- Never creates user accounts or passwords.
- Never marks questions as human-approved.
- Does not overwrite existing seed questions.
- Uses one transaction for atomic writes.

Run from the project root:

    python -m scripts.seed_toeic_part5
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from backend.app.db.models import (
    Question,
    QuestionOption,
    QuestionSkill,
    Skill,
)
from backend.app.db.session import engine as application_engine


EXPECTED_REVISION = "c4d8e2a91f70"

SEED_SOURCE_NAME = "TOEIC Tutor Agent synthetic Part 5 seed"

SEED_REFERENCE_PREFIX = "seed:toeic-part5:v1:"


@dataclass(frozen=True)
class SkillSeed:
    """Definition of one TOEIC skill."""

    code: str
    name: str
    category: str


@dataclass(frozen=True)
class QuestionSeed:
    """Definition of one synthetic TOEIC Part 5 question."""

    key: str
    content: str
    options: tuple[str, str, str, str]
    correct_option_key: str
    skill_codes: tuple[str, ...]
    difficulty: int


@dataclass
class SeedResult:
    """Number of newly inserted and existing records."""

    created_skills: int = 0
    existing_skills: int = 0
    created_questions: int = 0
    existing_questions: int = 0


SKILLS: tuple[SkillSeed, ...] = (
    SkillSeed(
        code="GRAMMAR_WORD_FORM",
        name="Word Forms",
        category="grammar",
    ),
    SkillSeed(
        code="GRAMMAR_TENSES",
        name="Verb Tenses",
        category="grammar",
    ),
    SkillSeed(
        code="GRAMMAR_PREPOSITIONS",
        name="Prepositions",
        category="grammar",
    ),
    SkillSeed(
        code="GRAMMAR_SUBJECT_VERB_AGREEMENT",
        name="Subject-Verb Agreement",
        category="grammar",
    ),
    SkillSeed(
        code="VOCAB_BUSINESS",
        name="Business Vocabulary",
        category="vocabulary",
    ),
)


QUESTIONS: tuple[QuestionSeed, ...] = (
    QuestionSeed(
        key="Q001",
        content=(
            "The marketing team prepared a _____ "
            "proposal for the client."
        ),
        options=(
            "detail",
            "detailed",
            "detailing",
            "details",
        ),
        correct_option_key="B",
        skill_codes=(
            "GRAMMAR_WORD_FORM",
            "VOCAB_BUSINESS",
        ),
        difficulty=1,
    ),
    QuestionSeed(
        key="Q002",
        content=(
            "By the time the meeting began, "
            "the manager _____ the report."
        ),
        options=(
            "has finalized",
            "had finalized",
            "finalizes",
            "will finalize",
        ),
        correct_option_key="B",
        skill_codes=("GRAMMAR_TENSES",),
        difficulty=2,
    ),
    QuestionSeed(
        key="Q003",
        content=(
            "All employees must submit their "
            "expense reports _____ Friday."
        ),
        options=(
            "at",
            "by",
            "during",
            "since",
        ),
        correct_option_key="B",
        skill_codes=("GRAMMAR_PREPOSITIONS",),
        difficulty=1,
    ),
    QuestionSeed(
        key="Q004",
        content=(
            "The list of approved suppliers "
            "_____ available on the intranet."
        ),
        options=(
            "are",
            "is",
            "have",
            "were",
        ),
        correct_option_key="B",
        skill_codes=("GRAMMAR_SUBJECT_VERB_AGREEMENT",),
        difficulty=2,
    ),
    QuestionSeed(
        key="Q005",
        content=(
            "The new software allows staff "
            "to process requests more _____."
        ),
        options=(
            "efficient",
            "efficiency",
            "efficiently",
            "efficiencies",
        ),
        correct_option_key="C",
        skill_codes=("GRAMMAR_WORD_FORM",),
        difficulty=1,
    ),
    QuestionSeed(
        key="Q006",
        content=(
            "Ms. Lee has worked in the "
            "finance department _____ 2021."
        ),
        options=(
            "for",
            "since",
            "during",
            "by",
        ),
        correct_option_key="B",
        skill_codes=("GRAMMAR_PREPOSITIONS",),
        difficulty=1,
    ),
)


def normalize_content(content: str) -> str:
    """Normalize question text for deterministic hashing."""

    return re.sub(
        r"\s+",
        " ",
        content.strip(),
    ).casefold()


def calculate_content_hash(content: str) -> str:
    """Return a SHA-256 hash of normalized question text."""

    normalized = normalize_content(content)

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


def validate_seed_definitions() -> None:
    """Validate seed data before opening a transaction."""

    skill_codes = [skill.code for skill in SKILLS]

    if len(skill_codes) != len(set(skill_codes)):
        raise ValueError("Duplicate skill codes in seed data.")

    known_skills = set(skill_codes)
    question_keys: set[str] = set()
    question_hashes: set[str] = set()

    for question in QUESTIONS:
        if question.key in question_keys:
            raise ValueError(
                f"Duplicate question key: {question.key}"
            )

        question_keys.add(question.key)

        if len(question.options) != 4:
            raise ValueError(
                f"Question {question.key} must have 4 options."
            )

        if any(not value.strip() for value in question.options):
            raise ValueError(
                f"Question {question.key} has an empty option."
            )

        if question.correct_option_key not in "ABCD":
            raise ValueError(
                f"Invalid answer key for {question.key}."
            )

        if not question.content.strip():
            raise ValueError(
                f"Empty question content: {question.key}"
            )

        if not 1 <= question.difficulty <= 5:
            raise ValueError(
                f"Invalid difficulty: {question.key}"
            )

        if (
            len(question.skill_codes)
            != len(set(question.skill_codes))
        ):
            raise ValueError(
                f"Duplicate skill links: {question.key}"
            )

        if not question.skill_codes:
            raise ValueError(
                f"Question has no skills: {question.key}"
            )

        unknown = set(question.skill_codes) - known_skills

        if unknown:
            raise ValueError(
                f"Unknown skills in {question.key}: {unknown}"
            )

        content_hash = calculate_content_hash(question.content)

        if content_hash in question_hashes:
            raise ValueError(
                f"Duplicate question content: {question.key}"
            )

        question_hashes.add(content_hash)


def check_database_revision(session: Session) -> None:
    """Prevent seeding a database at an unexpected revision."""

    revision = session.execute(
        text("SELECT version_num FROM alembic_version")
    ).scalar_one_or_none()

    if revision != EXPECTED_REVISION:
        raise RuntimeError(
            "Unexpected database revision. "
            f"Expected {EXPECTED_REVISION}, found {revision!r}. "
            "Check Alembic migrations before seeding."
        )

    foreign_keys_enabled = session.connection().exec_driver_sql(
        "PRAGMA foreign_keys"
    ).scalar_one()

    if foreign_keys_enabled != 1:
        raise RuntimeError(
            "SQLite foreign key enforcement is disabled."
        )


def ensure_skill(
    session: Session,
    definition: SkillSeed,
    result: SeedResult,
) -> Skill:
    """Create a skill only if its stable code does not exist."""

    existing = session.scalar(
        select(Skill).where(
            Skill.code == definition.code
        )
    )

    if existing is not None:
        if (
            existing.name != definition.name
            or existing.category != definition.category
        ):
            raise ValueError(
                "Existing skill conflicts with seed definition: "
                f"{definition.code}"
            )

        result.existing_skills += 1
        return existing

    skill = Skill(
        code=definition.code,
        name=definition.name,
        category=definition.category,
    )

    session.add(skill)
    session.flush()

    result.created_skills += 1
    return skill


def validate_existing_question(
    question: Question,
    definition: QuestionSeed,
) -> None:
    """Reject conflicts instead of overwriting question history."""

    expected_options = dict(
        zip(
            "ABCD",
            definition.options,
            strict=True,
        )
    )

    actual_options = {
        option.option_key: option.content
        for option in question.options
    }

    actual_skills = {
        link.skill.code
        for link in question.skill_links
    }

    expected_skills = set(definition.skill_codes)

    expected_hash = calculate_content_hash(
        definition.content
    )

    fields_match = (
        question.owner_user_id is None
        and question.visibility == "public"
        and question.part == 5
        and question.content == definition.content
        and question.correct_option_key
        == definition.correct_option_key
        and question.content_hash == expected_hash
        and question.difficulty == definition.difficulty
        and question.source_type == "ai_generated"
        and question.source_name == SEED_SOURCE_NAME
    )

    if (
        not fields_match
        or actual_options != expected_options
        or actual_skills != expected_skills
    ):
        raise ValueError(
            "Existing seed question differs from its definition: "
            f"{definition.key}. No records were overwritten."
        )


def ensure_question(
    session: Session,
    definition: QuestionSeed,
    skills_by_code: dict[str, Skill],
    result: SeedResult,
) -> None:
    """Insert a question or verify the existing seed record."""

    reference = (
        f"{SEED_REFERENCE_PREFIX}{definition.key}"
    )

    existing_matches = session.scalars(
        select(Question).where(
            Question.source_reference == reference
        )
    ).all()

    if len(existing_matches) > 1:
        raise ValueError(
            f"Duplicate seed reference in database: {reference}"
        )

    if existing_matches:
        validate_existing_question(
            existing_matches[0],
            definition,
        )

        result.existing_questions += 1
        return

    content_hash = calculate_content_hash(
        definition.content
    )

    duplicate = session.scalar(
        select(Question.id).where(
            Question.part == 5,
            Question.content_hash == content_hash,
            Question.owner_user_id.is_(None),
        )
    )

    if duplicate is not None:
        raise ValueError(
            "Question content already exists outside this seed: "
            f"{definition.key}, existing ID {duplicate}"
        )

    question = Question(
        owner_user_id=None,
        part=5,
        content=definition.content,
        correct_option_key=definition.correct_option_key,
        difficulty=definition.difficulty,
        review_status="draft",
        source_type="ai_generated",
        source_name=SEED_SOURCE_NAME,
        source_reference=reference,
        source_license=None,
        usage_permission_status="unknown",
        visibility="public",
        content_hash=content_hash,
    )

    question.options = [
        QuestionOption(
            option_key=option_key,
            content=option_text,
        )
        for option_key, option_text in zip(
            "ABCD",
            definition.options,
            strict=True,
        )
    ]

    question.skill_links = [
        QuestionSkill(
            skill=skills_by_code[skill_code]
        )
        for skill_code in definition.skill_codes
    ]

    session.add(question)
    session.flush()

    result.created_questions += 1


def seed_demo_data(db_engine: Engine) -> SeedResult:
    """Insert demo data atomically and safely for repeated runs."""

    validate_seed_definitions()

    if db_engine.url.get_backend_name() != "sqlite":
        raise ValueError("Seed supports SQLite only.")

    result = SeedResult()

    with Session(db_engine) as session:
        with session.begin():
            check_database_revision(session)

            skills_by_code: dict[str, Skill] = {}

            for definition in SKILLS:
                skill = ensure_skill(
                    session,
                    definition,
                    result,
                )

                skills_by_code[definition.code] = skill

            for definition in QUESTIONS:
                ensure_question(
                    session,
                    definition,
                    skills_by_code,
                    result,
                )

    return result


def main() -> None:
    """Seed the configured application database."""

    database_name = application_engine.url.database

    if database_name is None or database_name == ":memory:":
        raise RuntimeError(
            "Seed CLI requires a file-based SQLite database."
        )

    database_path = Path(database_name)

    if not database_path.is_file():
        raise RuntimeError(
            "Database file does not exist: "
            f"{database_path}. Run Alembic migrations first."
        )

    result = seed_demo_data(application_engine)

    print("TOEIC PART 5 SEED COMPLETED")
    print(f"Database: {database_path}")
    print(f"Created skills: {result.created_skills}")
    print(f"Existing skills: {result.existing_skills}")
    print(f"Created questions: {result.created_questions}")
    print(f"Existing questions: {result.existing_questions}")
    print("Question review status: draft")


if __name__ == "__main__":
    main()