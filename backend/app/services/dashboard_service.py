
"""Dashboard data aggregation services."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from backend.app.db.models import (
    Attempt,
    QuestionSkill,
    QuizItem,
    QuizSession,
    Skill,
    StudentProfile,
    StudyPlan,
    StudyPlanTask,
    User,
)
from backend.app.schemas.dashboard import (
    DashboardActivityDay,
    DashboardActivityResponse,
    DashboardOverviewResponse,
    DashboardPerformanceResponse,
    DashboardSkillItem,
    DashboardSkillsResponse,
    DashboardStudyPlanResponse,
)
from backend.app.schemas.study_plans import (
    StudyPlanPublic,
    StudyPlanTaskPublic,
)


class DashboardServiceError(Exception):
    """Base exception for dashboard service errors."""


class DashboardStudentNotFoundError(DashboardServiceError):
    """Raised when the requested student does not exist."""


def _get_student_timezone(profile: StudentProfile | None):
    """Resolve the student's timezone.

    UTC is used when the student has no profile or the stored
    timezone identifier is invalid.
    """

    timezone_name = (
        profile.timezone
        if profile is not None and profile.timezone
        else "UTC"
    )

    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return timezone.utc


def get_dashboard_overview(
    db: Session,
    *,
    student_id: int,
) -> DashboardOverviewResponse:
    """Build the learning overview for one student.

    Statistics use first attempts from submitted quiz sessions only.
    This function is read-only and does not commit or modify data.
    """

    if (
        not isinstance(student_id, int)
        or isinstance(student_id, bool)
        or student_id <= 0
    ):
        raise ValueError("student_id must be a positive integer.")

    student = db.get(User, student_id)

    if student is None:
        raise DashboardStudentNotFoundError(
            "Student account does not exist."
        )

    profile = db.get(StudentProfile, student_id)

    # Prefer the active study plan's target score.
    active_plan = db.scalar(
        select(StudyPlan).where(
            StudyPlan.user_id == student_id,
            StudyPlan.status == "active",
        )
    )

    target_score = (
        active_plan.target_score
        if active_plan is not None
        else (
            profile.target_score
            if profile is not None
            else None
        )
    )

    # Count submitted quiz sessions.
    submitted_session_count = (
        db.scalar(
            select(func.count(QuizSession.id)).where(
                QuizSession.user_id == student_id,
                QuizSession.status == "submitted",
            )
        )
        or 0
    )

    # Aggregate first attempts from submitted sessions only.
    progress_statement = (
        select(
            func.count(Attempt.id).label("answered_count"),
            func.coalesce(
                func.sum(
                    case(
                        (Attempt.is_correct.is_(True), 1),
                        else_=0,
                    )
                ),
                0,
            ).label("correct_count"),
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
        .where(
            Attempt.user_id == student_id,
            QuizSession.user_id == student_id,
            QuizSession.status == "submitted",
            Attempt.attempt_number == 1,
        )
    )

    progress_row = db.execute(
        progress_statement
    ).one()

    answered_count = int(progress_row.answered_count or 0)
    correct_count = int(progress_row.correct_count or 0)

    accuracy_percent = (
        round(correct_count / answered_count * 100, 1)
        if answered_count > 0
        else 0.0
    )

    # Determine active days in the student's local timezone.
    submitted_at_statement = (
        select(Attempt.submitted_at)
        .select_from(Attempt)
        .join(
            QuizItem,
            QuizItem.id == Attempt.quiz_item_id,
        )
        .join(
            QuizSession,
            QuizSession.id == QuizItem.quiz_session_id,
        )
        .where(
            Attempt.user_id == student_id,
            QuizSession.user_id == student_id,
            QuizSession.status == "submitted",
            Attempt.attempt_number == 1,
        )
    )

    submitted_timestamps = db.scalars(
        submitted_at_statement
    ).all()

    student_timezone = _get_student_timezone(profile)

    active_dates = set()

    for submitted_at in submitted_timestamps:
        if submitted_at.tzinfo is None:
            # SQLite stores DateTime(timezone=False) as naive values.
            # Quiz submission timestamps are created in UTC.
            submitted_at = submitted_at.replace(
                tzinfo=timezone.utc,
            )
        else:
            submitted_at = submitted_at.astimezone(
                timezone.utc,
            )

        local_date = submitted_at.astimezone(
            student_timezone,
        ).date()

        active_dates.add(local_date)

    return DashboardOverviewResponse(
        target_score=target_score,
        active_plan=(
            StudyPlanPublic.model_validate(active_plan)
            if active_plan is not None
            else None
        ),
        submitted_quiz_sessions=int(submitted_session_count),
        answered_questions=answered_count,
        correct_answers=correct_count,
        accuracy_percent=accuracy_percent,
        active_days=len(active_dates),
    )

def get_dashboard_performance(
    db: Session,
    *,
    student_id: int,
) -> DashboardPerformanceResponse:
    """Return submitted quiz performance for one student.

    Only first attempts from submitted sessions are included.
    Time spent is the sum of recorded first-attempt durations.
    This function is read-only.
    """

    if (
        not isinstance(student_id, int)
        or isinstance(student_id, bool)
        or student_id <= 0
    ):
        raise ValueError("student_id must be a positive integer.")

    student = db.get(User, student_id)

    if student is None:
        raise DashboardStudentNotFoundError(
            "Student account does not exist."
        )

    submitted_sessions = (
        db.scalar(
            select(func.count(QuizSession.id)).where(
                QuizSession.user_id == student_id,
                QuizSession.status == "submitted",
            )
        )
        or 0
    )

    statement = (
        select(
            func.count(Attempt.id).label("answered_count"),
            func.coalesce(
                func.sum(
                    case(
                        (Attempt.is_correct.is_(True), 1),
                        else_=0,
                    )
                ),
                0,
            ).label("correct_count"),
            func.coalesce(
                func.sum(
                    case(
                        (Attempt.is_correct.is_(False), 1),
                        else_=0,
                    )
                ),
                0,
            ).label("incorrect_count"),
            func.coalesce(
                func.sum(Attempt.time_spent_seconds),
                0,
            ).label("total_time_spent"),
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
        .where(
            Attempt.user_id == student_id,
            QuizSession.user_id == student_id,
            QuizSession.status == "submitted",
            Attempt.attempt_number == 1,
        )
    )

    row = db.execute(statement).one()

    answered_count = int(row.answered_count or 0)
    correct_count = int(row.correct_count or 0)
    incorrect_count = int(row.incorrect_count or 0)

    accuracy_percent = (
        round(correct_count / answered_count * 100, 1)
        if answered_count > 0
        else 0.0
    )

    return DashboardPerformanceResponse(
        submitted_sessions=int(submitted_sessions),
        answered_questions=answered_count,
        correct_answers=correct_count,
        incorrect_answers=incorrect_count,
        accuracy_percent=accuracy_percent,
        total_time_spent_seconds=int(
            row.total_time_spent or 0
        ),
    )

def get_dashboard_activity(
    db: Session,
    *,
    student_id: int,
    start_date: date,
    end_date: date,
) -> DashboardActivityResponse:
    """Return daily learning activity for one student.

    Activity dates are based on the quiz session's finished_at
    converted to the student's configured timezone.

    The date range is inclusive. Days without activity are
    included with zero values.
    """

    if (
        not isinstance(student_id, int)
        or isinstance(student_id, bool)
        or student_id <= 0
    ):
        raise ValueError("student_id must be a positive integer.")

    if (
        not isinstance(start_date, date)
        or isinstance(start_date, datetime)
    ):
        raise ValueError("start_date must be a date.")

    if (
        not isinstance(end_date, date)
        or isinstance(end_date, datetime)
    ):
        raise ValueError("end_date must be a date.")

    if end_date < start_date:
        raise ValueError("end_date must not be before start_date.")

    student = db.get(User, student_id)

    if student is None:
        raise DashboardStudentNotFoundError(
            "Student account does not exist."
        )

    profile = db.get(StudentProfile, student_id)
    student_timezone = _get_student_timezone(profile)

    # Convert local date boundaries to UTC.
    # The upper boundary is exclusive to include the full end date.
    start_local = datetime.combine(
        start_date,
        time.min,
        tzinfo=student_timezone,
    )

    end_local_exclusive = datetime.combine(
        end_date + timedelta(days=1),
        time.min,
        tzinfo=student_timezone,
    )

    start_utc = (
        start_local
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
    )

    end_utc_exclusive = (
        end_local_exclusive
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
    )

    # Aggregate each submitted session and its first attempts.
    statement = (
        select(
            QuizSession.id.label("session_id"),
            QuizSession.finished_at.label("finished_at"),
            func.count(Attempt.id).label("answered_count"),
            func.coalesce(
                func.sum(
                    case(
                        (Attempt.is_correct.is_(True), 1),
                        else_=0,
                    )
                ),
                0,
            ).label("correct_count"),
        )
        .select_from(QuizSession)
        .outerjoin(
            QuizItem,
            QuizItem.quiz_session_id == QuizSession.id,
        )
        .outerjoin(
            Attempt,
            (
                (Attempt.quiz_item_id == QuizItem.id)
                & (Attempt.user_id == student_id)
                & (Attempt.attempt_number == 1)
            ),
        )
        .where(
            QuizSession.user_id == student_id,
            QuizSession.status == "submitted",
            QuizSession.finished_at.is_not(None),
            QuizSession.finished_at >= start_utc,
            QuizSession.finished_at < end_utc_exclusive,
        )
        .group_by(
            QuizSession.id,
            QuizSession.finished_at,
        )
        .order_by(QuizSession.finished_at.asc())
    )

    rows = db.execute(statement).all()

    # Prepare zero-value buckets for every date in the range.
    daily_data = {}

    current_date = start_date

    while current_date <= end_date:
        daily_data[current_date] = {
            "submitted_sessions": 0,
            "answered_questions": 0,
            "correct_answers": 0,
        }
        current_date += timedelta(days=1)

    for row in rows:
        finished_at = row.finished_at

        if finished_at.tzinfo is None:
            finished_at = finished_at.replace(
                tzinfo=timezone.utc,
            )
        else:
            finished_at = finished_at.astimezone(
                timezone.utc,
            )

        activity_date = finished_at.astimezone(
            student_timezone,
        ).date()

        # Defensive range check.
        if activity_date not in daily_data:
            continue

        daily_data[activity_date]["submitted_sessions"] += 1
        daily_data[activity_date]["answered_questions"] += int(
            row.answered_count or 0
        )
        daily_data[activity_date]["correct_answers"] += int(
            row.correct_count or 0
        )

    days = []

    for activity_date, values in daily_data.items():
        answered_count = values["answered_questions"]
        correct_count = values["correct_answers"]

        accuracy_percent = (
            round(correct_count / answered_count * 100, 1)
            if answered_count > 0
            else 0.0
        )

        days.append(
            DashboardActivityDay(
                activity_date=activity_date,
                submitted_sessions=values["submitted_sessions"],
                answered_questions=answered_count,
                correct_answers=correct_count,
                accuracy_percent=accuracy_percent,
            )
        )

    total_active_days = sum(
        1
        for values in daily_data.values()
        if values["submitted_sessions"] > 0
    )

    total_submitted_sessions = sum(
        values["submitted_sessions"]
        for values in daily_data.values()
    )

    total_answered_questions = sum(
        values["answered_questions"]
        for values in daily_data.values()
    )

    return DashboardActivityResponse(
        start_date=start_date,
        end_date=end_date,
        days=days,
        total_active_days=total_active_days,
        total_submitted_sessions=total_submitted_sessions,
        total_answered_questions=total_answered_questions,
    )

def get_dashboard_skills(
    db: Session,
    *,
    student_id: int,
) -> DashboardSkillsResponse:
    """Return skill-level performance for one student.

    Only first attempts from submitted quiz sessions are counted.
    A skill is marked as weak when it has at least two first attempts.
    Results are ordered by error rate, attempt count, and skill name.
    This function is read-only.
    """

    if (
        not isinstance(student_id, int)
        or isinstance(student_id, bool)
        or student_id <= 0
    ):
        raise ValueError("student_id must be a positive integer.")

    student = db.get(User, student_id)

    if student is None:
        raise DashboardStudentNotFoundError(
            "Student account does not exist."
        )

    attempt_count = func.count(Attempt.id)

    correct_count = func.coalesce(
        func.sum(
            case(
                (Attempt.is_correct.is_(True), 1),
                else_=0,
            )
        ),
        0,
    )

    incorrect_count = func.coalesce(
        func.sum(
            case(
                (Attempt.is_correct.is_(False), 1),
                else_=0,
            )
        ),
        0,
    )

    error_rate = (
        incorrect_count * 1.0 / attempt_count
    )

    statement = (
        select(
            Skill.id.label("skill_id"),
            Skill.code.label("code"),
            Skill.name.label("name"),
            Skill.category.label("category"),
            attempt_count.label("attempt_count"),
            correct_count.label("correct_count"),
            incorrect_count.label("incorrect_count"),
        )
        .select_from(Skill)
        .join(
            QuestionSkill,
            QuestionSkill.skill_id == Skill.id,
        )
        .join(
            QuizItem,
            QuizItem.question_id == QuestionSkill.question_id,
        )
        .join(
            Attempt,
            Attempt.quiz_item_id == QuizItem.id,
        )
        .join(
            QuizSession,
            QuizSession.id == QuizItem.quiz_session_id,
        )
        .where(
            Attempt.user_id == student_id,
            QuizSession.user_id == student_id,
            QuizSession.status == "submitted",
            Attempt.attempt_number == 1,
        )
        .group_by(
            Skill.id,
            Skill.code,
            Skill.name,
            Skill.category,
        )
        .order_by(
            case(
                (attempt_count >= 2, 0),
                else_=1,
            ).asc(),
            error_rate.desc(),
            attempt_count.desc(),
            Skill.name.asc(),
        )
    )

    rows = db.execute(statement).all()

    items = []

    for row in rows:
        total_attempts = int(row.attempt_count or 0)
        total_correct = int(row.correct_count or 0)
        total_incorrect = int(row.incorrect_count or 0)

        accuracy_percent = (
            round(
                total_correct / total_attempts * 100,
                1,
            )
            if total_attempts > 0
            else 0.0
        )

        items.append(
            DashboardSkillItem(
                skill_id=row.skill_id,
                code=row.code,
                name=row.name,
                category=row.category,
                attempt_count=total_attempts,
                correct_count=total_correct,
                incorrect_count=total_incorrect,
                accuracy_percent=accuracy_percent,
                is_weak=total_attempts >= 2,
            )
        )

    return DashboardSkillsResponse(
        items=items,
        total=len(items),
    )

def get_dashboard_study_plan(
    db: Session,
    *,
    student_id: int,
    today: date | None = None,
) -> DashboardStudyPlanResponse:
    """Return active study plan progress for one student.

    Only the student's active plan is included.
    Upcoming tasks are pending tasks scheduled for today or later,
    limited to the next five tasks.

    This function is read-only and does not commit or modify data.
    """

    if (
        not isinstance(student_id, int)
        or isinstance(student_id, bool)
        or student_id <= 0
    ):
        raise ValueError("student_id must be a positive integer.")

    if today is None:
        today = date.today()
    elif not isinstance(today, date) or isinstance(today, datetime):
        raise ValueError("today must be a date.")

    student = db.get(User, student_id)

    if student is None:
        raise DashboardStudentNotFoundError(
            "Student account does not exist."
        )

    active_plan = db.scalar(
        select(StudyPlan)
        .options(
            selectinload(StudyPlan.tasks).selectinload(
                StudyPlanTask.skill
            )
        )
        .where(
            StudyPlan.user_id == student_id,
            StudyPlan.status == "active",
        )
    )

    if active_plan is None:
        return DashboardStudyPlanResponse(
            plan=None,
            total_tasks=0,
            completed_tasks=0,
            pending_tasks=0,
            skipped_tasks=0,
            completion_percent=0.0,
            upcoming_tasks=[],
        )

    tasks = active_plan.tasks

    total_tasks = len(tasks)

    completed_tasks = sum(
        task.status == "completed"
        for task in tasks
    )

    pending_tasks = sum(
        task.status == "pending"
        for task in tasks
    )

    skipped_tasks = sum(
        task.status == "skipped"
        for task in tasks
    )

    completion_percent = (
        round(
            completed_tasks / total_tasks * 100,
            1,
        )
        if total_tasks > 0
        else 0.0
    )

    upcoming_task_records = db.scalars(
        select(StudyPlanTask)
        .options(
            selectinload(StudyPlanTask.skill)
        )
        .where(
            StudyPlanTask.study_plan_id == active_plan.id,
            StudyPlanTask.status == "pending",
            StudyPlanTask.scheduled_date >= today,
        )
        .order_by(
            StudyPlanTask.scheduled_date.asc(),
            StudyPlanTask.id.asc(),
        )
        .limit(5)
    ).all()

    return DashboardStudyPlanResponse(
        plan=StudyPlanPublic.model_validate(active_plan),
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        pending_tasks=pending_tasks,
        skipped_tasks=skipped_tasks,
        completion_percent=completion_percent,
        upcoming_tasks=[
            StudyPlanTaskPublic.model_validate(task)
            for task in upcoming_task_records
        ],
    )
