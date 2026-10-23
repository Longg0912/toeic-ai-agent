"""add third party question source and explanation

Revision ID: 55db8077d91e
Revises: da7ab3c9873a
Create Date: 2026-10-23 15:42:19.523080

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '55db8077d91e'
down_revision: Union[str, Sequence[str], None] = 'da7ab3c9873a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add question explanation and third-party source support."""

    with op.batch_alter_table(
        "questions",
        recreate="always",
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "explanation",
                sa.Text(),
                nullable=True,
            )
        )

        batch_op.drop_constraint(
            "ck_questions_source_type",
            type_="check",
        )

        batch_op.create_check_constraint(
            "ck_questions_source_type",
            "source_type IN "
            "('original', 'licensed', 'ai_generated', "
            "'user_uploaded', 'third_party')",
        )


def downgrade() -> None:
    """Revert schema changes without discarding question data."""

    bind = op.get_bind()

    third_party_count = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM questions "
            "WHERE source_type = 'third_party'"
        )
    ).scalar_one()

    explanation_count = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM questions "
            "WHERE explanation IS NOT NULL"
        )
    ).scalar_one()

    if third_party_count:
        raise RuntimeError(
            "Cannot downgrade while third-party questions exist."
        )

    if explanation_count:
        raise RuntimeError(
            "Cannot downgrade while question explanations exist."
        )

    with op.batch_alter_table(
        "questions",
        recreate="always",
    ) as batch_op:
        batch_op.drop_column("explanation")

        batch_op.drop_constraint(
            "ck_questions_source_type",
            type_="check",
        )

        batch_op.create_check_constraint(
            "ck_questions_source_type",
            "source_type IN "
            "('original', 'licensed', 'ai_generated', "
            "'user_uploaded')",
        )
