
"""Add grammar skills for TOEIC Part 5 mapping."""

from alembic import op
import sqlalchemy as sa


revision = "b7e4c91a2d63"
down_revision = "55db8077d91e"
branch_labels = None
depends_on = None


NEW_SKILLS = [
    (
        "GRAMMAR_INVERSION",
        "Inversion",
        "grammar",
    ),
    (
        "GRAMMAR_CLAUSES_CONJUNCTIONS",
        "Conjunctions and Clauses",
        "grammar",
    ),
    (
        "GRAMMAR_QUANTIFIERS_DETERMINERS",
        "Quantifiers and Determiners",
        "grammar",
    ),
    (
        "GRAMMAR_RELATIVE_CLAUSES",
        "Relative Clauses",
        "grammar",
    ),
    (
        "GRAMMAR_INFINITIVES",
        "Infinitives and Verb Patterns",
        "grammar",
    ),
    (
        "GRAMMAR_GERUNDS",
        "Gerunds",
        "grammar",
    ),
    (
        "GRAMMAR_PARALLELISM",
        "Parallel Structure",
        "grammar",
    ),
    (
        "GRAMMAR_PARTICIPLE_CLAUSES",
        "Participle Clauses",
        "grammar",
    ),
    (
        "GRAMMAR_PASSIVE_VOICE",
        "Passive Voice",
        "grammar",
    ),
    (
        "GRAMMAR_SUBJUNCTIVE",
        "Subjunctive Mood",
        "grammar",
    ),
    (
        "GRAMMAR_COMPARISON",
        "Comparison and Superlatives",
        "grammar",
    ),
]


def upgrade() -> None:
    skills_table = sa.table(
        "skills",
        sa.column("code", sa.String(length=64)),
        sa.column("name", sa.String(length=150)),
        sa.column("category", sa.String(length=32)),
    )

    op.bulk_insert(
        skills_table,
        [
            {
                "code": code,
                "name": name,
                "category": category,
            }
            for code, name, category in NEW_SKILLS
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()

    # Remove the question-skill links created for these skills
    # before deleting the corresponding skill records.
    for code, _, _ in reversed(NEW_SKILLS):
        result = bind.execute(
            sa.text(
                "SELECT id FROM skills WHERE code = :code"
            ),
            {"code": code},
        ).first()

        if result is None:
            continue

        skill_id = result[0]

        bind.execute(
            sa.text(
                "DELETE FROM question_skills "
                "WHERE skill_id = :skill_id"
            ),
            {"skill_id": skill_id},
        )

        bind.execute(
            sa.text(
                "DELETE FROM skills WHERE id = :skill_id"
            ),
            {"skill_id": skill_id},
        )
