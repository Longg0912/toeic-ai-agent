
"""Study plan and scheduled learning task ORM models."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base

from backend.app.db.models.core import Skill
class StudyPlan(Base):
    """A personalized study plan owned by one user."""

    __tablename__ = "study_plans"

    __table_args__ = (
        CheckConstraint(
            "target_score BETWEEN 0 AND 990",
            name="ck_study_plans_target_score",
        ),
        CheckConstraint(
            "daily_minutes > 0",
            name="ck_study_plans_daily_minutes",
        ),
        CheckConstraint(
            "end_date >= start_date",
            name="ck_study_plans_date_range",
        ),
        CheckConstraint(
            "status IN ('active', 'completed', 'paused', 'cancelled')",
            name="ck_study_plans_status",
        ),
        Index(
            "ix_study_plans_user_status",
            "user_id",
            "status",
        ),
        Index(
            "uq_study_plans_one_active_per_user",
            "user_id",
            unique=True,
            sqlite_where=text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    target_score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    start_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    end_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    daily_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'active'"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    tasks: Mapped[list[StudyPlanTask]] = relationship(
        back_populates="study_plan",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="StudyPlanTask.scheduled_date",
    )


class StudyPlanTask(Base):
    """One scheduled learning activity inside a study plan."""

    __tablename__ = "study_plan_tasks"

    __table_args__ = (
        CheckConstraint(
            "task_type IN ('practice', 'review', 'quiz')",
            name="ck_study_plan_tasks_task_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'completed', 'skipped')",
            name="ck_study_plan_tasks_status",
        ),
        CheckConstraint(
            "estimated_minutes > 0",
            name="ck_study_plan_tasks_estimated_minutes",
        ),
        CheckConstraint(
            "target_question_count > 0",
            name="ck_study_plan_tasks_question_count",
        ),
        Index(
            "ix_study_plan_tasks_plan_date_status",
            "study_plan_id",
            "scheduled_date",
            "status",
        ),
        Index(
            "ix_study_plan_tasks_skill_id",
            "skill_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    study_plan_id: Mapped[int] = mapped_column(
        ForeignKey("study_plans.id", ondelete="CASCADE"),
        nullable=False,
    )

    skill_id: Mapped[int | None] = mapped_column(
        ForeignKey("skills.id", ondelete="SET NULL"),
        nullable=True,
    )

    task_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    scheduled_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    estimated_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    target_question_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'pending'"),
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )

    study_plan: Mapped[StudyPlan] = relationship(
        back_populates="tasks",
    )

    skill: Mapped[Skill | None] = relationship()
