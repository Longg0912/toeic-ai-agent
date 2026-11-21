
"""Tests for dashboard overview service."""

from collections.abc import Iterator
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.db.models import (
    Attempt,
    Question,
    QuestionSkill,
    QuizItem,
    QuizSession,
    Skill,
    StudentProfile,
    StudyPlan,
    StudyPlanTask,
    User,
)
from backend.app.services.dashboard_service import (
    DashboardStudentNotFoundError,
    get_dashboard_activity,
    get_dashboard_overview,
    get_dashboard_performance,
    get_dashboard_skills,
    get_dashboard_study_plan,
)

@pytest.fixture
def db() -> Iterator[Session]:
    """Create an isolated in-memory SQLite database."""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session

    engine.dispose()


def create_user(
    db: Session,
    email: str,
    target_score: int | None = None,
    timezone_name: str = "Asia/Ho_Chi_Minh",
) -> User:
    """Create a student and optional learning profile."""

    user = User(
        email=email,
        password_hash="test-only-password-hash",
    )
    db.add(user)
    db.flush()

    if target_score is not None:
        db.add(
            StudentProfile(
                user_id=user.id,
                target_score=target_score,
                timezone=timezone_name,
            )
        )
        db.flush()

    return user
def create_study_plan(
    db: Session,
    *,
    user_id: int,
    status: str = "active",
    title: str = "Dashboard study plan",
) -> StudyPlan:
    """Create a study plan for dashboard tests."""

    plan = StudyPlan(
        user_id=user_id,
        title=title,
        target_score=800,
        start_date=date(2026, 11, 1),
        end_date=date(2026, 12, 31),
        daily_minutes=60,
        status=status,
    )
    db.add(plan)
    db.flush()

    return plan


def create_study_plan_task(
    db: Session,
    *,
    study_plan_id: int,
    scheduled_date: date,
    status: str = "pending",
    skill_id: int | None = None,
    task_type: str = "practice",
) -> StudyPlanTask:
    """Create a study plan task for dashboard tests."""

    task = StudyPlanTask(
        study_plan_id=study_plan_id,
        skill_id=skill_id,
        task_type=task_type,
        scheduled_date=scheduled_date,
        estimated_minutes=30,
        target_question_count=15,
        status=status,
    )
    db.add(task)
    db.flush()

    return task

def create_submitted_attempt(
    db: Session,
    *,
    user_id: int,
    question_number: int,
    submitted_at: datetime,
    is_correct: bool,
    time_spent_seconds: int | None = None,
) -> QuizSession:
    """Create one submitted quiz session with a first attempt."""

    question = Question(
        part=5,
        content=f"Dashboard question {question_number}",
        correct_option_key="A",
        content_hash=f"{question_number:064d}",
    )
    db.add(question)
    db.flush()

    quiz_session = QuizSession(
        user_id=user_id,
        status="submitted",
        started_at=submitted_at,
        finished_at=submitted_at,
    )
    db.add(quiz_session)
    db.flush()

    quiz_item = QuizItem(
        quiz_session_id=quiz_session.id,
        question_id=question.id,
        position=1,
        question_snapshot={
            "content": f"Dashboard question {question_number}",
        },
        answer_key_snapshot="A",
    )
    db.add(quiz_item)
    db.flush()

    db.add(
        Attempt(
            user_id=user_id,
            quiz_item_id=quiz_item.id,
            attempt_number=1,
            selected_option_key="A" if is_correct else "B",
            is_correct=is_correct,
            is_retry=False,
            time_spent_seconds=time_spent_seconds,
            submitted_at=submitted_at,
        )
    )
    db.flush()

    return quiz_session

def attach_skill_to_session(
    db: Session,
    *,
    quiz_session: QuizSession,
    skill: Skill,
) -> None:
    """Attach a skill to the question in a quiz session."""

    quiz_item = (
        db.query(QuizItem)
        .filter(
            QuizItem.quiz_session_id == quiz_session.id
        )
        .one()
    )

    db.add(
        QuestionSkill(
            question_id=quiz_item.question_id,
            skill_id=skill.id,
        )
    )
    db.flush()


def test_overview_returns_empty_statistics_for_new_student(
    db: Session,
) -> None:
    user = create_user(
        db,
        "new-student@example.test",
        target_score=750,
    )
    db.commit()

    result = get_dashboard_overview(
        db,
        student_id=user.id,
    )

    assert result.target_score == 750
    assert result.active_plan is None
    assert result.submitted_quiz_sessions == 0
    assert result.answered_questions == 0
    assert result.correct_answers == 0
    assert result.accuracy_percent == 0.0
    assert result.active_days == 0


def test_overview_uses_active_plan_target_score(
    db: Session,
) -> None:
    user = create_user(
        db,
        "plan-student@example.test",
        target_score=650,
    )

    plan = StudyPlan(
        user_id=user.id,
        title="TOEIC target plan",
        target_score=850,
        start_date=date(2026, 11, 1),
        end_date=date(2026, 12, 1),
        daily_minutes=60,
        status="active",
    )
    db.add(plan)
    db.commit()

    result = get_dashboard_overview(
        db,
        student_id=user.id,
    )

    assert result.target_score == 850
    assert result.active_plan is not None
    assert result.active_plan.id == plan.id


def test_overview_counts_only_first_attempts_from_submitted_sessions(
    db: Session,
) -> None:
    user = create_user(
        db,
        "quiz-student@example.test",
        target_score=700,
    )

    submitted_at = datetime(
        2026,
        11,
        20,
        10,
        0,
        tzinfo=timezone.utc,
    )

    session_one = create_submitted_attempt(
        db,
        user_id=user.id,
        question_number=1,
        submitted_at=submitted_at,
        is_correct=True,
    )

    session_two = create_submitted_attempt(
        db,
        user_id=user.id,
        question_number=2,
        submitted_at=submitted_at,
        is_correct=False,
    )

    # Add a retry to the first quiz item.
    first_item = db.query(QuizItem).filter(
        QuizItem.quiz_session_id == session_one.id
    ).one()

    db.add(
        Attempt(
            user_id=user.id,
            quiz_item_id=first_item.id,
            attempt_number=2,
            selected_option_key="B",
            is_correct=False,
            is_retry=True,
            submitted_at=submitted_at,
        )
    )

    # An unfinished session must not contribute to the overview.
    unfinished_session = QuizSession(
        user_id=user.id,
        status="in_progress",
        started_at=submitted_at,
    )
    db.add(unfinished_session)

    db.commit()

    result = get_dashboard_overview(
        db,
        student_id=user.id,
    )

    assert result.submitted_quiz_sessions == 2
    assert result.answered_questions == 2
    assert result.correct_answers == 1
    assert result.accuracy_percent == 50.0
    assert result.active_days == 1


def test_overview_calculates_active_days_in_student_timezone(
    db: Session,
) -> None:
    user = create_user(
        db,
        "timezone-student@example.test",
        target_score=750,
        timezone_name="Asia/Ho_Chi_Minh",
    )

    # 17:30 UTC on November 20 = 00:30 on November 21 in Vietnam.
    create_submitted_attempt(
        db,
        user_id=user.id,
        question_number=10,
        submitted_at=datetime(
            2026,
            11,
            20,
            17,
            30,
            tzinfo=timezone.utc,
        ),
        is_correct=True,
    )

    # 18:30 UTC is still November 21 in Vietnam.
    create_submitted_attempt(
        db,
        user_id=user.id,
        question_number=11,
        submitted_at=datetime(
            2026,
            11,
            20,
            18,
            30,
            tzinfo=timezone.utc,
        ),
        is_correct=True,
    )

    # 17:30 UTC on November 21 = 00:30 on November 22 in Vietnam.
    create_submitted_attempt(
        db,
        user_id=user.id,
        question_number=12,
        submitted_at=datetime(
            2026,
            11,
            21,
            17,
            30,
            tzinfo=timezone.utc,
        ),
        is_correct=False,
    )

    db.commit()

    result = get_dashboard_overview(
        db,
        student_id=user.id,
    )

    assert result.active_days == 2
    assert result.answered_questions == 3


def test_overview_does_not_read_another_student_data(
    db: Session,
) -> None:
    student_one = create_user(
        db,
        "one-dashboard@example.test",
        target_score=750,
    )
    student_two = create_user(
        db,
        "two-dashboard@example.test",
        target_score=600,
    )

    create_submitted_attempt(
        db,
        user_id=student_one.id,
        question_number=20,
        submitted_at=datetime(
            2026,
            11,
            20,
            10,
            0,
            tzinfo=timezone.utc,
        ),
        is_correct=True,
    )

    db.commit()

    result = get_dashboard_overview(
        db,
        student_id=student_two.id,
    )

    assert result.target_score == 600
    assert result.submitted_quiz_sessions == 0
    assert result.answered_questions == 0
    assert result.correct_answers == 0
    assert result.active_days == 0


def test_overview_raises_when_student_does_not_exist(
    db: Session,
) -> None:
    with pytest.raises(DashboardStudentNotFoundError):
        get_dashboard_overview(
            db,
            student_id=999,
        )


@pytest.mark.parametrize(
    "student_id",
    [0, -1, True, "1", None],
)
def test_overview_rejects_invalid_student_id(
    db: Session,
    student_id: object,
) -> None:
    with pytest.raises(ValueError):
        get_dashboard_overview(
            db,
            student_id=student_id,
        )

def test_performance_counts_only_first_attempts_and_submitted_sessions(
    db: Session,
) -> None:
    user = create_user(
        db,
        "performance-student@example.test",
        target_score=750,
    )

    submitted_at = datetime(
        2026,
        11,
        20,
        10,
        0,
        tzinfo=timezone.utc,
    )

    session_one = create_submitted_attempt(
        db,
        user_id=user.id,
        question_number=101,
        submitted_at=submitted_at,
        is_correct=True,
        time_spent_seconds=30,
    )

    create_submitted_attempt(
        db,
        user_id=user.id,
        question_number=102,
        submitted_at=submitted_at,
        is_correct=False,
        time_spent_seconds=45,
    )

    first_item = db.query(QuizItem).filter(
        QuizItem.quiz_session_id == session_one.id
    ).one()

    # Retry must not contribute to performance or time.
    db.add(
        Attempt(
            user_id=user.id,
            quiz_item_id=first_item.id,
            attempt_number=2,
            selected_option_key="B",
            is_correct=False,
            is_retry=True,
            time_spent_seconds=100,
            submitted_at=submitted_at,
        )
    )

    # Unfinished sessions must not contribute.
    unfinished = QuizSession(
        user_id=user.id,
        status="in_progress",
        started_at=submitted_at,
    )
    db.add(unfinished)

    db.commit()

    result = get_dashboard_performance(
        db,
        student_id=user.id,
    )

    assert result.submitted_sessions == 2
    assert result.answered_questions == 2
    assert result.correct_answers == 1
    assert result.incorrect_answers == 1
    assert result.accuracy_percent == 50.0
    assert result.total_time_spent_seconds == 75


def test_performance_returns_zero_values_without_quiz_data(
    db: Session,
) -> None:
    user = create_user(
        db,
        "empty-performance@example.test",
    )
    db.commit()

    result = get_dashboard_performance(
        db,
        student_id=user.id,
    )

    assert result.submitted_sessions == 0
    assert result.answered_questions == 0
    assert result.correct_answers == 0
    assert result.incorrect_answers == 0
    assert result.accuracy_percent == 0.0
    assert result.total_time_spent_seconds == 0


def test_performance_rejects_unknown_student(
    db: Session,
) -> None:
    with pytest.raises(DashboardStudentNotFoundError):
        get_dashboard_performance(
            db,
            student_id=999,
        )


@pytest.mark.parametrize(
    "student_id",
    [0, -1, True, "1", None],
)
def test_performance_rejects_invalid_student_id(
    db: Session,
    student_id: object,
) -> None:
    with pytest.raises(ValueError):
        get_dashboard_performance(
            db,
            student_id=student_id,
        )

def test_activity_groups_sessions_by_student_local_date(
    db: Session,
) -> None:
    user = create_user(
        db,
        "activity-student@example.test",
        target_score=750,
        timezone_name="Asia/Ho_Chi_Minh",
    )

    # 17:30 UTC = 00:30 on November 21 in Vietnam.
    create_submitted_attempt(
        db,
        user_id=user.id,
        question_number=201,
        submitted_at=datetime(
            2026, 11, 20, 17, 30, tzinfo=timezone.utc
        ),
        is_correct=True,
    )

    # 18:30 UTC = 01:30 on November 21 in Vietnam.
    create_submitted_attempt(
        db,
        user_id=user.id,
        question_number=202,
        submitted_at=datetime(
            2026, 11, 20, 18, 30, tzinfo=timezone.utc
        ),
        is_correct=False,
    )

    # 17:30 UTC on November 21 = 00:30 on November 22.
    create_submitted_attempt(
        db,
        user_id=user.id,
        question_number=203,
        submitted_at=datetime(
            2026, 11, 21, 17, 30, tzinfo=timezone.utc
        ),
        is_correct=True,
    )

    db.commit()

    result = get_dashboard_activity(
        db,
        student_id=user.id,
        start_date=date(2026, 11, 20),
        end_date=date(2026, 11, 23),
    )

    assert len(result.days) == 4

    assert result.days[0].activity_date == date(2026, 11, 20)
    assert result.days[0].submitted_sessions == 0

    assert result.days[1].activity_date == date(2026, 11, 21)
    assert result.days[1].submitted_sessions == 2
    assert result.days[1].answered_questions == 2
    assert result.days[1].correct_answers == 1
    assert result.days[1].accuracy_percent == 50.0

    assert result.days[2].activity_date == date(2026, 11, 22)
    assert result.days[2].submitted_sessions == 1
    assert result.days[2].answered_questions == 1
    assert result.days[2].correct_answers == 1

    assert result.days[3].activity_date == date(2026, 11, 23)
    assert result.days[3].submitted_sessions == 0

    assert result.total_active_days == 2
    assert result.total_submitted_sessions == 3
    assert result.total_answered_questions == 3


def test_activity_does_not_include_another_students_sessions(
    db: Session,
) -> None:
    student_one = create_user(
        db,
        "activity-one@example.test",
    )
    student_two = create_user(
        db,
        "activity-two@example.test",
    )

    create_submitted_attempt(
        db,
        user_id=student_one.id,
        question_number=301,
        submitted_at=datetime(
            2026, 11, 20, 10, 0, tzinfo=timezone.utc
        ),
        is_correct=True,
    )

    db.commit()

    result = get_dashboard_activity(
        db,
        student_id=student_two.id,
        start_date=date(2026, 11, 20),
        end_date=date(2026, 11, 21),
    )

    assert result.total_active_days == 0
    assert result.total_submitted_sessions == 0
    assert result.total_answered_questions == 0
    assert len(result.days) == 2


def test_activity_rejects_reversed_date_range(
    db: Session,
) -> None:
    user = create_user(
        db,
        "invalid-range@example.test",
    )
    db.commit()

    with pytest.raises(ValueError):
        get_dashboard_activity(
            db,
            student_id=user.id,
            start_date=date(2026, 11, 22),
            end_date=date(2026, 11, 20),
        )


def test_activity_rejects_datetime_instead_of_date(
    db: Session,
) -> None:
    user = create_user(
        db,
        "invalid-date-type@example.test",
    )
    db.commit()

    with pytest.raises(ValueError):
        get_dashboard_activity(
            db,
            student_id=user.id,
            start_date=datetime(2026, 11, 20),
            end_date=date(2026, 11, 22),
        )


def test_activity_rejects_unknown_student(
    db: Session,
) -> None:
    with pytest.raises(DashboardStudentNotFoundError):
        get_dashboard_activity(
            db,
            student_id=999,
            start_date=date(2026, 11, 20),
            end_date=date(2026, 11, 22),
        )

def test_dashboard_skills_calculates_accuracy_and_weakness(
    db: Session,
) -> None:
    user = create_user(
        db,
        "skills-dashboard@example.test",
    )

    grammar = Skill(
        code="DASH_GRAMMAR",
        name="Grammar",
        category="grammar",
    )
    vocabulary = Skill(
        code="DASH_VOCAB",
        name="Vocabulary",
        category="vocabulary",
    )

    db.add_all([grammar, vocabulary])
    db.flush()

    submitted_at = datetime(
        2026, 11, 20, 10, 0, tzinfo=timezone.utc
    )

    for index, is_correct in enumerate(
        [False, True],
        start=1,
    ):
        quiz_session = create_submitted_attempt(
            db,
            user_id=user.id,
            question_number=400 + index,
            submitted_at=submitted_at,
            is_correct=is_correct,
        )
        attach_skill_to_session(
            db,
            quiz_session=quiz_session,
            skill=grammar,
        )

    for index in range(2):
        quiz_session = create_submitted_attempt(
            db,
            user_id=user.id,
            question_number=410 + index,
            submitted_at=submitted_at,
            is_correct=True,
        )
        attach_skill_to_session(
            db,
            quiz_session=quiz_session,
            skill=vocabulary,
        )

    db.commit()

    result = get_dashboard_skills(
        db,
        student_id=user.id,
    )

    assert result.total == 2

    grammar_result = next(
        item for item in result.items
        if item.skill_id == grammar.id
    )
    vocabulary_result = next(
        item for item in result.items
        if item.skill_id == vocabulary.id
    )

    assert grammar_result.attempt_count == 2
    assert grammar_result.correct_count == 1
    assert grammar_result.incorrect_count == 1
    assert grammar_result.accuracy_percent == 50.0
    assert grammar_result.is_weak is True

    assert vocabulary_result.attempt_count == 2
    assert vocabulary_result.correct_count == 2
    assert vocabulary_result.incorrect_count == 0
    assert vocabulary_result.accuracy_percent == 100.0
    assert vocabulary_result.is_weak is True

    assert result.items[0].skill_id == grammar.id


def test_dashboard_skills_ignores_retries(
    db: Session,
) -> None:
    user = create_user(
        db,
        "skills-retry@example.test",
    )

    skill = Skill(
        code="DASH_RETRY",
        name="Retry Skill",
        category="grammar",
    )
    db.add(skill)
    db.flush()

    quiz_session = create_submitted_attempt(
        db,
        user_id=user.id,
        question_number=420,
        submitted_at=datetime(
            2026, 11, 20, 10, 0, tzinfo=timezone.utc
        ),
        is_correct=True,
    )

    attach_skill_to_session(
        db,
        quiz_session=quiz_session,
        skill=skill,
    )

    quiz_item = (
        db.query(QuizItem)
        .filter(
            QuizItem.quiz_session_id == quiz_session.id
        )
        .one()
    )

    db.add(
        Attempt(
            user_id=user.id,
            quiz_item_id=quiz_item.id,
            attempt_number=2,
            selected_option_key="B",
            is_correct=False,
            is_retry=True,
            submitted_at=datetime(
                2026, 11, 20, 10, 5, tzinfo=timezone.utc
            ),
        )
    )

    db.commit()

    result = get_dashboard_skills(
        db,
        student_id=user.id,
    )

    assert result.total == 1
    assert result.items[0].attempt_count == 1
    assert result.items[0].correct_count == 1
    assert result.items[0].incorrect_count == 0
    assert result.items[0].is_weak is False


def test_dashboard_skills_prioritizes_weak_skills_over_insufficient_data(
    db: Session,
) -> None:
    user = create_user(
        db,
        "skills-priority@example.test",
    )

    insufficient = Skill(
        code="DASH_INSUFFICIENT",
        name="A Insufficient",
        category="grammar",
    )
    weak = Skill(
        code="DASH_WEAK",
        name="Z Weak",
        category="grammar",
    )

    db.add_all([insufficient, weak])
    db.flush()

    submitted_at = datetime(
        2026, 11, 20, 10, 0, tzinfo=timezone.utc
    )

    # One incorrect attempt: high error rate, but insufficient data.
    session_one = create_submitted_attempt(
        db,
        user_id=user.id,
        question_number=430,
        submitted_at=submitted_at,
        is_correct=False,
    )
    attach_skill_to_session(
        db,
        quiz_session=session_one,
        skill=insufficient,
    )

    # Two attempts, both incorrect: enough data to prioritize.
    for index in range(2):
        quiz_session = create_submitted_attempt(
            db,
            user_id=user.id,
            question_number=431 + index,
            submitted_at=submitted_at,
            is_correct=False,
        )
        attach_skill_to_session(
            db,
            quiz_session=quiz_session,
            skill=weak,
        )

    db.commit()

    result = get_dashboard_skills(
        db,
        student_id=user.id,
    )

    assert result.total == 2
    assert result.items[0].skill_id == weak.id
    assert result.items[0].is_weak is True
    assert result.items[1].skill_id == insufficient.id
    assert result.items[1].is_weak is False


def test_dashboard_skills_only_reads_current_student(
    db: Session,
) -> None:
    student_one = create_user(
        db,
        "skills-owner@example.test",
    )
    student_two = create_user(
        db,
        "skills-other@example.test",
    )

    skill = Skill(
        code="DASH_OWNER_ONLY",
        name="Owner Skill",
        category="grammar",
    )
    db.add(skill)
    db.flush()

    quiz_session = create_submitted_attempt(
        db,
        user_id=student_one.id,
        question_number=440,
        submitted_at=datetime(
            2026, 11, 20, 10, 0, tzinfo=timezone.utc
        ),
        is_correct=False,
    )

    attach_skill_to_session(
        db,
        quiz_session=quiz_session,
        skill=skill,
    )

    db.commit()

    result = get_dashboard_skills(
        db,
        student_id=student_two.id,
    )

    assert result.total == 0
    assert result.items == []

def test_dashboard_study_plan_returns_empty_result_without_active_plan(
    db: Session,
) -> None:
    user = create_user(
        db,
        "dashboard-no-plan@example.test",
    )
    db.commit()

    result = get_dashboard_study_plan(
        db,
        student_id=user.id,
        today=date(2026, 11, 21),
    )

    assert result.plan is None
    assert result.total_tasks == 0
    assert result.completed_tasks == 0
    assert result.pending_tasks == 0
    assert result.skipped_tasks == 0
    assert result.completion_percent == 0.0
    assert result.upcoming_tasks == []


def test_dashboard_study_plan_calculates_task_statistics(
    db: Session,
) -> None:
    user = create_user(
        db,
        "dashboard-plan-stats@example.test",
    )
    plan = create_study_plan(
        db,
        user_id=user.id,
    )

    create_study_plan_task(
        db,
        study_plan_id=plan.id,
        scheduled_date=date(2026, 11, 20),
        status="completed",
    )
    create_study_plan_task(
        db,
        study_plan_id=plan.id,
        scheduled_date=date(2026, 11, 21),
        status="completed",
    )
    create_study_plan_task(
        db,
        study_plan_id=plan.id,
        scheduled_date=date(2026, 11, 22),
        status="pending",
    )
    create_study_plan_task(
        db,
        study_plan_id=plan.id,
        scheduled_date=date(2026, 11, 23),
        status="pending",
    )
    create_study_plan_task(
        db,
        study_plan_id=plan.id,
        scheduled_date=date(2026, 11, 24),
        status="skipped",
    )

    db.commit()

    result = get_dashboard_study_plan(
        db,
        student_id=user.id,
        today=date(2026, 11, 21),
    )

    assert result.plan is not None
    assert result.plan.id == plan.id
    assert result.total_tasks == 5
    assert result.completed_tasks == 2
    assert result.pending_tasks == 2
    assert result.skipped_tasks == 1
    assert result.completion_percent == 40.0


def test_dashboard_study_plan_returns_only_upcoming_pending_tasks(
    db: Session,
) -> None:
    user = create_user(
        db,
        "dashboard-upcoming@example.test",
    )
    plan = create_study_plan(
        db,
        user_id=user.id,
    )

    today = date(2026, 11, 21)

    past_task = create_study_plan_task(
        db,
        study_plan_id=plan.id,
        scheduled_date=date(2026, 11, 20),
        status="pending",
    )

    completed_task = create_study_plan_task(
        db,
        study_plan_id=plan.id,
        scheduled_date=today,
        status="completed",
    )

    today_task = create_study_plan_task(
        db,
        study_plan_id=plan.id,
        scheduled_date=today,
        status="pending",
    )

    tomorrow_task = create_study_plan_task(
        db,
        study_plan_id=plan.id,
        scheduled_date=date(2026, 11, 22),
        status="pending",
    )

    db.commit()

    result = get_dashboard_study_plan(
        db,
        student_id=user.id,
        today=today,
    )

    upcoming_ids = [
        task.id for task in result.upcoming_tasks
    ]

    assert past_task.id not in upcoming_ids
    assert completed_task.id not in upcoming_ids
    assert today_task.id in upcoming_ids
    assert tomorrow_task.id in upcoming_ids

    assert upcoming_ids == [
        today_task.id,
        tomorrow_task.id,
    ]


def test_dashboard_study_plan_limits_upcoming_tasks_to_five(
    db: Session,
) -> None:
    user = create_user(
        db,
        "dashboard-limit@example.test",
    )
    plan = create_study_plan(
        db,
        user_id=user.id,
    )

    today = date(2026, 11, 21)

    created_tasks = []

    for index in range(7):
        task = create_study_plan_task(
            db,
            study_plan_id=plan.id,
            scheduled_date=date(
                2026,
                11,
                21 + index,
            ),
            status="pending",
        )
        created_tasks.append(task)

    db.commit()

    result = get_dashboard_study_plan(
        db,
        student_id=user.id,
        today=today,
    )

    assert len(result.upcoming_tasks) == 5

    assert [
        task.id for task in result.upcoming_tasks
    ] == [
        task.id for task in created_tasks[:5]
    ]


def test_dashboard_study_plan_includes_nested_skill_information(
    db: Session,
) -> None:
    user = create_user(
        db,
        "dashboard-task-skill@example.test",
    )

    skill = Skill(
        code="DASH_PLAN_GRAMMAR",
        name="Subject-Verb Agreement",
        category="grammar",
    )
    db.add(skill)
    db.flush()

    plan = create_study_plan(
        db,
        user_id=user.id,
    )

    task = create_study_plan_task(
        db,
        study_plan_id=plan.id,
        scheduled_date=date(2026, 11, 22),
        skill_id=skill.id,
    )

    db.commit()

    result = get_dashboard_study_plan(
        db,
        student_id=user.id,
        today=date(2026, 11, 21),
    )

    assert len(result.upcoming_tasks) == 1

    upcoming_task = result.upcoming_tasks[0]

    assert upcoming_task.id == task.id
    assert upcoming_task.skill is not None
    assert upcoming_task.skill.id == skill.id
    assert upcoming_task.skill.name == "Subject-Verb Agreement"


def test_dashboard_study_plan_does_not_read_another_students_plan(
    db: Session,
) -> None:
    student_one = create_user(
        db,
        "dashboard-plan-owner@example.test",
    )
    student_two = create_user(
        db,
        "dashboard-plan-other@example.test",
    )

    create_study_plan(
        db,
        user_id=student_one.id,
    )

    db.commit()

    result = get_dashboard_study_plan(
        db,
        student_id=student_two.id,
        today=date(2026, 11, 21),
    )

    assert result.plan is None
    assert result.total_tasks == 0
    assert result.upcoming_tasks == []


def test_dashboard_study_plan_does_not_modify_task_statuses(
    db: Session,
) -> None:
    user = create_user(
        db,
        "dashboard-read-only@example.test",
    )
    plan = create_study_plan(
        db,
        user_id=user.id,
    )

    task = create_study_plan_task(
        db,
        study_plan_id=plan.id,
        scheduled_date=date(2026, 11, 22),
        status="pending",
    )

    db.commit()

    result = get_dashboard_study_plan(
        db,
        student_id=user.id,
        today=date(2026, 11, 21),
    )

    db.refresh(task)

    assert result.total_tasks == 1
    assert task.status == "pending"
    assert task.completed_at is None