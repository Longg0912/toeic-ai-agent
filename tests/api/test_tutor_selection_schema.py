
"""Tests for Tutor text-selection context schemas."""

import pytest
from pydantic import ValidationError

from backend.app.schemas.tutor import (
    TutorChatRequest,
    TutorSelectionContext,
)


def test_selection_context_accepts_general_text() -> None:
    context = TutorSelectionContext(
        selected_text="be eligible for",
        source_type="general",
    )

    assert context.selected_text == "be eligible for"
    assert context.source_type == "general"
    assert context.quiz_session_id is None
    assert context.quiz_item_id is None


def test_selection_context_accepts_quiz_references() -> None:
    context = TutorSelectionContext(
        selected_text="The manager submitted the report.",
        source_type="quiz_question",
        quiz_session_id=10,
        quiz_item_id=25,
        part_number=5,
    )

    assert context.quiz_session_id == 10
    assert context.quiz_item_id == 25
    assert context.part_number == 5


def test_selection_context_accepts_surrounding_text() -> None:
    context = TutorSelectionContext(
        selected_text="eligible for",
        surrounding_text=(
            "Participants will be eligible for additional benefits."
        ),
    )

    assert context.surrounding_text == (
        "Participants will be eligible for additional benefits."
    )


def test_selection_context_normalizes_whitespace() -> None:
    context = TutorSelectionContext(
        selected_text="  eligible for  ",
        surrounding_text="  surrounding sentence  ",
    )

    assert context.selected_text == "eligible for"
    assert context.surrounding_text == "surrounding sentence"


@pytest.mark.parametrize(
    "selected_text",
    [
        "",
        " ",
        "\n\t",
    ],
)
def test_selection_context_rejects_empty_selection(
    selected_text: str,
) -> None:
    with pytest.raises(ValidationError):
        TutorSelectionContext(
            selected_text=selected_text,
        )


def test_selection_context_rejects_too_long_selection() -> None:
    with pytest.raises(ValidationError):
        TutorSelectionContext(
            selected_text="A" * 2001,
        )


def test_selection_context_rejects_too_long_surrounding_text() -> None:
    with pytest.raises(ValidationError):
        TutorSelectionContext(
            selected_text="selected text",
            surrounding_text="A" * 6001,
        )


@pytest.mark.parametrize(
    "source_type",
    [
        "unknown",
        "quiz",
        "part_5",
    ],
)
def test_selection_context_rejects_unknown_source_type(
    source_type: str,
) -> None:
    with pytest.raises(ValidationError):
        TutorSelectionContext(
            selected_text="selected text",
            source_type=source_type,
        )


@pytest.mark.parametrize(
    "part_number",
    [
        4,
        8,
        0,
    ],
)
def test_selection_context_rejects_invalid_part_number(
    part_number: int,
) -> None:
    with pytest.raises(ValidationError):
        TutorSelectionContext(
            selected_text="selected text",
            part_number=part_number,
        )


def test_selection_context_requires_quiz_ids_together() -> None:
    with pytest.raises(ValidationError):
        TutorSelectionContext(
            selected_text="selected text",
            quiz_session_id=10,
        )

    with pytest.raises(ValidationError):
        TutorSelectionContext(
            selected_text="selected text",
            quiz_item_id=25,
        )


def test_selection_context_rejects_non_positive_quiz_ids() -> None:
    with pytest.raises(ValidationError):
        TutorSelectionContext(
            selected_text="selected text",
            quiz_session_id=0,
            quiz_item_id=25,
        )


def test_chat_request_accepts_selection_context() -> None:
    request = TutorChatRequest(
        message="Cụm từ này có nghĩa là gì?",
        selection_context={
            "selected_text": "be eligible for",
            "source_type": "reading_passage",
            "part_number": 7,
            "surrounding_text": (
                "Employees are eligible for additional benefits."
            ),
        },
    )

    assert request.message == "Cụm từ này có nghĩa là gì?"
    assert request.selection_context is not None
    assert request.selection_context.selected_text == "be eligible for"


def test_chat_request_accepts_normal_chat_without_selection() -> None:
    request = TutorChatRequest(
        message="Giải thích thì hiện tại hoàn thành.",
    )

    assert request.selection_context is None


def test_chat_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        TutorChatRequest(
            message="Explain this.",
            unknown_field="not allowed",
        )


def test_chat_request_rejects_empty_message() -> None:
    with pytest.raises(ValidationError):
        TutorChatRequest(
            message="   ",
        )
