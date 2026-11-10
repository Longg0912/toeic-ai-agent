
"""Metadata tests for study plan ORM models."""

from sqlalchemy import CheckConstraint

# Import model registry so all models are registered in Base.metadata.
from backend.app.db import models  # noqa: F401
from backend.app.db.base import Base


def test_study_plan_tables_are_registered() -> None:
    """Both study plan tables must be registered in shared metadata."""

    assert "study_plans" in Base.metadata.tables
    assert "study_plan_tasks" in Base.metadata.tables


def test_study_plan_has_expected_columns() -> None:
    """Study plan table must expose its required fields."""

    table = Base.metadata.tables["study_plans"]

    expected_columns = {
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
    }

    assert expected_columns.issubset(set(table.columns.keys()))


def test_study_plan_task_has_expected_columns() -> None:
    """Task table must expose its required fields."""

    table = Base.metadata.tables["study_plan_tasks"]

    expected_columns = {
        "id",
        "study_plan_id",
        "skill_id",
        "task_type",
        "scheduled_date",
        "estimated_minutes",
        "target_question_count",
        "status",
        "completed_at",
    }

    assert expected_columns.issubset(set(table.columns.keys()))


def test_study_plan_has_one_active_plan_partial_unique_index() -> None:
    """A user can have at most one active plan."""

    table = Base.metadata.tables["study_plans"]

    index = next(
        index
        for index in table.indexes
        if index.name == "uq_study_plans_one_active_per_user"
    )

    assert index.unique is True
    assert index.dialect_options["sqlite"]["where"] is not None


def test_study_plan_constraints_are_registered() -> None:
    """Important business constraints must exist in metadata."""

    table = Base.metadata.tables["study_plans"]

    constraint_names = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "ck_study_plans_target_score" in constraint_names
    assert "ck_study_plans_daily_minutes" in constraint_names
    assert "ck_study_plans_date_range" in constraint_names
    assert "ck_study_plans_status" in constraint_names


def test_study_plan_task_constraints_are_registered() -> None:
    """Task constraints must exist in metadata."""

    table = Base.metadata.tables["study_plan_tasks"]

    constraint_names = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "ck_study_plan_tasks_task_type" in constraint_names
    assert "ck_study_plan_tasks_status" in constraint_names
    assert "ck_study_plan_tasks_estimated_minutes" in constraint_names
    assert "ck_study_plan_tasks_question_count" in constraint_names
