"""Tests for the TOEIC Tutor API client."""

import json

import httpx
import pytest

from frontend.tutor_api_client import (
    TutorAPIClient,
    TutorAPIError,
)


def make_client(handler) -> TutorAPIClient:
    transport = httpx.MockTransport(handler)

    return TutorAPIClient(
        base_url="http://testserver",
        access_token="test-access-token",
        transport=transport,
    )


def make_chat_response() -> dict:
    return {
        "chat_session_id": 10,
        "title": "TOEIC Tutor",
        "user_message": {
            "id": 101,
            "role": "user",
            "content": "Explain this text.",
            "created_at": "2026-11-23T10:00:00",
        },
        "assistant_message": {
            "id": 102,
            "role": "assistant",
            "content": "Here is the explanation.",
            "created_at": "2026-11-23T10:00:01",
        },
    }


def test_send_message_without_selection_context() -> None:
    """Existing chat requests must remain compatible."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/tutor/chat"

        body = json.loads(request.content)

        assert body == {
            "message": "Hello tutor",
        }

        return httpx.Response(
            200,
            json=make_chat_response(),
        )

    client = make_client(handler)

    try:
        result = client.send_message("  Hello tutor  ")

        assert result["chat_session_id"] == 10
        assert result["assistant_message"]["content"] == (
            "Here is the explanation."
        )
    finally:
        client.close()


def test_send_message_sends_selection_context() -> None:
    """Selection context must be included in the chat payload."""

    selection_context = {
        "selected_text": "is responsible for",
        "source_type": "quiz_question",
        "quiz_session_id": 20,
        "quiz_item_id": 30,
        "part_number": 5,
        "surrounding_text": (
            "The manager is responsible for the project."
        ),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/tutor/chat"
        assert request.headers["Authorization"] == (
            "Bearer test-access-token"
        )

        body = json.loads(request.content)

        assert body == {
            "message": "Explain the selected phrase.",
            "selection_context": selection_context,
        }

        return httpx.Response(
            200,
            json=make_chat_response(),
        )

    client = make_client(handler)

    try:
        result = client.send_message(
            "Explain the selected phrase.",
            selection_context=selection_context,
        )

        assert result["chat_session_id"] == 10
    finally:
        client.close()


def test_send_message_sends_chat_session_and_selection_context() -> None:
    """Follow-up messages must retain the chat session ID."""

    selection_context = {
        "selected_text": "annual report",
        "source_type": "reading_passage",
        "part_number": 7,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)

        assert body == {
            "message": "Explain this phrase further.",
            "chat_session_id": 10,
            "selection_context": selection_context,
        }

        return httpx.Response(
            200,
            json=make_chat_response(),
        )

    client = make_client(handler)

    try:
        result = client.send_message(
            "Explain this phrase further.",
            chat_session_id=10,
            selection_context=selection_context,
        )

        assert result["chat_session_id"] == 10
    finally:
        client.close()


@pytest.mark.parametrize(
    "selection_context",
    [
        {},
        {
            "selected_text": "   ",
            "source_type": "general",
        },
        {
            "selected_text": "word",
            "source_type": "invalid",
        },
        {
            "selected_text": "word",
            "source_type": "general",
            "quiz_session_id": 10,
        },
        {
            "selected_text": "word",
            "source_type": "general",
            "quiz_item_id": 20,
        },
        {
            "selected_text": "word",
            "source_type": "general",
            "quiz_session_id": True,
            "quiz_item_id": 20,
        },
        {
            "selected_text": "word",
            "source_type": "general",
            "part_number": 4,
        },
        {
            "selected_text": "word",
            "source_type": "general",
            "part_number": True,
        },
        {
            "selected_text": "word",
            "source_type": "general",
            "surrounding_text": 123,
        },
        {
            "selected_text": "word",
            "source_type": "general",
            "unknown_field": "unexpected",
        },
    ],
)
def test_send_message_rejects_invalid_selection_context(
    selection_context: dict,
) -> None:
    """Invalid selection contexts must be rejected locally."""

    client = make_client(
        lambda request: httpx.Response(
            200,
            json=make_chat_response(),
        )
    )

    try:
        with pytest.raises(ValueError):
            client.send_message(
                "Explain this.",
                selection_context=selection_context,
            )
    finally:
        client.close()


def test_send_message_rejects_non_dictionary_selection_context() -> None:
    """Selection context must be a dictionary."""

    client = make_client(
        lambda request: httpx.Response(
            200,
            json=make_chat_response(),
        )
    )

    try:
        with pytest.raises(ValueError):
            client.send_message(
                "Explain this.",
                selection_context="not a dictionary",
            )
    finally:
        client.close()


def test_send_message_rejects_selection_context_over_2000_chars() -> None:
    """Selected text must respect the backend length limit."""

    client = make_client(
        lambda request: httpx.Response(
            200,
            json=make_chat_response(),
        )
    )

    try:
        with pytest.raises(ValueError):
            client.send_message(
                "Explain this.",
                selection_context={
                    "selected_text": "a" * 2001,
                    "source_type": "general",
                },
            )
    finally:
        client.close()


def test_send_message_rejects_surrounding_text_over_6000_chars() -> None:
    """Surrounding text must respect the backend length limit."""

    client = make_client(
        lambda request: httpx.Response(
            200,
            json=make_chat_response(),
        )
    )

    try:
        with pytest.raises(ValueError):
            client.send_message(
                "Explain this.",
                selection_context={
                    "selected_text": "word",
                    "source_type": "general",
                    "surrounding_text": "a" * 6001,
                },
            )
    finally:
        client.close()

def test_list_sessions_returns_parsed_sessions() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/tutor/sessions"
        assert request.url.params["limit"] == "50"
        assert request.url.params["offset"] == "0"
        assert request.headers["Authorization"] == (
            "Bearer test-access-token"
        )
        return httpx.Response(200, json={
            "items": [{
                "id": 7,
                "title": "TOEIC Part 5",
                "created_at": "2026-11-23T10:00:00",
                "updated_at": "2026-11-23T10:01:00",
                "message_count": 4,
            }],
            "total": 1, "limit": 50, "offset": 0,
        })

    client = make_client(handler)
    try:
        result = client.list_sessions(limit=50, offset=0)
        assert result["total"] == 1
        assert result["items"][0]["id"] == 7
        assert result["items"][0]["message_count"] == 4
    finally:
        client.close()


@pytest.mark.parametrize(
    ("limit", "offset"),
    [(0, 0), (51, 0), (True, 0), (20, -1), (20, True)],
)
def test_list_sessions_rejects_invalid_pagination(
    limit: int, offset: int,
) -> None:
    client = make_client(lambda request: httpx.Response(200, json={}))
    try:
        with pytest.raises(ValueError):
            client.list_sessions(limit=limit, offset=offset)
    finally:
        client.close()
