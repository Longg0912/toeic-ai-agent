
"""Tests for the personalized TOEIC study plan service."""

from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import backend.app.db.models  # noqa: F401
from backend.app.db.base import Base
from backend.app.db.models import (
    Attempt,
    Question,
    QuestionSkill,
    QuizItem,
    QuizSession,
    Skill,
    StudyPlan,
    StudyPlanTask,
    User,
)
from backend.app.services.study_plan_service import (
    ActiveStudyPlanExistsError,
    StudyPlanUserNotFoundError,
    StudyPlanValidationError,
    create_study_plan,
    get_prioritized_skill_ids,
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
    email: str = "student@example.test",
) -> User:
    """Create a test student."""

    user = User(
        email=email,
        password_hash="test-only-password-hash",
    )

    db.add(user)
    db.flush()

    return user


def create_first_attempt(
    db: Session,
    user_id: int,
    skill: Skill,
    question_number: int,
    correct: bool,
) -> None:
    """Create one question and its first attempt."""

    question = Question(
        part=5,
        content=f"Study plan question {question_number}",
        correct_option_key="A",
        content_hash=f"{question_number:064d}",
    )

    db.add(question)
    db.flush()

    db.add(
        QuestionSkill(
            question_id=question.id,
            skill_id=skill.id,
        )
    )

    quiz_session = QuizSession(
        user_id=user_id,
    )

    db.add(quiz_session)
    db.flush()

    quiz_item = QuizItem(
        quiz_session_id=quiz_session.id,
        question_id=question.id,
        position=1,
        question_snapshot={
            "content": question.content,
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
            selected_option_key="A" if correct else "B",
            is_correct=correct,
            is_retry=False,
        )
    )

    db.flush()


def create_plan(
    db: Session,
    student_id: int,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    daily_minutes: int = 30,
) -> StudyPlan:
    """Create a plan using standard test values."""

    start = start_date or date(2026, 11, 16)

    return create_study_plan(
        db,
        student_id=student_id,
        title="My TOEIC Study Plan",
        target_score=750,
        start_date=start,
        end_date=end_date or start + timedelta(days=6),
        daily_minutes=daily_minutes,
    )


def test_create_study_plan_success(
    db: Session,
) -> None:
    """A valid plan must be saved with its scheduled tasks."""

    user = create_user(db)

    plan = create_plan(
        db,
        user.id,
    )

    assert plan.id > 0
    assert plan.user_id == user.id
    assert plan.title == "My TOEIC Study Plan"
    assert plan.target_score == 750
    assert plan.daily_minutes == 30
    assert plan.status == "active"

    tasks = db.scalars(
        select(StudyPlanTask).where(
            StudyPlanTask.study_plan_id == plan.id
        )
    ).all()

    assert len(tasks) == 15


def test_daily_task_minutes_never_exceed_daily_limit(
    db: Session,
) -> None:
    """The total task duration must equal the daily limit."""

    user = create_user(db)

    plan = create_plan(
        db,
        user.id,
        daily_minutes=30,
    )

    tasks = db.scalars(
        select(StudyPlanTask)
        .where(
            StudyPlanTask.study_plan_id == plan.id
        )
    ).all()

    daily_totals: dict[date, int] = {}

    for task in tasks:
        daily_totals[task.scheduled_date] = (
            daily_totals.get(task.scheduled_date, 0)
            + task.estimated_minutes
        )

    assert len(daily_totals) == 7

    for total_minutes in daily_totals.values():
        assert total_minutes <= 30
        assert total_minutes == 30


def test_normal_day_has_practice_and_review(
    db: Session,
) -> None:
    """A normal day with sufficient time has two tasks."""

    user = create_user(db)

    plan = create_plan(db, user.id)

    tasks = db.scalars(
        select(StudyPlanTask)
        .where(
            StudyPlanTask.study_plan_id == plan.id,
            StudyPlanTask.scheduled_date == plan.start_date,
        )
        .order_by(StudyPlanTask.id)
    ).all()

    assert [task.task_type for task in tasks] == [
        "practice",
        "review",
    ]

    assert sum(
        task.estimated_minutes for task in tasks
    ) == 30


def test_seventh_day_contains_quiz_task(
    db: Session,
) -> None:
    """The seventh day must include a quiz task."""

    user = create_user(db)

    plan = create_plan(db, user.id)

    quiz_date = plan.start_date + timedelta(days=6)

    tasks = db.scalars(
        select(StudyPlanTask)
        .where(
            StudyPlanTask.study_plan_id == plan.id,
            StudyPlanTask.scheduled_date == quiz_date,
        )
        .order_by(StudyPlanTask.id)
    ).all()

    assert [task.task_type for task in tasks] == [
        "practice",
        "review",
        "quiz",
    ]

    assert sum(
        task.estimated_minutes for task in tasks
    ) == 30

    quiz_task = tasks[-1]

    assert quiz_task.skill_id is None


def test_two_minutes_per_day_creates_two_tasks(
    db: Session,
) -> None:
    """Two minutes must be divided into two positive durations."""

    user = create_user(db)

    plan = create_plan(
        db,
        user.id,
        end_date=date(2026, 11, 16),
        daily_minutes=2,
    )

    tasks = db.scalars(
        select(StudyPlanTask).where(
            StudyPlanTask.study_plan_id == plan.id
        )
    ).all()

    assert len(tasks) == 2

    assert all(
        task.estimated_minutes == 1
        for task in tasks
    )


def test_one_minute_per_day_creates_one_practice_task(
    db: Session,
) -> None:
    """One minute must produce one valid task."""

    user = create_user(db)

    plan = create_plan(
        db,
        user.id,
        end_date=date(2026, 11, 16),
        daily_minutes=1,
    )

    tasks = db.scalars(
        select(StudyPlanTask).where(
            StudyPlanTask.study_plan_id == plan.id
        )
    ).all()

    assert len(tasks) == 1
    assert tasks[0].task_type == "practice"
    assert tasks[0].estimated_minutes == 1
    assert tasks[0].target_question_count == 1


def test_weak_skills_are_prioritized(
    db: Session,
) -> None:
    """Skills with higher first-attempt error rates come first."""

    user = create_user(db)

    grammar = Skill(
        code="PLAN_GRAMMAR",
        name="Grammar",
        category="grammar",
    )

    vocabulary = Skill(
        code="PLAN_VOCAB",
        name="Vocabulary",
        category="vocabulary",
    )

    db.add_all([grammar, vocabulary])
    db.flush()

    # Grammar: 2 incorrect attempts out of 2.
    create_first_attempt(
        db, user.id, grammar, 101, False
    )
    create_first_attempt(
        db, user.id, grammar, 102, False
    )

    # Vocabulary: 1 incorrect attempt out of 2.
    create_first_attempt(
        db, user.id, vocabulary, 103, False
    )
    create_first_attempt(
        db, user.id, vocabulary, 104, True
    )

    db.commit()

    skill_ids = get_prioritized_skill_ids(
        db,
        user.id,
    )

    assert skill_ids[0] == grammar.id
    assert skill_ids[1] == vocabulary.id


def test_plan_uses_weak_skill_for_practice(
    db: Session,
) -> None:
    """The first practice task must use the weakest skill."""

    user = create_user(db)

    grammar = Skill(
        code="PLAN_WEAK_GRAMMAR",
        name="Weak Grammar",
        category="grammar",
    )

    vocabulary = Skill(
        code="PLAN_STRONG_VOCAB",
        name="Strong Vocabulary",
        category="vocabulary",
    )

    db.add_all([grammar, vocabulary])
    db.flush()

    create_first_attempt(db, user.id, grammar, 201, False)
    create_first_attempt(db, user.id, grammar, 202, False)

    create_first_attempt(db, user.id, vocabulary, 203, True)
    create_first_attempt(db, user.id, vocabulary, 204, True)

    db.commit()

    plan = create_plan(
        db,
        user.id,
        end_date=date(2026, 11, 16),
    )

    practice_task = db.scalar(
        select(StudyPlanTask).where(
            StudyPlanTask.study_plan_id == plan.id,
            StudyPlanTask.task_type == "practice",
        )
    )

    assert practice_task is not None
    assert practice_task.skill_id == grammar.id


def test_student_does_not_use_another_students_attempts(
    db: Session,
) -> None:
    """Weakness ranking must use only the requested student's data."""

    student_one = create_user(
        db,
        "one@example.test",
    )

    student_two = create_user(
        db,
        "two@example.test",
    )

    grammar = Skill(
        code="ISOLATED_GRAMMAR",
        name="Grammar",
        category="grammar",
    )

    vocabulary = Skill(
        code="ISOLATED_VOCAB",
        name="Vocabulary",
        category="vocabulary",
    )

    db.add_all([grammar, vocabulary])
    db.flush()

    # Student one has weak grammar.
    create_first_attempt(
        db, student_one.id, grammar, 301, False
    )
    create_first_attempt(
        db, student_one.id, grammar, 302, False
    )

    # Student two has weak vocabulary.
    create_first_attempt(
        db, student_two.id, vocabulary, 303, False
    )
    create_first_attempt(
        db, student_two.id, vocabulary, 304, False
    )

    db.commit()

    student_one_skills = get_prioritized_skill_ids(
        db,
        student_one.id,
    )

    student_two_skills = get_prioritized_skill_ids(
        db,
        student_two.id,
    )

    assert student_one_skills[0] == grammar.id
    assert student_two_skills[0] == vocabulary.id


def test_plan_works_without_skills(
    db: Session,
) -> None:
    """Tasks must still be generated if no skills exist."""

    user = create_user(db)

    plan = create_plan(
        db,
        user.id,
        end_date=date(2026, 11, 16),
    )

    tasks = db.scalars(
        select(StudyPlanTask).where(
            StudyPlanTask.study_plan_id == plan.id
        )
    ).all()

    assert len(tasks) == 2
    assert all(task.skill_id is None for task in tasks)


def test_second_active_plan_is_rejected(
    db: Session,
) -> None:
    """A student cannot have two active plans."""

    user = create_user(db)

    create_plan(db, user.id)

    with pytest.raises(ActiveStudyPlanExistsError):
        create_plan(
            db,
            user.id,
            start_date=date(2027, 1, 1),
            end_date=date(2027, 1, 7),
        )

    active_plans = db.scalars(
        select(StudyPlan).where(
            StudyPlan.user_id == user.id,
            StudyPlan.status == "active",
        )
    ).all()

    assert len(active_plans) == 1


def test_missing_student_is_rejected(
    db: Session,
) -> None:
    """A nonexistent student cannot create a plan."""

    with pytest.raises(StudyPlanUserNotFoundError):
        create_plan(db, 999999)


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": ""},
        {"title": "   "},
        {"title": "x" * 201},
        {"target_score": -1},
        {"target_score": 991},
        {"target_score": True},
        {"daily_minutes": 0},
        {"daily_minutes": -5},
        {"daily_minutes": True},
        {"end_date": date(2026, 11, 15)},
    ],
)
def test_invalid_plan_input_is_rejected(
    db: Session,
    overrides: dict,
) -> None:
    """Invalid plan fields must be rejected before persistence."""

    user = create_user(db)

    arguments = {
        "title": "Valid Plan",
        "target_score": 750,
        "start_date": date(2026, 11, 16),
        "end_date": date(2026, 11, 22),
        "daily_minutes": 30,
    }

    arguments.update(overrides)

    with pytest.raises(StudyPlanValidationError):
        create_study_plan(
            db,
            student_id=user.id,
            **arguments,
        )

    assert db.scalar(
        select(StudyPlan.id).where(
            StudyPlan.user_id == user.id
        )
    ) is None
