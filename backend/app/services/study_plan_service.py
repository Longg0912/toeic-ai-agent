
"""Business logic for creating personalized TOEIC study plans."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.models import (
    Attempt,
    QuestionSkill,
    QuizItem,
    QuizSession,
    Skill,
    StudyPlan,
    StudyPlanTask,
    User,
)


class StudyPlanError(Exception):
    """Base exception for study plan service errors."""


class StudyPlanValidationError(StudyPlanError):
    """Raised when study plan input is invalid."""


class StudyPlanUserNotFoundError(StudyPlanError):
    """Raised when the requested student does not exist."""


class StudyPlanUserNotEligibleError(StudyPlanError):
    """Raised when the account cannot create a study plan."""


class ActiveStudyPlanExistsError(StudyPlanError):
    """Raised when the student already has an active study plan."""

class StudyPlanNotFoundError(StudyPlanError):
    """Raised when the plan does not exist or is not owned by the student."""

class StudyPlanNotActiveError(StudyPlanError):
    """Raised when an operation requires an active study plan."""

class StudyPlanNotPausedError(StudyPlanError):
    """Raised when an operation requires a paused study plan."""

def validate_plan_input(
    *,
    title: str,
    target_score: int,
    start_date: date,
    end_date: date,
    daily_minutes: int,
) -> str:
    """Validate and normalize study plan input."""

    if not isinstance(title, str):
        raise StudyPlanValidationError(
            "Title must be a string."
        )

    normalized_title = title.strip()

    if not normalized_title:
        raise StudyPlanValidationError(
            "Title must not be empty."
        )

    if len(normalized_title) > 200:
        raise StudyPlanValidationError(
            "Title must not exceed 200 characters."
        )

    if (
        not isinstance(target_score, int)
        or isinstance(target_score, bool)
        or not 0 <= target_score <= 990
    ):
        raise StudyPlanValidationError(
            "Target score must be an integer between 0 and 990."
        )

    if (
        not isinstance(daily_minutes, int)
        or isinstance(daily_minutes, bool)
        or daily_minutes <= 0
    ):
        raise StudyPlanValidationError(
            "Daily minutes must be a positive integer."
        )

    if (
        not isinstance(start_date, date)
        or isinstance(start_date, type(None))
        or isinstance(start_date, __import__("datetime").datetime)
    ):
        raise StudyPlanValidationError(
            "Start date must be a date."
        )

    if not isinstance(start_date, date) or isinstance(start_date, datetime):
        raise StudyPlanValidationError(
            "Start date must be a date."
        )

    if not isinstance(end_date, date) or isinstance(end_date, datetime):
        raise StudyPlanValidationError(
            "End date must be a date."
        )

    if end_date < start_date:
        raise StudyPlanValidationError(
            "End date must not be earlier than start date."
        )

    return normalized_title


def get_prioritized_skill_ids(
    db: Session,
    student_id: int,
) -> list[int]:
    """Return skill IDs ordered by weakness, then by skill ID.

    Weakness is calculated from first attempts only.
    A skill requires at least two first attempts.
    Only the authenticated student's records are considered.
    """

    incorrect_count = func.sum(
        case(
            (Attempt.is_correct.is_(False), 1),
            else_=0,
        )
    )

    attempt_count = func.count(Attempt.id)

    error_rate = (
        incorrect_count * 1.0 / attempt_count
    )

    weak_skill_statement = (
        select(
            Skill.id.label("skill_id"),
        )
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
        .group_by(Skill.id)
        .having(attempt_count >= 2)
        .order_by(
            error_rate.desc(),
            attempt_count.desc(),
            Skill.name.asc(),
        )
    )

    weak_skill_ids = list(
        db.scalars(weak_skill_statement).all()
    )

    # Include other skills after identified weak skills.
    # This ensures students can still receive a plan
    # when they have little or no practice history.
    all_skill_ids = list(
        db.scalars(
            select(Skill.id).order_by(Skill.id.asc())
        ).all()
    )

    prioritized_ids = list(weak_skill_ids)

    for skill_id in all_skill_ids:
        if skill_id not in prioritized_ids:
            prioritized_ids.append(skill_id)

    return prioritized_ids


def _get_daily_task_types(
    day_number: int,
    daily_minutes: int,
) -> list[str]:
    """Choose task types for one day."""

    is_quiz_day = day_number % 7 == 0

    if daily_minutes == 1:
        return ["practice"]

    if is_quiz_day:
        if daily_minutes >= 3:
            return ["practice", "review", "quiz"]

        return ["practice", "quiz"]

    return ["practice", "review"]


def _split_daily_minutes(
    daily_minutes: int,
    task_count: int,
) -> list[int]:
    """Split minutes into positive task durations.

    The sum of returned durations always equals daily_minutes.
    """

    if task_count <= 0 or task_count > daily_minutes:
        raise ValueError(
            "Task count must be positive and cannot exceed daily minutes."
        )

    base_minutes, remainder = divmod(
        daily_minutes,
        task_count,
    )

    return [
        base_minutes + (1 if index < remainder else 0)
        for index in range(task_count)
    ]


def generate_study_tasks(
    *,
    plan: StudyPlan,
    prioritized_skill_ids: list[int],
) -> list[StudyPlanTask]:
    """Generate all scheduled tasks for a study plan."""

    tasks: list[StudyPlanTask] = []

    current_date = plan.start_date
    day_number = 1
    skill_count = len(prioritized_skill_ids)

    while current_date <= plan.end_date:
        task_types = _get_daily_task_types(
            day_number,
            plan.daily_minutes,
        )

        durations = _split_daily_minutes(
            plan.daily_minutes,
            len(task_types),
        )

        for index, task_type in enumerate(task_types):
            skill_id: int | None = None

            if skill_count > 0:
                if task_type == "practice":
                    skill_id = prioritized_skill_ids[
                        (day_number - 1) % skill_count
                    ]

                elif task_type == "review":
                    skill_id = prioritized_skill_ids[
                        (day_number - 1) % skill_count
                    ]

            estimated_minutes = durations[index]

            target_question_count = max(
                1,
                estimated_minutes // 2,
            )

            task = StudyPlanTask(
                study_plan=plan,
                skill_id=skill_id,
                task_type=task_type,
                scheduled_date=current_date,
                estimated_minutes=estimated_minutes,
                target_question_count=target_question_count,
                status="pending",
            )

            tasks.append(task)

        current_date += timedelta(days=1)
        day_number += 1

    return tasks


def create_study_plan(
    db: Session,
    *,
    student_id: int,
    title: str,
    target_score: int,
    start_date: date,
    end_date: date,
    daily_minutes: int,
) -> StudyPlan:
    """Create a study plan and its daily tasks.

    Transaction policy:
    - Commit the plan and all tasks together.
    - Roll back all changes if any write fails.
    - Only one active plan is allowed per student.
    """

    normalized_title = validate_plan_input(
        title=title,
        target_score=target_score,
        start_date=start_date,
        end_date=end_date,
        daily_minutes=daily_minutes,
    )

    try:
        # 1. Verify the student account.
        student = db.get(User, student_id)

        if student is None:
            raise StudyPlanUserNotFoundError(
                "Student account does not exist."
            )

        if student.role != "student" or not student.is_active:
            raise StudyPlanUserNotEligibleError(
                "Only active student accounts can create study plans."
            )

        # 2. Check for an existing active plan.
        existing_plan_statement = select(
            StudyPlan.id
        ).where(
            StudyPlan.user_id == student_id,
            StudyPlan.status == "active",
        )

        existing_plan_id = db.scalar(
            existing_plan_statement
        )

        if existing_plan_id is not None:
            raise ActiveStudyPlanExistsError(
                "The student already has an active study plan."
            )

        # 3. Find skills, prioritizing weak skills.
        prioritized_skill_ids = get_prioritized_skill_ids(
            db,
            student_id,
        )

        # 4. Create the plan.
        plan = StudyPlan(
            user_id=student_id,
            title=normalized_title,
            target_score=target_score,
            start_date=start_date,
            end_date=end_date,
            daily_minutes=daily_minutes,
            status="active",
        )

        db.add(plan)
        db.flush()

        # 5. Generate and attach all tasks.
        tasks = generate_study_tasks(
            plan=plan,
            prioritized_skill_ids=prioritized_skill_ids,
        )

        db.add_all(tasks)

        # 6. Commit plan and tasks atomically.
        db.commit()
        db.refresh(plan)

        return plan

    except ActiveStudyPlanExistsError:
        db.rollback()
        raise

    except (
        StudyPlanUserNotFoundError,
        StudyPlanUserNotEligibleError,
    ):
        db.rollback()
        raise

    except IntegrityError:
        db.rollback()

        # Handle a concurrent request that created an active plan.
        existing_plan_id = db.scalar(
            select(StudyPlan.id).where(
                StudyPlan.user_id == student_id,
                StudyPlan.status == "active",
            )
        )

        if existing_plan_id is not None:
            raise ActiveStudyPlanExistsError(
                "The student already has an active study plan."
            ) from None

        raise

    except Exception:
        db.rollback()
        raise


def _get_owned_study_plan(
    db: Session,
    *,
    student_id: int,
    plan_id: int,
) -> StudyPlan:
    """Get a study plan only if it belongs to the requested student."""

    plan = db.scalar(
        select(StudyPlan).where(
            StudyPlan.id == plan_id,
            StudyPlan.user_id == student_id,
        )
    )

    if plan is None:
        raise StudyPlanNotFoundError(
            "Study plan does not exist or does not belong to this student."
        )

    return plan


def pause_study_plan(
    db: Session,
    *,
    student_id: int,
    plan_id: int,
) -> StudyPlan:
    """Pause an active study plan without modifying its tasks."""

    try:
        plan = _get_owned_study_plan(
            db,
            student_id=student_id,
            plan_id=plan_id,
        )

        if plan.status != "active":
            raise StudyPlanNotActiveError(
                "Only an active study plan can be paused."
            )

        plan.status = "paused"

        db.commit()
        db.refresh(plan)

        return plan

    except (
        StudyPlanNotFoundError,
        StudyPlanNotActiveError,
    ):
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise


def resume_study_plan(
    db: Session,
    *,
    student_id: int,
    plan_id: int,
) -> StudyPlan:
    """Resume a paused study plan if no other active plan exists."""

    try:
        plan = _get_owned_study_plan(
            db,
            student_id=student_id,
            plan_id=plan_id,
        )

        if plan.status != "paused":
            raise StudyPlanNotPausedError(
                "Only a paused study plan can be resumed."
            )

        existing_active_plan_id = db.scalar(
            select(StudyPlan.id).where(
                StudyPlan.user_id == student_id,
                StudyPlan.status == "active",
                StudyPlan.id != plan.id,
            )
        )

        if existing_active_plan_id is not None:
            raise ActiveStudyPlanExistsError(
                "The student already has an active study plan."
            )

        plan.status = "active"

        db.commit()
        db.refresh(plan)

        return plan

    except (
        StudyPlanNotFoundError,
        StudyPlanNotPausedError,
        ActiveStudyPlanExistsError,
    ):
        db.rollback()
        raise

    except IntegrityError:
        db.rollback()

        # Protect against concurrent requests that activate
        # another plan after the initial existence check.
        existing_active_plan_id = db.scalar(
            select(StudyPlan.id).where(
                StudyPlan.user_id == student_id,
                StudyPlan.status == "active",
            )
        )

        if existing_active_plan_id is not None:
            raise ActiveStudyPlanExistsError(
                "The student already has an active study plan."
            ) from None

        raise

    except Exception:
        db.rollback()
        raise

def complete_study_plan(
    db: Session,
    *,
    student_id: int,
    plan_id: int,
) -> StudyPlan:
    """Complete an active study plan without deleting its tasks."""

    try:
        plan = _get_owned_study_plan(
            db,
            student_id=student_id,
            plan_id=plan_id,
        )

        if plan.status != "active":
            raise StudyPlanNotActiveError(
                "Only an active study plan can be completed."
            )

        plan.status = "completed"

        db.commit()
        db.refresh(plan)

        return plan

    except (
        StudyPlanNotFoundError,
        StudyPlanNotActiveError,
    ):
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise
