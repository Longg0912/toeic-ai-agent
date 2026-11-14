
"""Integration tests for Study Plan API endpoints."""

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from alembic import command
from alembic.config import Config

from backend.app.api.deps import get_db

from backend.app.db.session import make_engine
from backend.app.main import app
from backend.app.security.jwt_tokens import (
    JWTSettings,
    create_access_token,
)
from backend.app.db.models import (
    Skill,
    StudyPlan,
    StudyPlanTask,
    User,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = PROJECT_ROOT / "alembic.ini"

TEST_SECRET = "test-secret-key-that-is-at-least-32-bytes-long"


@pytest.fixture
def study_plan_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, Engine, dict[str, dict[str, str]]]]:
    """Create an isolated database and authenticated users."""

    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET)

    database_path = tmp_path / "study_plans.sqlite3"
    database_url = (
        f"sqlite+pysqlite:///{database_path.as_posix()}"
    )
    test_engine = make_engine(database_url)

    config = Config(str(ALEMBIC_CONFIG))
    previous_overrides = app.dependency_overrides.copy()

    try:
        # Apply real migrations to the temporary database.
        with test_engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        with Session(test_engine) as session:
            student_1 = User(
                email="study-plan-student-1@example.com",
                password_hash="test-only-hash",
                role="student",
                is_active=True,
            )
            student_2 = User(
                email="study-plan-student-2@example.com",
                password_hash="test-only-hash",
                role="student",
                is_active=True,
            )
            admin = User(
                email="study-plan-admin@example.com",
                password_hash="test-only-hash",
                role="admin",
                is_active=True,
            )

            session.add_all([student_1, student_2, admin])
            session.flush()

            session.add_all(
                [
                    Skill(
                        code="TEST_STUDY_GRAMMAR",
                        name="Test Grammar",
                        category="grammar",
                    ),
                    Skill(
                        code="TEST_STUDY_VOCABULARY",
                        name="Test Vocabulary",
                        category="vocabulary",
                    ),
                ]
            )
            session.commit()

            user_ids = {
                "student_1": student_1.id,
                "student_2": student_2.id,
                "admin": admin.id,
            }

        headers: dict[str, dict[str, str]] = {}

        for role, user_id in user_ids.items():
            token = create_access_token(
                user_id,
                settings=JWTSettings(secret_key=TEST_SECRET),
            )
            headers[role] = {
                "Authorization": f"Bearer {token}",
            }

        def override_get_db() -> Iterator[Session]:
            with Session(test_engine) as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as client:
            yield client, test_engine, headers

    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        test_engine.dispose()


def valid_plan_payload() -> dict:
    """Return a valid study plan request body."""

    return {
        "title": "TOEIC 700 Preparation",
        "target_score": 700,
        "start_date": "2026-11-15",
        "end_date": "2026-11-21",
        "daily_minutes": 60,
    }


def test_create_study_plan_success(
    study_plan_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
) -> None:
    """A student can create a study plan."""

    client, engine, headers = study_plan_client

    response = client.post(
        "/study-plans",
        json=valid_plan_payload(),
        headers=headers["student_1"],
    )

    assert response.status_code == 201

    data = response.json()

    assert data["title"] == "TOEIC 700 Preparation"
    assert data["target_score"] == 700
    assert data["start_date"] == "2026-11-15"
    assert data["end_date"] == "2026-11-21"
    assert data["daily_minutes"] == 60
    assert data["status"] == "active"
    assert data["id"] > 0

    with Session(engine) as session:
        saved_plan = session.get(StudyPlan, data["id"])

        assert saved_plan is not None
        assert saved_plan.user_id > 0
        assert saved_plan.status == "active"

        # The plan service should generate scheduled tasks.
        assert len(saved_plan.tasks) > 0


def test_create_study_plan_requires_authentication(
    study_plan_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
) -> None:
    """Unauthenticated users cannot create study plans."""

    client, engine, _ = study_plan_client

    response = client.post(
        "/study-plans",
        json=valid_plan_payload(),
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"

    with Session(engine) as session:
        plans = session.scalars(select(StudyPlan)).all()
        assert plans == []


def test_admin_cannot_create_study_plan(
    study_plan_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
) -> None:
    """Only student accounts can create study plans."""

    client, engine, headers = study_plan_client

    response = client.post(
        "/study-plans",
        json=valid_plan_payload(),
        headers=headers["admin"],
    )

    assert response.status_code == 403

    with Session(engine) as session:
        plans = session.scalars(select(StudyPlan)).all()
        assert plans == []


def test_duplicate_active_study_plan_returns_conflict(
    study_plan_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
) -> None:
    """A student cannot create a second active study plan."""

    client, _, headers = study_plan_client

    first_response = client.post(
        "/study-plans",
        json=valid_plan_payload(),
        headers=headers["student_1"],
    )

    assert first_response.status_code == 201

    second_payload = valid_plan_payload()
    second_payload["title"] = "Another TOEIC Plan"

    second_response = client.post(
        "/study-plans",
        json=second_payload,
        headers=headers["student_1"],
    )

    assert second_response.status_code == 409
    assert second_response.json()["detail"] == (
        "An active study plan already exists."
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": ""},
        {"title": "x" * 201},
        {"target_score": -1},
        {"target_score": 991},
        {"daily_minutes": 0},
        {"daily_minutes": -10},
        {
            "start_date": "2026-11-22",
            "end_date": "2026-11-21",
        },
        {"unexpected_field": "not allowed"},
    ],
)
def test_invalid_study_plan_payload_is_rejected(
    study_plan_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
    overrides: dict,
) -> None:
    """Invalid request data returns HTTP 422."""

    client, _, headers = study_plan_client

    payload = valid_plan_payload()
    payload.update(overrides)

    response = client.post(
        "/study-plans",
        json=payload,
        headers=headers["student_1"],
    )

    assert response.status_code == 422


def test_list_study_plans_returns_only_current_student_plans(
    study_plan_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
) -> None:
    """A student can only see their own study plans."""

    client, engine, headers = study_plan_client

    # Each student creates an independent active plan.
    response_1 = client.post(
        "/study-plans",
        json=valid_plan_payload(),
        headers=headers["student_1"],
    )
    response_2 = client.post(
        "/study-plans",
        json=valid_plan_payload(),
        headers=headers["student_2"],
    )

    assert response_1.status_code == 201
    assert response_2.status_code == 201

    plan_1_id = response_1.json()["id"]
    plan_2_id = response_2.json()["id"]

    list_1 = client.get(
        "/study-plans",
        headers=headers["student_1"],
    )
    list_2 = client.get(
        "/study-plans",
        headers=headers["student_2"],
    )

    assert list_1.status_code == 200
    assert list_2.status_code == 200

    data_1 = list_1.json()
    data_2 = list_2.json()

    assert data_1["total"] == 1
    assert data_2["total"] == 1

    assert [item["id"] for item in data_1["items"]] == [
        plan_1_id
    ]
    assert [item["id"] for item in data_2["items"]] == [
        plan_2_id
    ]

    assert plan_2_id not in [
        item["id"] for item in data_1["items"]
    ]
    assert plan_1_id not in [
        item["id"] for item in data_2["items"]
    ]

    with Session(engine) as session:
        saved_plans = session.scalars(
            select(StudyPlan).order_by(StudyPlan.id)
        ).all()

        assert len(saved_plans) == 2
        assert saved_plans[0].user_id != saved_plans[1].user_id


def test_list_study_plans_requires_authentication(
    study_plan_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
) -> None:
    """Unauthenticated users cannot list study plans."""

    client, _, _ = study_plan_client

    response = client.get("/study-plans")

    assert response.status_code == 401


def test_list_study_plans_supports_pagination(
    study_plan_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
) -> None:
    """List endpoint returns pagination metadata."""

    client, _, headers = study_plan_client

    response = client.get(
        "/study-plans?limit=10&offset=0",
        headers=headers["student_1"],
    )

    assert response.status_code == 200

    data = response.json()

    assert data["items"] == []
    assert data["total"] == 0
    assert data["limit"] == 10
    assert data["offset"] == 0


@pytest.mark.parametrize(
    "query",
    [
        "?limit=0",
        "?limit=101",
        "?offset=-1",
    ],
)
def test_invalid_pagination_parameters_are_rejected(
    study_plan_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
    query: str,
) -> None:
    """Invalid pagination parameters return HTTP 422."""

    client, _, headers = study_plan_client

    response = client.get(
        f"/study-plans{query}",
        headers=headers["student_1"],
    )

    assert response.status_code == 422


def test_get_study_plan_detail_returns_plan_and_tasks(
    study_plan_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
) -> None:
    """The owner can retrieve plan details and scheduled tasks."""

    client, _, headers = study_plan_client

    create_response = client.post(
        "/study-plans",
        json=valid_plan_payload(),
        headers=headers["student_1"],
    )

    assert create_response.status_code == 201

    plan_id = create_response.json()["id"]

    response = client.get(
        f"/study-plans/{plan_id}",
        headers=headers["student_1"],
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == plan_id
    assert data["title"] == "TOEIC 700 Preparation"
    assert data["target_score"] == 700
    assert data["status"] == "active"

    # Seven days: 2 tasks on normal days and 3 on quiz day.
    assert len(data["tasks"]) == 15

    task_dates = [
        (task["scheduled_date"], task["id"])
        for task in data["tasks"]
    ]

    assert task_dates == sorted(task_dates)

    # Tasks with a skill must include its public information.
    skill_tasks = [
        task
        for task in data["tasks"]
        if task["skill_id"] is not None
    ]

    assert skill_tasks

    for task in skill_tasks:
        assert task["skill"] is not None
        assert task["skill"]["id"] == task["skill_id"]
        assert task["skill"]["code"]
        assert task["skill"]["name"]
        assert task["skill"]["category"]

    # Quiz tasks do not have an assigned skill.
    quiz_tasks = [
        task
        for task in data["tasks"]
        if task["task_type"] == "quiz"
    ]

    assert quiz_tasks

    for task in quiz_tasks:
        assert task["skill_id"] is None
        assert task["skill"] is None


def test_get_study_plan_detail_returns_404_for_missing_plan(
    study_plan_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
) -> None:
    """A nonexistent study plan returns HTTP 404."""

    client, _, headers = study_plan_client

    response = client.get(
        "/study-plans/999999",
        headers=headers["student_1"],
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Study plan not found."


def test_student_cannot_get_another_students_study_plan(
    study_plan_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
) -> None:
    """A student cannot access another student's plan."""

    client, _, headers = study_plan_client

    create_response = client.post(
        "/study-plans",
        json=valid_plan_payload(),
        headers=headers["student_1"],
    )

    assert create_response.status_code == 201

    plan_id = create_response.json()["id"]

    response = client.get(
        f"/study-plans/{plan_id}",
        headers=headers["student_2"],
    )

    # Do not reveal whether another student's plan exists.
    assert response.status_code == 404
    assert response.json()["detail"] == "Study plan not found."


def test_get_study_plan_detail_requires_authentication(
    study_plan_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
) -> None:
    """Unauthenticated users cannot access study plan details."""

    client, _, _ = study_plan_client

    response = client.get("/study-plans/1")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_admin_cannot_get_study_plan_detail(
    study_plan_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
) -> None:
    """Only student accounts can access study plan details."""

    client, _, headers = study_plan_client

    response = client.get(
        "/study-plans/1",
        headers=headers["admin"],
    )

    assert response.status_code == 403


def _create_plan_for_lifecycle_test(
    client: TestClient,
    headers: dict[str, str],
) -> int:
    """Create a plan and return its ID."""

    response = client.post(
        "/study-plans",
        json=valid_plan_payload(),
        headers=headers,
    )

    assert response.status_code == 201

    return response.json()["id"]


def _get_task_snapshot(
    engine: Engine,
    plan_id: int,
) -> list[tuple]:
    """Return task fields to verify lifecycle operations preserve them."""

    with Session(engine) as session:
        tasks = session.scalars(
            select(StudyPlanTask)
            .where(StudyPlanTask.study_plan_id == plan_id)
            .order_by(StudyPlanTask.id)
        ).all()

        return [
            (
                task.id,
                task.skill_id,
                task.task_type,
                task.scheduled_date,
                task.estimated_minutes,
                task.target_question_count,
                task.status,
                task.completed_at,
            )
            for task in tasks
        ]


def test_pause_study_plan_success_and_preserves_tasks(
    study_plan_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
) -> None:
    """Pausing a plan changes its status but preserves all tasks."""

    client, engine, headers = study_plan_client

    plan_id = _create_plan_for_lifecycle_test(
        client,
        headers["student_1"],
    )

    tasks_before = _get_task_snapshot(engine, plan_id)

    response = client.post(
        f"/study-plans/{plan_id}/pause",
        headers=headers["student_1"],
    )

    assert response.status_code == 200
    assert response.json()["id"] == plan_id
    assert response.json()["status"] == "paused"

    assert _get_task_snapshot(engine, plan_id) == tasks_before


def test_pause_study_plan_rejects_non_active_plan(
    study_plan_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
) -> None:
    """A paused plan cannot be paused again."""

    client, _, headers = study_plan_client

    plan_id = _create_plan_for_lifecycle_test(
        client,
        headers["student_1"],
    )

    first_response = client.post(
        f"/study-plans/{plan_id}/pause",
        headers=headers["student_1"],
    )

    assert first_response.status_code == 200

    second_response = client.post(
        f"/study-plans/{plan_id}/pause",
        headers=headers["student_1"],
    )

    assert second_response.status_code == 409


def test_resume_study_plan_success_and_preserves_tasks(
    study_plan_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
) -> None:
    """A paused plan can be resumed without modifying its tasks."""

    client, engine, headers = study_plan_client

    plan_id = _create_plan_for_lifecycle_test(
        client,
        headers["student_1"],
    )

    pause_response = client.post(
        f"/study-plans/{plan_id}/pause",
        headers=headers["student_1"],
    )

    assert pause_response.status_code == 200

    tasks_before = _get_task_snapshot(engine, plan_id)

    response = client.post(
        f"/study-plans/{plan_id}/resume",
        headers=headers["student_1"],
    )

    assert response.status_code == 200
    assert response.json()["status"] == "active"

    assert _get_task_snapshot(engine, plan_id) == tasks_before


def test_resume_study_plan_rejects_active_plan(
    study_plan_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
) -> None:
    """An already active plan cannot be resumed."""

    client, _, headers = study_plan_client

    plan_id = _create_plan_for_lifecycle_test(
        client,
        headers["student_1"],
    )

    response = client.post(
        f"/study-plans/{plan_id}/resume",
        headers=headers["student_1"],
    )

    assert response.status_code == 409


def test_resume_study_plan_rejects_when_another_plan_is_active(
    study_plan_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
) -> None:
    """A student cannot resume a plan while another plan is active."""

    client, _, headers = study_plan_client

    paused_plan_id = _create_plan_for_lifecycle_test(
        client,
        headers["student_1"],
    )

    pause_response = client.post(
        f"/study-plans/{paused_plan_id}/pause",
        headers=headers["student_1"],
    )

    assert pause_response.status_code == 200

    active_plan_id = _create_plan_for_lifecycle_test(
        client,
        headers["student_1"],
    )

    response = client.post(
        f"/study-plans/{paused_plan_id}/resume",
        headers=headers["student_1"],
    )

    assert response.status_code == 409

    # The existing active plan must remain active.
    detail_response = client.get(
        f"/study-plans/{active_plan_id}",
        headers=headers["student_1"],
    )

    assert detail_response.status_code == 200
    assert detail_response.json()["status"] == "active"


def test_complete_study_plan_success_and_preserves_tasks(
    study_plan_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
) -> None:
    """Completing a plan changes its status but preserves all tasks."""

    client, engine, headers = study_plan_client

    plan_id = _create_plan_for_lifecycle_test(
        client,
        headers["student_1"],
    )

    tasks_before = _get_task_snapshot(engine, plan_id)

    response = client.post(
        f"/study-plans/{plan_id}/complete",
        headers=headers["student_1"],
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"

    assert _get_task_snapshot(engine, plan_id) == tasks_before


def test_complete_study_plan_rejects_paused_plan(
    study_plan_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
) -> None:
    """A paused plan cannot be completed through this endpoint."""

    client, _, headers = study_plan_client

    plan_id = _create_plan_for_lifecycle_test(
        client,
        headers["student_1"],
    )

    pause_response = client.post(
        f"/study-plans/{plan_id}/pause",
        headers=headers["student_1"],
    )

    assert pause_response.status_code == 200

    response = client.post(
        f"/study-plans/{plan_id}/complete",
        headers=headers["student_1"],
    )

    assert response.status_code == 409


@pytest.mark.parametrize(
    "action",
    ["pause", "resume", "complete"],
)
def test_lifecycle_endpoint_returns_404_for_missing_plan(
    study_plan_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
    action: str,
) -> None:
    """Lifecycle endpoints return 404 for nonexistent plans."""

    client, _, headers = study_plan_client

    response = client.post(
        f"/study-plans/999999/{action}",
        headers=headers["student_1"],
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Study plan not found."


@pytest.mark.parametrize(
    "action",
    ["pause", "resume", "complete"],
)
def test_student_cannot_change_another_students_plan(
    study_plan_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
    action: str,
) -> None:
    """A student cannot change another student's study plan."""

    client, _, headers = study_plan_client

    plan_id = _create_plan_for_lifecycle_test(
        client,
        headers["student_1"],
    )

    response = client.post(
        f"/study-plans/{plan_id}/{action}",
        headers=headers["student_2"],
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Study plan not found."

    # The owner's plan must remain active.
    detail_response = client.get(
        f"/study-plans/{plan_id}",
        headers=headers["student_1"],
    )

    assert detail_response.status_code == 200
    assert detail_response.json()["status"] == "active"
