"""Integration tests for authenticated dashboard API endpoints."""

from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.db.models import StudyPlan, User
from backend.app.db.session import make_engine
from backend.app.main import app
from backend.app.security.jwt_tokens import (
    JWTSettings,
    create_access_token,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = PROJECT_ROOT / "alembic.ini"

TEST_SECRET = "test-dashboard-secret-key-at-least-32-bytes"


@pytest.fixture
def dashboard_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[
    tuple[TestClient, Engine, dict[str, dict[str, str]]]
]:
    """Create an isolated dashboard API and temporary database."""

    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET)

    database_path = tmp_path / "dashboard_test.sqlite3"

    database_url = (
        f"sqlite+pysqlite:///{database_path.as_posix()}"
    )

    test_engine = make_engine(database_url)

    config = Config(str(ALEMBIC_CONFIG))
    previous_overrides = app.dependency_overrides.copy()

    try:
        # Apply the real project migrations.
        with test_engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        # Create test users.
        with Session(test_engine) as session:
            student_one = User(
                email="dashboard-student-1@example.com",
                password_hash="test-only-hash",
                role="student",
                is_active=True,
            )

            student_two = User(
                email="dashboard-student-2@example.com",
                password_hash="test-only-hash",
                role="student",
                is_active=True,
            )

            admin = User(
                email="dashboard-admin@example.com",
                password_hash="test-only-hash",
                role="admin",
                is_active=True,
            )

            session.add_all(
                [
                    student_one,
                    student_two,
                    admin,
                ]
            )
            session.commit()

            user_ids = {
                "student_1": student_one.id,
                "student_2": student_two.id,
                "admin": admin.id,
            }

        # Generate test-only JWTs.
        jwt_settings = JWTSettings(
            secret_key=TEST_SECRET,
        )

        headers: dict[str, dict[str, str]] = {}

        for role, user_id in user_ids.items():
            token = create_access_token(
                user_id,
                settings=jwt_settings,
            )

            headers[role] = {
                "Authorization": f"Bearer {token}",
            }

        # Redirect database access to temporary SQLite.
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


def test_dashboard_endpoints_return_empty_data_for_new_student(
    dashboard_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
) -> None:
    """All dashboard endpoints work for a student without learning data."""

    client, _, headers = dashboard_client

    student_headers = headers["student_1"]

    overview = client.get(
        "/dashboard/overview",
        headers=student_headers,
    )

    performance = client.get(
        "/dashboard/performance",
        headers=student_headers,
    )

    skills = client.get(
        "/dashboard/skills",
        headers=student_headers,
    )

    activity = client.get(
        "/dashboard/activity",
        params={
            "start_date": "2026-11-20",
            "end_date": "2026-11-21",
        },
        headers=student_headers,
    )

    study_plan = client.get(
        "/dashboard/study-plan",
        headers=student_headers,
    )

    assert overview.status_code == 200
    assert overview.json()["active_plan"] is None
    assert overview.json()["submitted_quiz_sessions"] == 0
    assert overview.json()["answered_questions"] == 0

    assert performance.status_code == 200
    assert performance.json()["submitted_sessions"] == 0
    assert performance.json()["answered_questions"] == 0

    assert skills.status_code == 200
    assert skills.json() == {
        "items": [],
        "total": 0,
    }

    assert activity.status_code == 200
    assert activity.json()["total_active_days"] == 0
    assert activity.json()["total_submitted_sessions"] == 0
    assert len(activity.json()["days"]) == 2

    assert study_plan.status_code == 200
    assert study_plan.json()["plan"] is None
    assert study_plan.json()["total_tasks"] == 0
    assert study_plan.json()["upcoming_tasks"] == []


@pytest.mark.parametrize(
    "path",
    [
        "/dashboard/overview",
        "/dashboard/performance",
        "/dashboard/skills",
        "/dashboard/activity?start_date=2026-11-20&end_date=2026-11-21",
        "/dashboard/study-plan",
    ],
)
def test_dashboard_endpoints_require_authentication(
    dashboard_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
    path: str,
) -> None:
    """Every dashboard endpoint requires a valid Bearer token."""

    client, _, _ = dashboard_client

    response = client.get(path)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "path",
    [
        "/dashboard/overview",
        "/dashboard/performance",
        "/dashboard/skills",
        "/dashboard/activity?start_date=2026-11-20&end_date=2026-11-21",
        "/dashboard/study-plan",
    ],
)
def test_admin_cannot_access_student_dashboard(
    dashboard_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
    path: str,
) -> None:
    """Dashboard endpoints are restricted to student accounts."""

    client, _, headers = dashboard_client

    response = client.get(
        path,
        headers=headers["admin"],
    )

    assert response.status_code == 403


def test_dashboard_study_plan_returns_current_students_plan(
    dashboard_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
) -> None:
    """The authenticated student can see their own active plan."""

    client, engine, headers = dashboard_client

    start_date = date.today() + timedelta(days=1)
    end_date = start_date + timedelta(days=6)

    create_response = client.post(
        "/study-plans",
        json={
            "title": "Dashboard integration plan",
            "target_score": 800,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "daily_minutes": 60,
        },
        headers=headers["student_1"],
    )

    assert create_response.status_code == 201

    plan_id = create_response.json()["id"]

    response = client.get(
        "/dashboard/study-plan",
        headers=headers["student_1"],
    )

    assert response.status_code == 200

    data = response.json()

    assert data["plan"]["id"] == plan_id
    assert data["plan"]["title"] == "Dashboard integration plan"
    assert data["plan"]["status"] == "active"
    assert data["total_tasks"] > 0
    assert data["pending_tasks"] > 0
    assert len(data["upcoming_tasks"]) <= 5

    with Session(engine) as session:
        saved_plan = session.get(StudyPlan, plan_id)

        assert saved_plan is not None
        assert saved_plan.user_id != 0


def test_dashboard_does_not_expose_another_students_plan(
    dashboard_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
) -> None:
    """A student cannot view another student's dashboard plan."""

    client, _, headers = dashboard_client

    start_date = date.today() + timedelta(days=1)
    end_date = start_date + timedelta(days=6)

    create_response = client.post(
        "/study-plans",
        json={
            "title": "Private student plan",
            "target_score": 750,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "daily_minutes": 45,
        },
        headers=headers["student_1"],
    )

    assert create_response.status_code == 201

    response = client.get(
        "/dashboard/study-plan",
        headers=headers["student_2"],
    )

    assert response.status_code == 200
    assert response.json()["plan"] is None
    assert response.json()["total_tasks"] == 0
    assert response.json()["upcoming_tasks"] == []


def test_dashboard_ignores_client_supplied_student_id(
    dashboard_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
) -> None:
    """A query parameter cannot override the authenticated identity."""

    client, _, headers = dashboard_client

    response = client.get(
        "/dashboard/study-plan",
        params={
            "student_id": 999999,
        },
        headers=headers["student_1"],
    )

    assert response.status_code == 200
    assert response.json()["plan"] is None


def test_dashboard_activity_rejects_invalid_date_range(
    dashboard_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
) -> None:
    """An end date before the start date returns HTTP 422."""

    client, _, headers = dashboard_client

    response = client.get(
        "/dashboard/activity",
        params={
            "start_date": "2026-11-22",
            "end_date": "2026-11-20",
        },
        headers=headers["student_1"],
    )

    assert response.status_code == 422


def test_dashboard_activity_requires_both_dates(
    dashboard_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
) -> None:
    """Activity requests must specify both date boundaries."""

    client, _, headers = dashboard_client

    response = client.get(
        "/dashboard/activity",
        params={
            "start_date": "2026-11-20",
        },
        headers=headers["student_1"],
    )

    assert response.status_code == 422


def test_dashboard_routes_declare_bearer_authentication(
    dashboard_client: tuple[
        TestClient,
        Engine,
        dict[str, dict[str, str]],
    ],
) -> None:
    """OpenAPI documents Bearer authentication for all dashboard routes."""

    client, _, _ = dashboard_client

    response = client.get("/openapi.json")

    assert response.status_code == 200

    schema = response.json()

    expected_paths = [
        "/dashboard/overview",
        "/dashboard/performance",
        "/dashboard/skills",
        "/dashboard/activity",
        "/dashboard/study-plan",
    ]

    for path in expected_paths:
        operation = schema["paths"][path]["get"]

        assert operation["security"] == [
            {"BearerAuth": []}
        ]