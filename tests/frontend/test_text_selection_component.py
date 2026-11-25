"""Tests for the text-selection Streamlit component wrapper."""

import pytest

from frontend.text_selection_component import (
    _normalize_selection_event,
)


def test_normalize_valid_question_selection() -> None:
    result = _normalize_selection_event(
        {
            "selected_text": "  is responsible for  ",
            "source_type": "quiz_question",
            "surrounding_text": "The manager is responsible for the project.",
            "event_id": "event-123",
        }
    )

    assert result == {
        "selected_text": "is responsible for",
        "source_type": "quiz_question",
        "surrounding_text": "The manager is responsible for the project.",
        "event_id": "event-123",
    }


def test_normalize_valid_option_selection() -> None:
    result = _normalize_selection_event(
        {
            "selected_text": "annual report",
            "source_type": "quiz_option",
            "surrounding_text": "A. annual report",
            "event_id": "event-456",
        }
    )

    assert result is not None
    assert result["source_type"] == "quiz_option"


@pytest.mark.parametrize(
    "value",
    [
        "not-a-dictionary",
        {},
        {"selected_text": "word", "source_type": "general", "event_id": "x"},
        {"selected_text": "   ", "source_type": "quiz_question", "event_id": "x"},
        {"selected_text": "a" * 2001, "source_type": "quiz_question", "event_id": "x"},
        {"selected_text": "word", "source_type": "quiz_question", "event_id": ""},
        {"selected_text": "word", "source_type": "quiz_question", "event_id": "x" * 81},
        {"selected_text": "word", "source_type": "quiz_question", "surrounding_text": 123, "event_id": "x"},
    ],
)
def test_normalize_rejects_invalid_selection(value) -> None:
    assert _normalize_selection_event(value) is None


def test_normalize_truncates_surrounding_text() -> None:
    result = _normalize_selection_event(
        {
            "selected_text": "word",
            "source_type": "quiz_question",
            "surrounding_text": "x" * 7000,
            "event_id": "event-789",
        }
    )

    assert result is not None
    assert len(result["surrounding_text"]) == 6000


def test_normalize_none_returns_none() -> None:
    assert _normalize_selection_event(None) is None
