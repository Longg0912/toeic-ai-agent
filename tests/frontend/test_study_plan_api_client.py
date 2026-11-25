
from datetime import date

import httpx
import pytest

from frontend.study_plan_api_client import (
    StudyPlanAPIClient,
    StudyPlanAPIError,
)


BASE_URL = "http://testserver"
TOKEN = "test-access-token"


def make_plan(
    plan_id: int = 1,
    status: str = "active",
) -> dict:
    return {
        "id": plan_id,
        "title": "TOEIC 800",
        "target_score": 800,
        "start_date": "2026-11-21",
        "end_date": "2026-12-21",
        "daily_minutes": 60,
        "status": status,
        "created_at": "2026-11-21T08:00:00",
        "updated_at": "2026-11-21T08:00:00",
    }


def make_task(
    task_id: int = 1,
    skill: dict | None = None,
) -> dict:
    return {
        "id": task_id,
        "skill_id": skill["id"] if skill else None,
        "skill": skill,
        "task_type": "practice",
        "scheduled_date": "2026-11-21",
        "estimated_minutes": 30,
        "target_question_count": 15,
        "status": "pending",
        "completed_at": None,
    }


def make_detail() -> dict:
    data = make_plan()
    data["tasks"] = [
        make_task(
            skill={
                "id": 1,
                "code": "part5",
                "name": "Incomplete Sentences",
                "category": "grammar",
            }
        ),
        make_task(task_id=2, skill=None),
    ]
    return data


def make_list() -> dict:
    return {
        "items": [make_plan()],
        "total": 1,
        "limit": 20,
        "offset": 0,
    }


def make_client(handler) -> StudyPlanAPIClient:
    transport = httpx.MockTransport(handler)

    return StudyPlanAPIClient(
        base_url=BASE_URL,
        access_token=TOKEN,
        transport=transport,
    )


def json_response(
    data: dict,
    status_code: int = 200,
) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=data,
    )


# ------------------------------------------------------------------
# Constructor and authentication
# ------------------------------------------------------------------


def test_constructor_requires_access_token():
    with pytest.raises(ValueError):
        StudyPlanAPIClient(
            base_url=BASE_URL,
            access_token="",
        )


def test_constructor_rejects_invalid_timeout():
    with pytest.raises(ValueError):
        StudyPlanAPIClient(
            base_url=BASE_URL,
            access_token=TOKEN,
            timeout=0,
        )


def test_client_sends_bearer_token():
    def handler(request: httpx.Request):
        assert request.headers["Authorization"] == (
            f"Bearer {TOKEN}"
        )
        return json_response(make_list())

    with make_client(handler) as client:
        client.get_study_plans()


# ------------------------------------------------------------------
# Create study plan
# ------------------------------------------------------------------


def test_create_study_plan_success():
    def handler(request: httpx.Request):
        assert request.method == "POST"
        assert request.url.path == "/study-plans"

        payload = __import__("json").loads(request.content)

        assert payload == {
            "title": "TOEIC 800",
            "target_score": 800,
            "start_date": "2026-11-21",
            "end_date": "2026-12-21",
            "daily_minutes": 60,
        }

        return json_response(
            make_plan(),
            status_code=201,
        )

    with make_client(handler) as client:
        result = client.create_study_plan(
            title="TOEIC 800",
            target_score=800,
            start_date=date(2026, 11, 21),
            end_date=date(2026, 12, 21),
            daily_minutes=60,
        )

    assert result["id"] == 1
    assert result["status"] == "active"


@pytest.mark.parametrize(
    "title",
    ["", "   ", "x" * 201],
)
def test_create_study_plan_rejects_invalid_title(title):
    with make_client(
        lambda request: json_response(make_plan(), 201)
    ) as client:
        with pytest.raises(ValueError):
            client.create_study_plan(
                title=title,
                target_score=800,
                start_date=date(2026, 11, 21),
                end_date=date(2026, 12, 21),
                daily_minutes=60,
            )


@pytest.mark.parametrize(
    "target_score",
    [-1, 991, True, 800.5],
)
def test_create_study_plan_rejects_invalid_target_score(
    target_score,
):
    with make_client(
        lambda request: json_response(make_plan(), 201)
    ) as client:
        with pytest.raises(ValueError):
            client.create_study_plan(
                title="TOEIC 800",
                target_score=target_score,
                start_date=date(2026, 11, 21),
                end_date=date(2026, 12, 21),
                daily_minutes=60,
            )


@pytest.mark.parametrize(
    "daily_minutes",
    [0, -1, True, 30.5],
)
def test_create_study_plan_rejects_invalid_daily_minutes(
    daily_minutes,
):
    with make_client(
        lambda request: json_response(make_plan(), 201)
    ) as client:
        with pytest.raises(ValueError):
            client.create_study_plan(
                title="TOEIC 800",
                target_score=800,
                start_date=date(2026, 11, 21),
                end_date=date(2026, 12, 21),
                daily_minutes=daily_minutes,
            )


def test_create_study_plan_rejects_reversed_dates():
    with make_client(
        lambda request: json_response(make_plan(), 201)
    ) as client:
        with pytest.raises(ValueError):
            client.create_study_plan(
                title="TOEIC 800",
                target_score=800,
                start_date=date(2026, 12, 21),
                end_date=date(2026, 11, 21),
                daily_minutes=60,
            )


def test_create_study_plan_rejects_datetime_instead_of_date():
    from datetime import datetime

    with make_client(
        lambda request: json_response(make_plan(), 201)
    ) as client:
        with pytest.raises(ValueError):
            client.create_study_plan(
                title="TOEIC 800",
                target_score=800,
                start_date=datetime(2026, 11, 21),
                end_date=date(2026, 12, 21),
                daily_minutes=60,
            )


# ------------------------------------------------------------------
# Get study plans
# ------------------------------------------------------------------


def test_get_study_plans_success():
    def handler(request: httpx.Request):
        assert request.method == "GET"
        assert request.url.path == "/study-plans"
        assert request.url.params["limit"] == "20"
        assert request.url.params["offset"] == "0"

        return json_response(make_list())

    with make_client(handler) as client:
        result = client.get_study_plans()

    assert result["total"] == 1
    assert len(result["items"]) == 1
    assert result["items"][0]["title"] == "TOEIC 800"


def test_get_study_plans_supports_pagination():
    def handler(request: httpx.Request):
        assert request.url.params["limit"] == "10"
        assert request.url.params["offset"] == "20"

        return json_response({
            "items": [],
            "total": 30,
            "limit": 10,
            "offset": 20,
        })

    with make_client(handler) as client:
        result = client.get_study_plans(
            limit=10,
            offset=20,
        )

    assert result["items"] == []
    assert result["total"] == 30


@pytest.mark.parametrize(
    ("limit", "offset"),
    [
        (0, 0),
        (101, 0),
        (True, 0),
        (20, -1),
        (20, True),
        (1.5, 0),
    ],
)
def test_get_study_plans_rejects_invalid_pagination(
    limit,
    offset,
):
    with make_client(
        lambda request: json_response(make_list())
    ) as client:
        with pytest.raises(ValueError):
            client.get_study_plans(
                limit=limit,
                offset=offset,
            )


# ------------------------------------------------------------------
# Get study plan detail
# ------------------------------------------------------------------


def test_get_study_plan_detail_success():
    def handler(request: httpx.Request):
        assert request.method == "GET"
        assert request.url.path == "/study-plans/1"

        return json_response(make_detail())

    with make_client(handler) as client:
        result = client.get_study_plan_detail(1)

    assert result["id"] == 1
    assert len(result["tasks"]) == 2
    assert result["tasks"][0]["skill"]["name"] == (
        "Incomplete Sentences"
    )
    assert result["tasks"][1]["skill"] is None


@pytest.mark.parametrize(
    "plan_id",
    [0, -1, True, 1.5, "1"],
)
def test_get_study_plan_detail_rejects_invalid_plan_id(
    plan_id,
):
    with make_client(
        lambda request: json_response(make_detail())
    ) as client:
        with pytest.raises(ValueError):
            client.get_study_plan_detail(plan_id)


def test_get_study_plan_detail_rejects_missing_tasks():
    data = make_plan()

    with make_client(
        lambda request: json_response(data)
    ) as client:
        with pytest.raises(StudyPlanAPIError):
            client.get_study_plan_detail(1)


def test_get_study_plan_detail_rejects_invalid_task_type():
    data = make_detail()
    data["tasks"][0]["task_type"] = "invalid"

    with make_client(
        lambda request: json_response(data)
    ) as client:
        with pytest.raises(StudyPlanAPIError):
            client.get_study_plan_detail(1)


# ------------------------------------------------------------------
# Lifecycle actions
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method_name", "action", "status"),
    [
        ("pause_study_plan", "pause", "paused"),
        ("resume_study_plan", "resume", "active"),
        ("complete_study_plan", "complete", "completed"),
    ],
)
def test_study_plan_lifecycle_actions(
    method_name,
    action,
    status,
):
    def handler(request: httpx.Request):
        assert request.method == "POST"
        assert request.url.path == (
            f"/study-plans/1/{action}"
        )

        return json_response(
            make_plan(status=status)
        )

    with make_client(handler) as client:
        method = getattr(client, method_name)
        result = method(1)

    assert result["status"] == status


# ------------------------------------------------------------------
# HTTP error handling
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status_code", "expected_text"),
    [
        (401, "đăng nhập"),
        (403, "quyền"),
        (404, "Không tìm thấy"),
        (409, "trạng thái"),
        (422, "không hợp lệ"),
        (500, "Backend"),
    ],
)
def test_http_errors_are_translated(
    status_code,
    expected_text,
):
    def handler(request: httpx.Request):
        return httpx.Response(status_code)

    with make_client(handler) as client:
        with pytest.raises(StudyPlanAPIError) as exc_info:
            client.get_study_plans()

    assert exc_info.value.status_code == status_code
    assert expected_text.lower() in str(exc_info.value).lower()


def test_invalid_json_response_is_rejected():
    def handler(request: httpx.Request):
        return httpx.Response(
            200,
            content=b"not-json",
            headers={"Content-Type": "application/json"},
        )

    with make_client(handler) as client:
        with pytest.raises(StudyPlanAPIError):
            client.get_study_plans()


def test_non_object_json_response_is_rejected():
    def handler(request: httpx.Request):
        return httpx.Response(
            200,
            json=["not", "an", "object"],
        )

    with make_client(handler) as client:
        with pytest.raises(StudyPlanAPIError):
            client.get_study_plans()


def test_backend_connection_error_is_translated():
    def handler(request: httpx.Request):
        raise httpx.ConnectError(
            "connection failed",
            request=request,
        )

    with make_client(handler) as client:
        with pytest.raises(StudyPlanAPIError) as exc_info:
            client.get_study_plans()

    assert "kết nối" in str(exc_info.value).lower()


def test_backend_timeout_is_translated():
    def handler(request: httpx.Request):
        raise httpx.ReadTimeout(
            "request timed out",
            request=request,
        )

    with make_client(handler) as client:
        with pytest.raises(StudyPlanAPIError) as exc_info:
            client.get_study_plans()

    assert "chậm" in str(exc_info.value).lower()


# ------------------------------------------------------------------
# Response validation
# ------------------------------------------------------------------


def test_invalid_plan_response_is_rejected():
    data = make_plan()
    del data["target_score"]

    with make_client(
        lambda request: json_response(data, 201)
    ) as client:
        with pytest.raises(StudyPlanAPIError):
            client.create_study_plan(
                title="TOEIC 800",
                target_score=800,
                start_date=date(2026, 11, 21),
                end_date=date(2026, 12, 21),
                daily_minutes=60,
            )


def test_invalid_plan_status_is_rejected():
    data = make_plan(status="unknown")

    with make_client(
        lambda request: json_response(data)
    ) as client:
        with pytest.raises(StudyPlanAPIError):
            client.get_study_plans()


def test_invalid_list_response_is_rejected():
    data = make_list()
    del data["total"]

    with make_client(
        lambda request: json_response(data)
    ) as client:
        with pytest.raises(StudyPlanAPIError):
            client.get_study_plans()


def test_invalid_skill_response_is_rejected():
    data = make_detail()
    data["tasks"][0]["skill"]["name"] = 123

    with make_client(
        lambda request: json_response(data)
    ) as client:
        with pytest.raises(StudyPlanAPIError):
            client.get_study_plan_detail(1)
