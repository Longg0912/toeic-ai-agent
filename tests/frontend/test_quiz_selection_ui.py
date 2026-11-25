"""Tests for TOEIC quiz text-selection integration helpers."""

import pytest

from frontend.quiz_ui import _build_selection_context


def test_build_selection_context_includes_quiz_references() -> None:
    result = _build_selection_context(
        {
            "selected_text": "by Friday",
            "source_type": "quiz_question",
            "surrounding_text": "Submit the report by Friday.",
            "event_id": "event-1",
        },
        session_id=12,
        item_id=34,
    )

    assert result == {
        "selected_text": "by Friday",
        "source_type": "quiz_question",
        "quiz_session_id": 12,
        "quiz_item_id": 34,
        "part_number": 5,
        "surrounding_text": "Submit the report by Friday.",
    }


def test_build_selection_context_supports_option_selection() -> None:
    result = _build_selection_context(
        {
            "selected_text": "annual report",
            "source_type": "quiz_option",
            "surrounding_text": "A. annual report",
        },
        session_id=1,
        item_id=2,
    )

    assert result["source_type"] == "quiz_option"
    assert result["quiz_session_id"] == 1
    assert result["quiz_item_id"] == 2


@pytest.mark.parametrize(
    ("session_id", "item_id"),
    [
        (0, 1),
        (1, 0),
        (-1, 1),
        (1, -1),
        (True, 1),
        (1, False),
    ],
)
def test_build_selection_context_rejects_invalid_ids(
    session_id: int,
    item_id: int,
) -> None:
    with pytest.raises(ValueError):
        _build_selection_context(
            {
                "selected_text": "text",
                "source_type": "quiz_question",
            },
            session_id=session_id,
            item_id=item_id,
        )


def test_build_selection_context_rejects_empty_selection() -> None:
    with pytest.raises(ValueError, match="Không có nội dung"):
        _build_selection_context(
            {
                "selected_text": "   ",
                "source_type": "quiz_question",
            },
            session_id=1,
            item_id=2,
        )


def test_build_selection_context_rejects_unsupported_source_type() -> None:
    with pytest.raises(ValueError, match="Loại nội dung"):
        _build_selection_context(
            {
                "selected_text": "text",
                "source_type": "general",
            },
            session_id=1,
            item_id=2,
        )


def test_build_selection_context_truncates_surrounding_text() -> None:
    result = _build_selection_context(
        {
            "selected_text": "text",
            "source_type": "quiz_question",
            "surrounding_text": "x" * 7000,
        },
        session_id=1,
        item_id=2,
    )

    assert len(result["surrounding_text"]) == 6000
