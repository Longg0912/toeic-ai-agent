
"""Tests for the TOEIC quiz API client."""

import json

import httpx
import pytest

from frontend.quiz_api_client import QuizAPIClient, QuizAPIError


def make_client(handler) -> QuizAPIClient:
    transport = httpx.MockTransport(handler)

    return QuizAPIClient(
        base_url="http://testserver",
        access_token="test-access-token",
        transport=transport,
    )


def test_create_session_sends_auth_and_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/quiz-sessions"
        assert request.headers["Authorization"] == (
            "Bearer test-access-token"
        )
        assert json.loads(request.content) == {
            "question_count": 5,
            "skill_code": "GRAMMAR_PRONOUNS",
        }

        return httpx.Response(
            201,
            json={
                "id": 10,
                "status": "in_progress",
                "question_count": 5,
                "items": [],
            },
        )

    client = make_client(handler)

    try:
        result = client.create_session(
            question_count=5,
            skill_code="GRAMMAR_PRONOUNS",
        )

        assert result["id"] == 10
        assert result["status"] == "in_progress"
    finally:
        client.close()


def test_submit_session_sends_answers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/quiz-sessions/10/submit"

        body = json.loads(request.content)
        assert body == {
            "answers": [
                {
                    "quiz_item_id": 101,
                    "selected_option_key": "B",
                    "time_spent_seconds": 12,
                }
            ]
        }

        return httpx.Response(
            200,
            json={
                "session_id": 10,
                "status": "submitted",
                "total_questions": 1,
                "answered_count": 1,
                "correct_count": 1,
                "accuracy_percent": 100.0,
                "items": [],
            },
        )

    client = make_client(handler)

    try:
        result = client.submit_session(
            session_id=10,
            answers=[
                {
                    "quiz_item_id": 101,
                    "selected_option_key": "B",
                    "time_spent_seconds": 12,
                }
            ],
        )

        assert result["correct_count"] == 1
        assert result["accuracy_percent"] == 100.0
    finally:
        client.close()


def test_list_sessions_sends_pagination_parameters() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/quiz-sessions"
        assert request.url.params["limit"] == "5"
        assert request.url.params["offset"] == "10"

        return httpx.Response(
            200,
            json={
                "items": [],
                "total": 0,
                "limit": 5,
                "offset": 10,
            },
        )

    client = make_client(handler)

    try:
        result = client.list_sessions(limit=5, offset=10)

        assert result["items"] == []
        assert result["total"] == 0
    finally:
        client.close()


def test_get_session_uses_session_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/quiz-sessions/10"

        return httpx.Response(
            200,
            json={
                "id": 10,
                "status": "submitted",
                "items": [],
            },
        )

    client = make_client(handler)

    try:
        result = client.get_session(10)

        assert result["id"] == 10
        assert result["status"] == "submitted"
    finally:
        client.close()


def test_insufficient_questions_error_is_translated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "detail": {
                    "message": (
                        "Not enough eligible TOEIC Part 5 questions."
                    ),
                    "requested": 10,
                    "available": 3,
                }
            },
        )

    client = make_client(handler)

    try:
        with pytest.raises(QuizAPIError) as exc_info:
            client.create_session(question_count=10)

        assert exc_info.value.status_code == 409
        assert "chỉ có 3 câu hỏi" in str(exc_info.value).lower()
        assert "yêu cầu 10 câu" in str(exc_info.value).lower()
    finally:
        client.close()


def test_expired_token_error_is_translated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"detail": "Not authenticated"},
        )

    client = make_client(handler)

    try:
        with pytest.raises(QuizAPIError) as exc_info:
            client.list_sessions()

        assert exc_info.value.status_code == 401
        assert "đăng nhập lại" in str(exc_info.value).lower()
    finally:
        client.close()


def test_create_session_rejects_invalid_question_count() -> None:
    client = make_client(
        lambda request: httpx.Response(201, json={})
    )

    try:
        with pytest.raises(ValueError):
            client.create_session(question_count=0)
    finally:
        client.close()


def test_client_requires_access_token() -> None:
    with pytest.raises(ValueError):
        QuizAPIClient(
            base_url="http://testserver",
            access_token="",
        )
