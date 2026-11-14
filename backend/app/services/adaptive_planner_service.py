
"""Adaptive study plan scheduling based on student performance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from backend.app.db.models import (
    Attempt,
    QuestionSkill,
    QuizItem,
    QuizSession,
    Skill,
    StudyPlan,
    StudyPlanTask,
)


class AdaptivePlannerError(Exception):
    """Base exception for adaptive planner errors."""


class AdaptivePlannerValidationError(AdaptivePlannerError):
    """Raised when adaptive planner input is invalid."""


class AdaptivePlanNotFoundError(AdaptivePlannerError):
    """Raised when the requested plan does not exist or is not owned."""


class AdaptivePlanNotActiveError(AdaptivePlannerError):
    """Raised when the requested plan is not active."""


@dataclass(frozen=True)
class AdaptivePlannerResult:
    """Summary of one adaptive scheduling operation."""

    plan_id: int
    updated_task_count: int
    prioritized_skill_ids: tuple[int, ...]


def get_weak_skill_ids(
    db: Session,
    student_id: int,
) -> list[int]:
    """Return weak skill IDs ordered by first-attempt error rate.

    A skill must have at least two first attempts to qualify.
    Only records belonging to the requested student are considered.
    """

    incorrect_count = func.sum(
        case(
            (Attempt.is_correct.is_(False), 1),
            else_=0,
        )
    )

    attempt_count = func.count(Attempt.id)

    error_rate = incorrect_count * 1.0 / attempt_count

    statement = (
        select(Skill.id)
        .select_from(Attempt)
        .join(
            QuizItem,
            QuizItem.id == Attempt.quiz_item_id,
        )
        .join(
            QuizSession,
            QuizSession.id == QuizItem.quiz_session_id,
        )
        .join(
            QuestionSkill,
            QuestionSkill.question_id == QuizItem.question_id,
        )
        .join(
            Skill,
            Skill.id == QuestionSkill.skill_id,
        )
        .where(
            Attempt.user_id == student_id,
            QuizSession.user_id == student_id,
            Attempt.attempt_number == 1,
        )
        .group_by(
            Skill.id,
            Skill.name,
        )
        .having(
            attempt_count >= 2,
        )
        .order_by(
            error_rate.desc(),
            attempt_count.desc(),
            Skill.name.asc(),
        )
    )

    return list(db.scalars(statement).all())


def _validate_adaptive_input(
    *,
    student_id: int,
    plan_id: int,
    today: date,
) -> None:
    """Validate identifiers and the reference date."""

    if (
        not isinstance(student_id, int)
        or isinstance(student_id, bool)
        or student_id <= 0
    ):
        raise AdaptivePlannerValidationError(
            "Student ID must be a positive integer."
        )

    if (
        not isinstance(plan_id, int)
        or isinstance(plan_id, bool)
        or plan_id <= 0
    ):
        raise AdaptivePlannerValidationError(
            "Study plan ID must be a positive integer."
        )

    if not isinstance(today, date) or isinstance(today, datetime):
        raise AdaptivePlannerValidationError(
            "Today must be a date."
        )


def adapt_study_plan(
    db: Session,
    *,
    student_id: int,
    plan_id: int,
    today: date | None = None,
) -> AdaptivePlannerResult:
    """Reassign future pending practice/review tasks to weak skills.

    Completed tasks, skipped tasks, quiz tasks, past tasks, task duration,
    and target question counts are never modified.

    The operation is committed atomically. Any unexpected error rolls
    back all changes.
    """

    reference_date = today if today is not None else date.today()

    _validate_adaptive_input(
        student_id=student_id,
        plan_id=plan_id,
        today=reference_date,
    )

    try:
        # 1. Load the plan and verify ownership.
        plan = db.scalar(
            select(StudyPlan).where(
                StudyPlan.id == plan_id,
                StudyPlan.user_id == student_id,
            )
        )

        if plan is None:
            raise AdaptivePlanNotFoundError(
                "Study plan does not exist or does not belong to this student."
            )

        if plan.status != "active":
            raise AdaptivePlanNotActiveError(
                "Only an active study plan can be adapted."
            )

        # 2. Find weak skills using the student's first attempts.
        weak_skill_ids = get_weak_skill_ids(
            db,
            student_id,
        )

        # 3. No reliable weakness data: keep the existing schedule.
        if not weak_skill_ids:
            db.commit()

            return AdaptivePlannerResult(
                plan_id=plan.id,
                updated_task_count=0,
                prioritized_skill_ids=(),
            )

        # 4. Select only future pending practice/review tasks.
        pending_tasks = list(
            db.scalars(
                select(StudyPlanTask)
                .where(
                    StudyPlanTask.study_plan_id == plan.id,
                    StudyPlanTask.status == "pending",
                    StudyPlanTask.scheduled_date > reference_date,
                    StudyPlanTask.task_type.in_(
                        ["practice", "review"]
                    ),
                )
                .order_by(
                    StudyPlanTask.scheduled_date.asc(),
                    StudyPlanTask.id.asc(),
                )
            ).all()
        )

        # 5. Assign weak skills in priority order.
        updated_task_count = 0

        for index, task in enumerate(pending_tasks):
            new_skill_id = weak_skill_ids[
                index % len(weak_skill_ids)
            ]

            if task.skill_id != new_skill_id:
                task.skill_id = new_skill_id
                updated_task_count += 1

        # 6. Commit all task changes together.
        db.commit()

        return AdaptivePlannerResult(
            plan_id=plan.id,
            updated_task_count=updated_task_count,
            prioritized_skill_ids=tuple(weak_skill_ids),
        )

    except (
        AdaptivePlanNotFoundError,
        AdaptivePlanNotActiveError,
    ):
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise
