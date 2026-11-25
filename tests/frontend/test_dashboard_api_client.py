
"""Unit tests for the Dashboard API client."""

from datetime import date, datetime

import httpx
import pytest

from frontend.dashboard_api_client import (
    DashboardAPIClient,
    DashboardAPIError,
)


TOKEN = "test-access-token"


def make_client(handler):
    transport = httpx.MockTransport(handler)

    return DashboardAPIClient(
        base_url="http://testserver",
        access_token=TOKEN,
        transport=transport,
    )


def json_response(data, status_code=200):
    return httpx.Response(
        status_code=status_code,
        json=data,
    )


OVERVIEW_RESPONSE = {
    "target_score": 750,
    "active_plan": None,
    "submitted_quiz_sessions": 3,
    "answered_questions": 60,
    "correct_answers": 45,
    "accuracy_percent": 75.0,
    "active_days": 5,
}

PERFORMANCE_RESPONSE = {
    "submitted_sessions": 3,
    "answered_questions": 60,
    "correct_answers": 45,
    "incorrect_answers": 15,
    "accuracy_percent": 75.0,
    "total_time_spent_seconds": 3600,
}

SKILLS_RESPONSE = {
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
        }
    ],
    "total": 1,
}

ACTIVITY_RESPONSE = {
    "start_date": "2026-11-01",
    "end_date": "2026-11-07",
    "days": [
        {
            "activity_date": "2026-11-01",
            "submitted_sessions": 1,
            "answered_questions": 10,
            "correct_answers": 8,
            "accuracy_percent": 80.0,
        }
    ],
    "total_active_days": 1,
    "total_submitted_sessions": 1,
    "total_answered_questions": 10,
}

STUDY_PLAN_RESPONSE = {
    "plan": None,
    "total_tasks": 0,
    "completed_tasks": 0,
    "pending_tasks": 0,
    "skipped_tasks": 0,
    "completion_percent": 0.0,
    "upcoming_tasks": [],
}


# =====================================================
# Constructor and authentication
# =====================================================


def test_client_sends_bearer_token():
    def handler(request):
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        return json_response(OVERVIEW_RESPONSE)

    with make_client(handler) as client:
        result = client.get_overview()

    assert result == OVERVIEW_RESPONSE


@pytest.mark.parametrize(
    "base_url,token,timeout",
    [
        ("", TOKEN, 10.0),
        ("http://testserver", "", 10.0),
        ("http://testserver", TOKEN, 0),
        ("http://testserver", TOKEN, -1),
    ],
)
def test_client_rejects_invalid_configuration(
    base_url,
    token,
    timeout,
):
    with pytest.raises(ValueError):
        DashboardAPIClient(
            base_url=base_url,
            access_token=token,
            timeout=timeout,
        )


# =====================================================
# Successful Dashboard requests
# =====================================================


def test_get_overview_success():
    def handler(request):
        assert request.method == "GET"
        assert request.url.path == "/dashboard/overview"
        return json_response(OVERVIEW_RESPONSE)

    with make_client(handler) as client:
        result = client.get_overview()

    assert result["target_score"] == 750
    assert result["accuracy_percent"] == 75.0


def test_get_performance_success():
    def handler(request):
        assert request.method == "GET"
        assert request.url.path == "/dashboard/performance"
        return json_response(PERFORMANCE_RESPONSE)

    with make_client(handler) as client:
        result = client.get_performance()

    assert result["submitted_sessions"] == 3
    assert result["incorrect_answers"] == 15


def test_get_skills_success():
    def handler(request):
        assert request.method == "GET"
        assert request.url.path == "/dashboard/skills"
        return json_response(SKILLS_RESPONSE)

    with make_client(handler) as client:
        result = client.get_skills()

    assert result["total"] == 1
    assert result["items"][0]["is_weak"] is True


def test_get_activity_success():
    def handler(request):
        assert request.method == "GET"
        assert request.url.path == "/dashboard/activity"

        assert request.url.params["start_date"] == "2026-11-01"
        assert request.url.params["end_date"] == "2026-11-07"

        return json_response(ACTIVITY_RESPONSE)

    with make_client(handler) as client:
        result = client.get_activity(
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 7),
        )

    assert result["total_active_days"] == 1
    assert len(result["days"]) == 1


def test_get_study_plan_success():
    def handler(request):
        assert request.method == "GET"
        assert request.url.path == "/dashboard/study-plan"
        return json_response(STUDY_PLAN_RESPONSE)

    with make_client(handler) as client:
        result = client.get_study_plan()

    assert result["plan"] is None
    assert result["completion_percent"] == 0.0


# =====================================================
# Activity date validation
# =====================================================


@pytest.mark.parametrize(
    "start_date,end_date",
    [
        (None, date(2026, 11, 7)),
        (date(2026, 11, 1), None),
        ("2026-11-01", date(2026, 11, 7)),
        (date(2026, 11, 1), "2026-11-07"),
        (
            datetime(2026, 11, 1, 10, 0),
            date(2026, 11, 7),
        ),
        (
            date(2026, 11, 1),
            datetime(2026, 11, 7, 10, 0),
        ),
    ],
)
def test_get_activity_rejects_invalid_date_types(
    start_date,
    end_date,
):
    def handler(request):
        pytest.fail("HTTP request must not be sent.")

    with make_client(handler) as client:
        with pytest.raises(ValueError):
            client.get_activity(start_date, end_date)


def test_get_activity_rejects_reversed_date_range():
    def handler(request):
        pytest.fail("HTTP request must not be sent.")

    with make_client(handler) as client:
        with pytest.raises(ValueError, match="không được sau"):
            client.get_activity(
                date(2026, 11, 8),
                date(2026, 11, 1),
            )


# =====================================================
# HTTP error handling
# =====================================================


@pytest.mark.parametrize(
    "status_code,expected_message",
    [
        (401, "đăng nhập lại"),
        (403, "không có quyền"),
        (404, "Không tìm thấy"),
        (422, "không hợp lệ"),
        (500, "Backend đang gặp lỗi"),
    ],
)
def test_http_errors_are_converted_to_dashboard_api_error(
    status_code,
    expected_message,
):
    def handler(request):
        return json_response(
            {"detail": "Internal server detail"},
            status_code=status_code,
        )

    with make_client(handler) as client:
        with pytest.raises(DashboardAPIError) as exc_info:
            client.get_overview()

    assert exc_info.value.status_code == status_code
    assert expected_message in str(exc_info.value)
    assert "Internal server detail" not in str(exc_info.value)


def test_invalid_json_response_is_rejected():
    def handler(request):
        return httpx.Response(
            status_code=200,
            content=b"not-json",
            headers={"Content-Type": "application/json"},
        )

    with make_client(handler) as client:
        with pytest.raises(
            DashboardAPIError,
            match="JSON hợp lệ",
        ):
            client.get_overview()


def test_non_object_json_response_is_rejected():
    def handler(request):
        return httpx.Response(
            status_code=200,
            json=["unexpected", "list"],
        )

    with make_client(handler) as client:
        with pytest.raises(
            DashboardAPIError,
            match="không hợp lệ",
        ):
            client.get_overview()


# =====================================================
# Connection and timeout errors
# =====================================================


def test_connection_error_is_converted_to_dashboard_api_error():
    def handler(request):
        raise httpx.ConnectError(
            "Internal connection details",
            request=request,
        )

    with make_client(handler) as client:
        with pytest.raises(DashboardAPIError) as exc_info:
            client.get_overview()

    assert "Không thể kết nối" in str(exc_info.value)


def test_timeout_error_is_converted_to_dashboard_api_error():
    def handler(request):
        raise httpx.ReadTimeout(
            "Internal timeout details",
            request=request,
        )

    with make_client(handler) as client:
        with pytest.raises(DashboardAPIError) as exc_info:
            client.get_overview()

    assert "quá chậm" in str(exc_info.value)


# =====================================================
# Response validation
# =====================================================


def test_overview_rejects_missing_required_field():
    invalid_response = {
        "target_score": 750,
        "active_plan": None,
        "submitted_quiz_sessions": 3,
        "answered_questions": 60,
        "correct_answers": 45,
        "accuracy_percent": 75.0,
        # Missing active_days
    }

    def handler(request):
        return json_response(invalid_response)

    with make_client(handler) as client:
        with pytest.raises(
            DashboardAPIError,
            match="active_days",
        ):
            client.get_overview()


def test_overview_rejects_invalid_target_score():
    invalid_response = {
        **OVERVIEW_RESPONSE,
        "target_score": 1000,
    }

    def handler(request):
        return json_response(invalid_response)

    with make_client(handler) as client:
        with pytest.raises(
            DashboardAPIError,
            match="Điểm TOEIC mục tiêu",
        ):
            client.get_overview()


def test_overview_rejects_invalid_accuracy():
    invalid_response = {
        **OVERVIEW_RESPONSE,
        "accuracy_percent": 120,
    }

    def handler(request):
        return json_response(invalid_response)

    with make_client(handler) as client:
        with pytest.raises(
            DashboardAPIError,
            match="accuracy_percent",
        ):
            client.get_overview()


def test_performance_rejects_negative_count():
    invalid_response = {
        **PERFORMANCE_RESPONSE,
        "correct_answers": -1,
    }

    def handler(request):
        return json_response(invalid_response)

    with make_client(handler) as client:
        with pytest.raises(
            DashboardAPIError,
            match="correct_answers",
        ):
            client.get_performance()


def test_skills_rejects_total_mismatch():
    invalid_response = {
        **SKILLS_RESPONSE,
        "total": 2,
    }

    def handler(request):
        return json_response(invalid_response)

    with make_client(handler) as client:
        with pytest.raises(
            DashboardAPIError,
            match="không khớp",
        ):
            client.get_skills()


def test_skills_rejects_invalid_skill_item():
    invalid_response = {
        "items": [
            {
                "skill_id": 1,
                "code": "PART5",
                "name": "Grammar",
                "category": "Part 5",
                "attempt_count": 10,
                "correct_count": 6,
                "incorrect_count": 4,
                "accuracy_percent": 60.0,
                "is_weak": "yes",
            }
        ],
        "total": 1,
    }

    def handler(request):
        return json_response(invalid_response)

    with make_client(handler) as client:
        with pytest.raises(
            DashboardAPIError,
            match="Trạng thái kỹ năng yếu",
        ):
            client.get_skills()


def test_activity_rejects_invalid_day():
    invalid_response = {
        **ACTIVITY_RESPONSE,
        "days": [
            {
                "activity_date": 123,
                "submitted_sessions": 1,
                "answered_questions": 10,
                "correct_answers": 8,
                "accuracy_percent": 80.0,
            }
        ],
    }

    def handler(request):
        return json_response(invalid_response)

    with make_client(handler) as client:
        with pytest.raises(
            DashboardAPIError,
            match="Ngày hoạt động",
        ):
            client.get_activity(
                date(2026, 11, 1),
                date(2026, 11, 7),
            )


def test_study_plan_rejects_invalid_completion_percent():
    invalid_response = {
        **STUDY_PLAN_RESPONSE,
        "completion_percent": 150,
    }

    def handler(request):
        return json_response(invalid_response)

    with make_client(handler) as client:
        with pytest.raises(
            DashboardAPIError,
            match="completion_percent",
        ):
            client.get_study_plan()
