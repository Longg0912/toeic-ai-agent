
"""Tests for the adaptive TOEIC study planner service."""

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
from backend.app.services.study_plan_service import create_study_plan
from backend.app.services.adaptive_planner_service import (
    AdaptivePlanNotActiveError,
    AdaptivePlanNotFoundError,
    AdaptivePlannerValidationError,
    adapt_study_plan,
    get_weak_skill_ids,
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
) -> QuizItem:
    """Create one question and its first attempt."""

    question = Question(
        part=5,
        content=f"Adaptive question {question_number}",
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

    return quiz_item


def create_plan(
    db: Session,
    student_id: int,
    *,
    status: str = "active",
) -> StudyPlan:
    """Create a standard seven-day study plan."""

    plan = create_study_plan(
        db,
        student_id=student_id,
        title="Adaptive TOEIC Plan",
        target_score=750,
        start_date=date(2026, 11, 16),
        end_date=date(2026, 11, 22),
        daily_minutes=30,
    )

    if status != "active":
        plan.status = status
        db.flush()

    return plan


def create_weak_skills(
    db: Session,
    user_id: int,
) -> tuple[Skill, Skill]:
    """Create two skills with different first-attempt error rates."""

    grammar = Skill(
        code="ADAPT_GRAMMAR",
        name="Grammar",
        category="grammar",
    )

    vocabulary = Skill(
        code="ADAPT_VOCAB",
        name="Vocabulary",
        category="vocabulary",
    )

    db.add_all([grammar, vocabulary])
    db.flush()

    # Grammar: 2 incorrect out of 2 first attempts.
    create_first_attempt(db, user_id, grammar, 1001, False)
    create_first_attempt(db, user_id, grammar, 1002, False)

    # Vocabulary: 1 incorrect out of 2 first attempts.
    create_first_attempt(db, user_id, vocabulary, 1003, False)
    create_first_attempt(db, user_id, vocabulary, 1004, True)

    db.flush()

    return grammar, vocabulary


def get_plan_tasks(
    db: Session,
    plan_id: int,
) -> list[StudyPlanTask]:
    """Return all plan tasks in deterministic order."""

    return list(
        db.scalars(
            select(StudyPlanTask)
            .where(
                StudyPlanTask.study_plan_id == plan_id,
            )
            .order_by(
                StudyPlanTask.scheduled_date.asc(),
                StudyPlanTask.id.asc(),
            )
        ).all()
    )


def test_get_weak_skill_ids_ranks_high_error_rate_first(
    db: Session,
) -> None:
    """Skills with higher first-attempt error rates come first."""

    user = create_user(db)
    grammar, vocabulary = create_weak_skills(
        db,
        user.id,
    )

    db.commit()

    skill_ids = get_weak_skill_ids(
        db,
        user.id,
    )

    assert skill_ids == [
        grammar.id,
        vocabulary.id,
    ]


def test_get_weak_skill_ids_ignores_retry_attempts(
    db: Session,
) -> None:
    """Retry attempts must not affect the weakness ranking."""

    user = create_user(db)

    grammar = Skill(
        code="ADAPT_RETRY_GRAMMAR",
        name="Grammar",
        category="grammar",
    )

    vocabulary = Skill(
        code="ADAPT_RETRY_VOCAB",
        name="Vocabulary",
        category="vocabulary",
    )

    db.add_all([grammar, vocabulary])
    db.flush()

    # Grammar first attempts: 1 incorrect, 1 correct.
    grammar_item_one = create_first_attempt(
        db, user.id, grammar, 1101, False
    )
    create_first_attempt(
        db, user.id, grammar, 1102, True
    )

    # Vocabulary first attempts: 2 incorrect.
    create_first_attempt(
        db, user.id, vocabulary, 1103, False
    )
    create_first_attempt(
        db, user.id, vocabulary, 1104, False
    )

    # Add a correct retry to the incorrect Grammar question.
    db.add(
        Attempt(
            user_id=user.id,
            quiz_item_id=grammar_item_one.id,
            attempt_number=2,
            selected_option_key="A",
            is_correct=True,
            is_retry=True,
        )
    )

    db.commit()

    skill_ids = get_weak_skill_ids(
        db,
        user.id,
    )

    assert skill_ids == [
        vocabulary.id,
        grammar.id,
    ]


def test_get_weak_skill_ids_requires_two_first_attempts(
    db: Session,
) -> None:
    """A skill with only one first attempt is not classified as weak."""

    user = create_user(db)

    skill = Skill(
        code="ADAPT_LOW_DATA",
        name="Low data skill",
        category="grammar",
    )

    db.add(skill)
    db.flush()

    create_first_attempt(
        db,
        user.id,
        skill,
        1201,
        False,
    )

    db.commit()

    assert get_weak_skill_ids(db, user.id) == []


def test_get_weak_skill_ids_does_not_read_another_student(
    db: Session,
) -> None:
    """Only the requested student's attempts are considered."""

    student_one = create_user(
        db,
        "one@example.test",
    )

    student_two = create_user(
        db,
        "two@example.test",
    )

    skill = Skill(
        code="ADAPT_PRIVATE",
        name="Private skill",
        category="grammar",
    )

    db.add(skill)
    db.flush()

    create_first_attempt(
        db, student_one.id, skill, 1301, False
    )
    create_first_attempt(
        db, student_one.id, skill, 1302, False
    )

    db.commit()

    assert get_weak_skill_ids(
        db,
        student_two.id,
    ) == []




def test_adapt_study_plan_assigns_weak_skills_in_priority_order(
    db: Session,
) -> None:
    """Future pending practice/review tasks receive prioritized weak skills."""

    user = create_user(db)
    grammar, vocabulary = create_weak_skills(
        db,
        user.id,
    )

    plan = create_plan(db, user.id)
    db.commit()

    today = date(2026, 11, 14)

    eligible_tasks_before = [
        task
        for task in get_plan_tasks(db, plan.id)
        if (
            task.task_type in {"practice", "review"}
            and task.status == "pending"
            and task.scheduled_date > today
        )
    ]

    original_skill_ids = {
        task.id: task.skill_id
        for task in eligible_tasks_before
    }

    result = adapt_study_plan(
        db,
        student_id=user.id,
        plan_id=plan.id,
        today=today,
    )

    tasks = [
        task
        for task in get_plan_tasks(db, plan.id)
        if (
            task.task_type in {"practice", "review"}
            and task.status == "pending"
            and task.scheduled_date > today
        )
    ]

    assert result.plan_id == plan.id
    assert result.prioritized_skill_ids == (
        grammar.id,
        vocabulary.id,
    )

    expected_skill_ids = [
        grammar.id if index % 2 == 0 else vocabulary.id
        for index in range(len(tasks))
    ]

    assert [
        task.skill_id for task in tasks
    ] == expected_skill_ids

    expected_updated_count = sum(
        original_skill_ids[task.id] != task.skill_id
        for task in tasks
    )

    assert result.updated_task_count == expected_updated_count




def test_adapt_study_plan_only_updates_future_pending_tasks(
    db: Session,
) -> None:
    """Past, current-day, completed, and skipped tasks remain unchanged."""

    user = create_user(db)
    grammar, _ = create_weak_skills(db, user.id)

    plan = create_plan(db, user.id)
    tasks = get_plan_tasks(db, plan.id)

    practice_tasks = [
        task for task in tasks
        if task.task_type == "practice"
    ]

    past_task = practice_tasks[0]
    current_task = practice_tasks[1]
    completed_task = practice_tasks[2]
    skipped_task = practice_tasks[3]

    past_task.scheduled_date = date(2026, 11, 13)
    current_task.scheduled_date = date(2026, 11, 14)
    completed_task.status = "completed"
    skipped_task.status = "skipped"

    original_values = {
        task.id: (
            task.skill_id,
            task.estimated_minutes,
            task.target_question_count,
            task.status,
            task.scheduled_date,
        )
        for task in [
            past_task,
            current_task,
            completed_task,
            skipped_task,
        ]
    }

    db.commit()

    result = adapt_study_plan(
        db,
        student_id=user.id,
        plan_id=plan.id,
        today=date(2026, 11, 14),
    )

    db.refresh(past_task)
    db.refresh(current_task)
    db.refresh(completed_task)
    db.refresh(skipped_task)

    assert result.updated_task_count > 0

    for task in [
        past_task,
        current_task,
        completed_task,
        skipped_task,
    ]:
        assert (
            task.skill_id,
            task.estimated_minutes,
            task.target_question_count,
            task.status,
            task.scheduled_date,
        ) == original_values[task.id]

    # At least one eligible future task receives the weak skill.
    future_pending_practice = [
        task
        for task in get_plan_tasks(db, plan.id)
        if (
            task.task_type == "practice"
            and task.status == "pending"
            and task.scheduled_date > date(2026, 11, 14)
        )
    ]

    assert any(
        task.skill_id == grammar.id
        for task in future_pending_practice
    )


def test_adapt_study_plan_does_not_modify_quiz_tasks(
    db: Session,
) -> None:
    """Quiz tasks are never reassigned to a skill."""

    user = create_user(db)
    create_weak_skills(db, user.id)

    plan = create_plan(db, user.id)
    db.commit()

    quiz_tasks_before = [
        (
            task.id,
            task.skill_id,
            task.status,
            task.estimated_minutes,
            task.target_question_count,
        )
        for task in get_plan_tasks(db, plan.id)
        if task.task_type == "quiz"
    ]

    adapt_study_plan(
        db,
        student_id=user.id,
        plan_id=plan.id,
        today=date(2026, 11, 14),
    )

    quiz_tasks_after = [
        (
            task.id,
            task.skill_id,
            task.status,
            task.estimated_minutes,
            task.target_question_count,
        )
        for task in get_plan_tasks(db, plan.id)
        if task.task_type == "quiz"
    ]

    assert quiz_tasks_after == quiz_tasks_before


def test_adapt_study_plan_preserves_task_duration_and_question_count(
    db: Session,
) -> None:
    """Adapting a task must not change its workload."""

    user = create_user(db)
    create_weak_skills(db, user.id)

    plan = create_plan(db, user.id)
    db.commit()

    before = {
        task.id: (
            task.estimated_minutes,
            task.target_question_count,
        )
        for task in get_plan_tasks(db, plan.id)
    }

    adapt_study_plan(
        db,
        student_id=user.id,
        plan_id=plan.id,
        today=date(2026, 11, 14),
    )

    after = {
        task.id: (
            task.estimated_minutes,
            task.target_question_count,
        )
        for task in get_plan_tasks(db, plan.id)
    }

    assert after == before


def test_adapt_study_plan_keeps_schedule_when_no_weak_skills(
    db: Session,
) -> None:
    """No reliable weakness data means no task changes."""

    user = create_user(db)
    plan = create_plan(db, user.id)
    db.commit()

    before = [
        (
            task.id,
            task.skill_id,
            task.status,
            task.scheduled_date,
        )
        for task in get_plan_tasks(db, plan.id)
    ]

    result = adapt_study_plan(
        db,
        student_id=user.id,
        plan_id=plan.id,
        today=date(2026, 11, 14),
    )

    after = [
        (
            task.id,
            task.skill_id,
            task.status,
            task.scheduled_date,
        )
        for task in get_plan_tasks(db, plan.id)
    ]

    assert result.updated_task_count == 0
    assert result.prioritized_skill_ids == ()
    assert after == before


def test_adapt_study_plan_rejects_plan_owned_by_another_student(
    db: Session,
) -> None:
    """A student cannot adapt another student's plan."""

    owner = create_user(
        db,
        "owner@example.test",
    )

    another_student = create_user(
        db,
        "another@example.test",
    )

    plan = create_plan(db, owner.id)
    db.commit()

    with pytest.raises(AdaptivePlanNotFoundError):
        adapt_study_plan(
            db,
            student_id=another_student.id,
            plan_id=plan.id,
            today=date(2026, 11, 14),
        )


def test_adapt_study_plan_rejects_missing_plan(
    db: Session,
) -> None:
    """A nonexistent plan must be rejected."""

    user = create_user(db)

    with pytest.raises(AdaptivePlanNotFoundError):
        adapt_study_plan(
            db,
            student_id=user.id,
            plan_id=999999,
            today=date(2026, 11, 14),
        )


def test_adapt_study_plan_rejects_inactive_plan(
    db: Session,
) -> None:
    """Only active plans can be adapted."""

    user = create_user(db)
    plan = create_plan(
        db,
        user.id,
        status="paused",
    )
    db.commit()

    with pytest.raises(AdaptivePlanNotActiveError):
        adapt_study_plan(
            db,
            student_id=user.id,
            plan_id=plan.id,
            today=date(2026, 11, 14),
        )


@pytest.mark.parametrize(
    ("student_id", "plan_id", "today"),
    [
        (True, 1, date(2026, 11, 14)),
        (0, 1, date(2026, 11, 14)),
        (1, True, date(2026, 11, 14)),
        (1, 0, date(2026, 11, 14)),
        (1, 1, "2026-11-14"),
    ],
)
def test_adapt_study_plan_rejects_invalid_input(
    db: Session,
    student_id: int,
    plan_id: int,
    today: date,
) -> None:
    """Invalid identifiers and dates must be rejected."""

    with pytest.raises(AdaptivePlannerValidationError):
        adapt_study_plan(
            db,
            student_id=student_id,
            plan_id=plan_id,
            today=today,
        )
