
"""Add grammar pronouns skill for TOEIC Part 5."""

from alembic import op
import sqlalchemy as sa


revision = "c4d8e2a91f70"
down_revision = "b7e4c91a2d63"
branch_labels = None
depends_on = None


SKILL_CODE = "GRAMMAR_PRONOUNS"
SKILL_NAME = "Pronouns and Possessives"
SKILL_CATEGORY = "grammar"


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
                "code": SKILL_CODE,
                "name": SKILL_NAME,
                "category": SKILL_CATEGORY,
            }
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()

    result = bind.execute(
        sa.text("SELECT id FROM skills WHERE code = :code"),
        {"code": SKILL_CODE},
    ).first()

    if result is None:
        return

    skill_id = result[0]

    bind.execute(
        sa.text(
            "DELETE FROM question_skills WHERE skill_id = :skill_id"
        ),
        {"skill_id": skill_id},
    )

    bind.execute(
        sa.text("DELETE FROM skills WHERE id = :skill_id"),
        {"skill_id": skill_id},
    )
