"""add study plan tables

Revision ID: f2f8eab7a67a
Revises: f1a9c3d7e205
Create Date: 2026-11-10 15:30:44.319468

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2f8eab7a67a'
down_revision: Union[str, Sequence[str], None] = 'f1a9c3d7e205'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    """Create Study Plan tables and indexes."""

    op.create_table(
        "study_plans",
        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("target_score", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("daily_minutes", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'paused', 'cancelled')",
            name="ck_study_plans_status",
        ),
        sa.CheckConstraint(
            "daily_minutes > 0",
            name="ck_study_plans_daily_minutes",
        ),
        sa.CheckConstraint(
            "end_date >= start_date",
            name="ck_study_plans_date_range",
        ),
        sa.CheckConstraint(
            "target_score BETWEEN 0 AND 990",
            name="ck_study_plans_target_score",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes directly.
    # Do not use batch_alter_table for these indexes.
    op.create_index(
        "ix_study_plans_user_status",
        "study_plans",
        ["user_id", "status"],
        unique=False,
    )

    op.create_index(
        "uq_study_plans_one_active_per_user",
        "study_plans",
        ["user_id"],
        unique=True,
        sqlite_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "study_plan_tasks",
        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("study_plan_id", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=True),
        sa.Column("task_type", sa.String(length=20), nullable=False),
        sa.Column("scheduled_date", sa.Date(), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("target_question_count", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'skipped')",
            name="ck_study_plan_tasks_status",
        ),
        sa.CheckConstraint(
            "task_type IN ('practice', 'review', 'quiz')",
            name="ck_study_plan_tasks_task_type",
        ),
        sa.CheckConstraint(
            "estimated_minutes > 0",
            name="ck_study_plan_tasks_estimated_minutes",
        ),
        sa.CheckConstraint(
            "target_question_count > 0",
            name="ck_study_plan_tasks_question_count",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["skills.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["study_plan_id"],
            ["study_plans.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_study_plan_tasks_plan_date_status",
        "study_plan_tasks",
        ["study_plan_id", "scheduled_date", "status"],
        unique=False,
    )

    op.create_index(
        "ix_study_plan_tasks_skill_id",
        "study_plan_tasks",
        ["skill_id"],
        unique=False,
    )



def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        "ix_study_plan_tasks_skill_id",
        table_name="study_plan_tasks",
    )

    op.drop_index(
        "ix_study_plan_tasks_plan_date_status",
        table_name="study_plan_tasks",
    )

    op.drop_table("study_plan_tasks")

    op.drop_index(
        "uq_study_plans_one_active_per_user",
        table_name="study_plans",
    )

    op.drop_index(
        "ix_study_plans_user_status",
        table_name="study_plans",
    )

    op.drop_table("study_plans")