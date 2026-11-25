
"""Tests for the Streamlit Study Planner UI."""

from datetime import date, timedelta

import pytest
from streamlit.testing.v1 import AppTest

import frontend.study_plan_ui as study_plan_ui

from frontend.study_plan_api_client import StudyPlanAPIError


TEST_TOKEN = "test-study-plan-token"


def make_plan(
    *,
    plan_id: int = 1,
    status: str = "active",
) -> dict:
    """Create a representative StudyPlan API response."""

    return {
        "id": plan_id,
        "user_id": 1,
        "title": "TOEIC 750 - 8 tuần",
        "target_score": 750,
        "start_date": date.today().isoformat(),
        "end_date": (date.today() + timedelta(days=30)).isoformat(),
        "daily_minutes": 60,
        "status": status,
        "created_at": "2026-11-21T08:00:00",
        "updated_at": "2026-11-21T08:00:00",
    }


def make_task() -> dict:
    """Create a representative StudyPlanTask response."""

    return {
        "id": 1,
        "study_plan_id": 1,
        "skill_id": 1,
        "task_type": "practice",
        "scheduled_date": date.today().isoformat(),
        "estimated_minutes": 20,
        "target_question_count": 10,
        "status": "pending",
        "completed_at": None,
        "skill": {
            "id": 1,
            "code": "PART5_GRAMMAR",
            "name": "Grammar",
            "category": "Part 5",
        },
    }


class FakeStudyPlanAPIClient:
    """Fake API client for Study Planner UI tests."""

    def __init__(
        self,
        *,
        base_url: str = "http://testserver",
        access_token: str = TEST_TOKEN,
    ) -> None:
        self.base_url = base_url
        self.access_token = access_token

        self.calls = []
        self.plans = [make_plan()]
        self.plan_detail = {
            **make_plan(),
            "tasks": [make_task()],
        }

        self.list_error = None
        self.detail_error = None
        self.resume_error = None

        self.resumed_plan_ids = []
        self.paused_plan_ids = []
        self.completed_plan_ids = []

        self.created_payloads = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def get_study_plans(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
    ):
        self.calls.append(("get_study_plans", limit, offset))

        if self.list_error:
            raise self.list_error

        return {
            "items": self.plans,
            "total": len(self.plans),
            "limit": limit,
            "offset": offset,
        }

    def get_study_plan_detail(self, plan_id: int):
        self.calls.append(("get_study_plan_detail", plan_id))

        if self.detail_error:
            raise self.detail_error

        return self.plan_detail

    def create_study_plan(
        self,
        *,
        title,
        target_score,
        start_date,
        end_date,
        daily_minutes,
    ):
        payload = {
            "title": title,
            "target_score": target_score,
            "start_date": start_date,
            "end_date": end_date,
            "daily_minutes": daily_minutes,
        }
        self.created_payloads.append(payload)

        return make_plan()

    def pause_study_plan(self, plan_id: int):
        self.paused_plan_ids.append(plan_id)
        return make_plan(status="paused")

    def resume_study_plan(self, plan_id: int):
        if self.resume_error:
            raise self.resume_error

        self.resumed_plan_ids.append(plan_id)
        return make_plan(status="active")

    def complete_study_plan(self, plan_id: int):
        self.completed_plan_ids.append(plan_id)
        return make_plan(status="completed")


def start_app(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeStudyPlanAPIClient | None,
    *,
    token: str | None = TEST_TOKEN,
) -> AppTest:
    """Start the Study Planner UI with a fake authenticated session."""

    monkeypatch.setattr(
        study_plan_ui,
        "get_active_token",
        lambda state: token,
    )

    if fake_client is not None:
        monkeypatch.setattr(
            study_plan_ui,
            "StudyPlanAPIClient",
            lambda **kwargs: fake_client,
        )

    return AppTest.from_string(
        "from frontend.study_plan_ui import render_study_plan_interface\n"
        "render_study_plan_interface('http://testserver')\n",
        default_timeout=10,
    ).run()


def test_anonymous_user_sees_login_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An anonymous user must not access the Study Planner API."""

    def unexpected_client(**kwargs):
        pytest.fail(
            "StudyPlanAPIClient must not be created without authentication."
        )

    monkeypatch.setattr(
        study_plan_ui,
        "get_active_token",
        lambda state: None,
    )

    monkeypatch.setattr(
        study_plan_ui,
        "StudyPlanAPIClient",
        unexpected_client,
    )

    app = AppTest.from_string(
        "from frontend.study_plan_ui import render_study_plan_interface\n"
        "render_study_plan_interface('http://testserver')\n",
        default_timeout=10,
    ).run()

    assert len(app.exception) == 0

    assert any(
        "Vui lòng đăng nhập" in element.value
        for element in app.info
    )


def test_authenticated_user_sees_plan_list_and_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Authenticated user can see plan information and tasks."""

    fake = FakeStudyPlanAPIClient()

    app = start_app(monkeypatch, fake)

    assert len(app.exception) == 0

    assert fake.access_token == TEST_TOKEN
    assert fake.base_url == "http://testserver"

    assert fake.calls == [
        ("get_study_plans", 20, 0),
        ("get_study_plan_detail", 1),
    ]

    headers = [
        element.value
        for element in app.header
    ]

    subheaders = [
        element.value
        for element in app.subheader
    ]

    assert "🗓️ Study Planner" in headers
    assert "Tạo kế hoạch học tập" in subheaders
    assert "Danh sách kế hoạch" in subheaders
    assert "Chi tiết kế hoạch" in subheaders

    assert any(
        "TOEIC 750 - 8 tuần" in element.value
        for element in app.markdown
    )

    # One dataframe for the plan list and one for task details.
    assert len(app.dataframe) == 2

    # The task progress indicator is rendered.
    assert len(app.progress) == 1


def test_paused_plan_can_be_resumed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A paused plan exposes the resume action."""

    fake = FakeStudyPlanAPIClient()

    fake.plans = [
        make_plan(status="paused")
    ]

    fake.plan_detail = {
        **make_plan(status="paused"),
        "tasks": [make_task()],
    }

    app = start_app(monkeypatch, fake)

    assert len(app.exception) == 0

    resume_buttons = [
        button
        for button in app.button
        if button.label == "Tiếp tục kế hoạch"
    ]

    assert len(resume_buttons) == 1

    resume_buttons[0].click().run()

    assert len(app.exception) == 0
    assert fake.resumed_plan_ids == [1]


def test_study_plan_api_error_is_displayed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Study Planner displays API errors without crashing."""

    fake = FakeStudyPlanAPIClient()

    fake.list_error = StudyPlanAPIError(
        "Không thể tải danh sách kế hoạch.",
        status_code=500,
    )

    app = start_app(monkeypatch, fake)

    assert len(app.exception) == 0

    assert any(
        "Không thể tải danh sách kế hoạch."
        in element.value
        for element in app.error
    )

    assert fake.calls == [
        ("get_study_plans", 20, 0),
    ]


def test_authenticated_user_can_create_study_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Authenticated user can submit a valid study plan."""

    fake = FakeStudyPlanAPIClient()

    app = start_app(monkeypatch, fake)

    assert len(app.exception) == 0

    title_input = next(
        widget
        for widget in app.text_input
        if widget.key == "toeic_plan_title"
    )
    title_input.set_value("TOEIC 850 - 12 tuần")

    create_button = next(
        button
        for button in app.button
        if button.label == "Tạo kế hoạch"
    )

    create_button.click().run()

    assert len(app.exception) == 0
    assert len(fake.created_payloads) == 1

    payload = fake.created_payloads[0]

    assert payload["title"] == "TOEIC 850 - 12 tuần"
    assert payload["target_score"] == 750
    assert payload["daily_minutes"] == 60
    assert payload["start_date"] == date.today()
    assert payload["end_date"] == date.today() + timedelta(days=30)


def test_active_plan_can_be_paused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An active study plan exposes the pause action."""

    fake = FakeStudyPlanAPIClient()

    app = start_app(monkeypatch, fake)

    assert len(app.exception) == 0

    pause_buttons = [
        button
        for button in app.button
        if button.label == "Tạm dừng kế hoạch"
    ]

    assert len(pause_buttons) == 1

    pause_buttons[0].click().run()

    assert len(app.exception) == 0
    assert fake.paused_plan_ids == [1]


def test_active_plan_can_be_completed_after_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completing a plan requires explicit confirmation."""

    fake = FakeStudyPlanAPIClient()

    app = start_app(monkeypatch, fake)

    assert len(app.exception) == 0
    assert fake.completed_plan_ids == []

    complete_buttons = [
        button
        for button in app.button
        if button.label == "Hoàn thành kế hoạch"
    ]

    assert len(complete_buttons) == 1

    complete_buttons[0].click().run()

    assert len(app.exception) == 0
    assert fake.completed_plan_ids == []

    confirm_buttons = [
        button
        for button in app.button
        if button.label == "Xác nhận hoàn thành"
    ]

    assert len(confirm_buttons) == 1

    confirm_buttons[0].click().run()

    assert len(app.exception) == 0
    assert fake.completed_plan_ids == [1]
