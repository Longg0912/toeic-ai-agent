"""Tests for the Streamlit student dashboard UI."""

from datetime import date, timedelta

import pytest
from streamlit.testing.v1 import AppTest

import frontend.dashboard_ui as dashboard_ui

from frontend.dashboard_api_client import DashboardAPIError


TEST_TOKEN = "test-dashboard-access-token"


# =====================================================
# Fake Dashboard API Client
# =====================================================


class FakeDashboardAPIClient:
    """In-memory Dashboard API client for Streamlit AppTest."""

    def __init__(
        self,
        *,
        base_url: str = "http://testserver",
        access_token: str = TEST_TOKEN,
    ) -> None:
        self.base_url = base_url
        self.access_token = access_token

        self.calls = []

        self.overview_error = None
        self.performance_error = None
        self.skills_error = None
        self.activity_error = None
        self.study_plan_error = None

        self.overview_data = {
            "target_score": 750,
            "active_plan": {
                "title": "TOEIC 750 - 8 tuần",
            },
            "submitted_quiz_sessions": 5,
            "answered_questions": 100,
            "correct_answers": 75,
            "accuracy_percent": 75.0,
            "active_days": 6,
        }

        self.performance_data = {
            "submitted_sessions": 5,
            "answered_questions": 100,
            "correct_answers": 75,
            "incorrect_answers": 25,
            "accuracy_percent": 75.0,
            "total_time_spent_seconds": 7200,
        }

        self.skills_data = {
            "items": [
                {
                    "skill_id": 1,
                    "code": "PART5_GRAMMAR",
                    "name": "Grammar",
                    "category": "Part 5",
                    "attempt_count": 10,
                    "correct_count": 6,
                    "incorrect_count": 4,
                    "accuracy_percent": 60.0,
                    "is_weak": True,
                },
                {
                    "skill_id": 2,
                    "code": "PART5_VOCAB",
                    "name": "Vocabulary",
                    "category": "Part 5",
                    "attempt_count": 10,
                    "correct_count": 9,
                    "incorrect_count": 1,
                    "accuracy_percent": 90.0,
                    "is_weak": False,
                },
            ],
            "total": 2,
        }

        self.activity_data = {
            "start_date": date.today().isoformat(),
            "end_date": date.today().isoformat(),
            "days": [
                {
                    "activity_date": date.today().isoformat(),
                    "submitted_sessions": 2,
                    "answered_questions": 20,
                    "correct_answers": 15,
                    "accuracy_percent": 75.0,
                }
            ],
            "total_active_days": 1,
            "total_submitted_sessions": 2,
            "total_answered_questions": 20,
        }

        self.study_plan_data = {
            "plan": {
                "title": "TOEIC 750 - 8 tuần",
            },
            "total_tasks": 20,
            "completed_tasks": 8,
            "pending_tasks": 10,
            "skipped_tasks": 2,
            "completion_percent": 40.0,
            "upcoming_tasks": [
                {
                    "scheduled_date": date.today().isoformat(),
                    "task_type": "practice",
                    "skill": {
                        "name": "Grammar",
                    },
                    "estimated_minutes": 20,
                    "target_question_count": 10,
                    "status": "pending",
                }
            ],
        }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def get_overview(self):
        self.calls.append("overview")

        if self.overview_error:
            raise self.overview_error

        return self.overview_data

    def get_performance(self):
        self.calls.append("performance")

        if self.performance_error:
            raise self.performance_error

        return self.performance_data

    def get_skills(self):
        self.calls.append("skills")

        if self.skills_error:
            raise self.skills_error

        return self.skills_data

    def get_activity(self, *, start_date, end_date):
        self.calls.append(
            ("activity", start_date, end_date)
        )

        if self.activity_error:
            raise self.activity_error

        return self.activity_data

    def get_study_plan(self):
        self.calls.append("study_plan")

        if self.study_plan_error:
            raise self.study_plan_error

        return self.study_plan_data


# =====================================================
# AppTest helpers
# =====================================================


def start_dashboard_app(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeDashboardAPIClient | None,
    *,
    token: str | None = TEST_TOKEN,
) -> AppTest:
    """Run the Dashboard UI with a fake authenticated session."""

    monkeypatch.setattr(
        dashboard_ui,
        "get_active_token",
        lambda state: token,
    )

    if fake_client is not None:
        monkeypatch.setattr(
            dashboard_ui,
            "DashboardAPIClient",
            lambda **kwargs: fake_client,
        )

    return AppTest.from_string(
        "from frontend.dashboard_ui import render_dashboard_interface\n"
        "render_dashboard_interface('http://testserver')\n",
        default_timeout=10,
    ).run()


# =====================================================
# Group A — Authentication
# =====================================================


def test_anonymous_user_sees_login_required_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dashboard must not request API data without a JWT."""

    def unexpected_client(**kwargs):
        pytest.fail(
            "DashboardAPIClient must not be created without authentication."
        )

    monkeypatch.setattr(
        dashboard_ui,
        "get_active_token",
        lambda state: None,
    )

    monkeypatch.setattr(
        dashboard_ui,
        "DashboardAPIClient",
        unexpected_client,
    )

    app = AppTest.from_string(
        "from frontend.dashboard_ui import render_dashboard_interface\n"
        "render_dashboard_interface('http://testserver')\n",
        default_timeout=10,
    ).run()

    assert len(app.exception) == 0

    assert any(
        "Vui lòng đăng nhập" in element.value
        for element in app.info
    )

    assert not any(
        element.value == "📊 Dashboard học tập"
        for element in app.header
    )


# =====================================================
# Group B — Successful Dashboard rendering
# =====================================================


def test_authenticated_user_loads_all_dashboard_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Authenticated Dashboard loads all five API resources."""

    fake = FakeDashboardAPIClient()

    app = start_dashboard_app(
        monkeypatch,
        fake,
    )

    assert len(app.exception) == 0
    assert fake.access_token == TEST_TOKEN
    assert fake.base_url == "http://testserver"

    assert fake.calls[:3] == [
        "overview",
        "performance",
        "skills",
    ]

    activity_call = fake.calls[3]

    assert activity_call[0] == "activity"
    assert activity_call[1] == date.today() - timedelta(days=29)
    assert activity_call[2] == date.today()

    assert fake.calls[4] == "study_plan"

    rendered_sections = [
        element.value
        for element in app.subheader
    ]

    assert "Tổng quan học tập" in rendered_sections
    assert "Hiệu suất luyện tập" in rendered_sections
    assert "Phân tích kỹ năng" in rendered_sections
    assert "Hoạt động học tập" in rendered_sections
    assert "Kế hoạch học tập" in rendered_sections

    assert any(
        "Grammar" in element.value
        for element in app.warning
    )


def test_dashboard_displays_empty_data_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty skills, activity, and plan data are handled."""

    fake = FakeDashboardAPIClient()

    fake.skills_data = {
        "items": [],
        "total": 0,
    }

    fake.activity_data = {
        "start_date": date.today().isoformat(),
        "end_date": date.today().isoformat(),
        "days": [],
        "total_active_days": 0,
        "total_submitted_sessions": 0,
        "total_answered_questions": 0,
    }

    fake.study_plan_data = {
        "plan": None,
        "total_tasks": 0,
        "completed_tasks": 0,
        "pending_tasks": 0,
        "skipped_tasks": 0,
        "completion_percent": 0.0,
        "upcoming_tasks": [],
    }

    app = start_dashboard_app(
        monkeypatch,
        fake,
    )

    assert len(app.exception) == 0

    info_messages = [
        element.value
        for element in app.info
    ]

    assert any(
        "Chưa có dữ liệu kỹ năng" in message
        for message in info_messages
    )

    assert any(
        "Chưa có hoạt động học tập" in message
        for message in info_messages
    )

    assert any(
        "chưa có kế hoạch học tập" in message
        for message in info_messages
    )


# =====================================================
# Group C — Error handling
# =====================================================


def test_dashboard_api_error_is_displayed_without_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dashboard API errors must be shown to the student."""

    fake = FakeDashboardAPIClient()

    fake.performance_error = DashboardAPIError(
        "Không thể tải hiệu suất luyện tập.",
        status_code=500,
    )

    app = start_dashboard_app(
        monkeypatch,
        fake,
    )

    assert len(app.exception) == 0

    assert any(
        "Không thể tải hiệu suất luyện tập."
        in element.value
        for element in app.error
    )

    # The UI should stop loading further sections after an API error.
    assert fake.calls == [
        "overview",
        "performance",
    ]