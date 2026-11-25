
"""Tests for the text-selection context builder."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.app.schemas.tutor import TutorSelectionContext
from backend.app.services.selection_context_service import (
    SelectionContextNotFoundError,
    SelectionTextMismatchError,
    build_selection_context,
)


def _make_quiz_item(
    *,
    status: str = "in_progress",
    attempts: list | None = None,
):
    """Create a lightweight quiz item for service tests."""

    snapshot = {
        "content": (
            "The manager asked employees to submit reports by Friday."
        ),
        "difficulty": 2,
        "options": [
            {
                "option_key": "A",
                "content": "at",
            },
            {
                "option_key": "B",
                "content": "by",
            },
            {
                "option_key": "C",
                "content": "during",
            },
            {
                "option_key": "D",
                "content": "while",
            },
        ],
        "skill_codes": ["PREPOSITIONS"],
        "explanation": (
            "By expresses a deadline."
        ),
    }

    question = SimpleNamespace(part=5)

    session = SimpleNamespace(
        id=10,
        status=status,
    )

    return SimpleNamespace(
        id=25,
        position=1,
        question_snapshot=snapshot,
        answer_key_snapshot="B",
        question=question,
        session=session,
        attempts=attempts or [],
    )


def _make_context(
    *,
    selected_text: str = "by Friday",
    source_type: str = "quiz_question",
) -> TutorSelectionContext:
    return TutorSelectionContext(
        selected_text=selected_text,
        source_type=source_type,
        quiz_session_id=10,
        quiz_item_id=25,
        part_number=5,
    )


def test_general_selection_context_does_not_query_database() -> None:
    db = MagicMock()

    context = TutorSelectionContext(
        selected_text="eligible for",
        source_type="general",
        surrounding_text="Employees are eligible for benefits.",
    )

    result = build_selection_context(
        db,
        student_id=1,
        context=context,
    )

    assert "eligible for" in result
    assert "Employees are eligible for benefits." in result
    db.scalar.assert_not_called()


def test_quiz_context_loads_question_and_options() -> None:
    db = MagicMock()
    db.scalar.return_value = _make_quiz_item()

    result = build_selection_context(
        db,
        student_id=1,
        context=_make_context(),
    )

    assert "TOEIC PART: 5" in result
    assert "by Friday" in result
    assert "QUESTION CONTENT:" in result
    assert "B. by" in result


def test_unsubmitted_quiz_does_not_expose_answer_key() -> None:
    db = MagicMock()
    db.scalar.return_value = _make_quiz_item(
        status="in_progress",
    )

    result = build_selection_context(
        db,
        student_id=1,
        context=_make_context(),
    )

    assert "OFFICIAL CORRECT ANSWER:" not in result
    assert "EXISTING EXPLANATION:" not in result
    assert "B. by" in result


def test_submitted_quiz_includes_answer_and_explanation() -> None:
    db = MagicMock()
    db.scalar.return_value = _make_quiz_item(
        status="submitted",
    )

    result = build_selection_context(
        db,
        student_id=1,
        context=_make_context(),
    )

    assert "OFFICIAL CORRECT ANSWER:" in result
    assert "B" in result
    assert "By expresses a deadline." in result


def test_quiz_context_includes_latest_student_answer() -> None:
    db = MagicMock()

    attempts = [
        SimpleNamespace(
            attempt_number=1,
            selected_option_key="A",
        ),
        SimpleNamespace(
            attempt_number=2,
            selected_option_key="B",
        ),
    ]

    db.scalar.return_value = _make_quiz_item(
        attempts=attempts,
    )

    result = build_selection_context(
        db,
        student_id=1,
        context=_make_context(),
    )

    assert "STUDENT'S LATEST ANSWER:" in result
    assert result.endswith("B")


def test_quiz_context_rejects_selection_not_in_question() -> None:
    db = MagicMock()
    db.scalar.return_value = _make_quiz_item()

    context = _make_context(
        selected_text="This text does not exist.",
    )

    with pytest.raises(SelectionTextMismatchError):
        build_selection_context(
            db,
            student_id=1,
            context=context,
        )


def test_quiz_option_selection_matches_option_content() -> None:
    db = MagicMock()
    db.scalar.return_value = _make_quiz_item()

    context = _make_context(
        selected_text="during",
        source_type="quiz_option",
    )

    result = build_selection_context(
        db,
        student_id=1,
        context=context,
    )

    assert "during" in result


def test_quiz_option_selection_rejects_question_only_text() -> None:
    db = MagicMock()
    db.scalar.return_value = _make_quiz_item()

    context = _make_context(
        selected_text="The manager",
        source_type="quiz_option",
    )

    with pytest.raises(SelectionTextMismatchError):
        build_selection_context(
            db,
            student_id=1,
            context=context,
        )


def test_context_rejects_mismatched_part_number() -> None:
    db = MagicMock()
    db.scalar.return_value = _make_quiz_item()

    context = TutorSelectionContext(
        selected_text="by Friday",
        source_type="quiz_question",
        quiz_session_id=10,
        quiz_item_id=25,
        part_number=7,
    )

    with pytest.raises(SelectionTextMismatchError):
        build_selection_context(
            db,
            student_id=1,
            context=context,
        )


def test_context_rejects_unknown_or_other_users_quiz_item() -> None:
    db = MagicMock()
    db.scalar.return_value = None

    with pytest.raises(SelectionContextNotFoundError):
        build_selection_context(
            db,
            student_id=999,
            context=_make_context(),
        )


def test_explanation_is_not_available_before_submission() -> None:
    db = MagicMock()
    db.scalar.return_value = _make_quiz_item(
        status="in_progress",
    )

    context = _make_context(
        selected_text="By expresses a deadline.",
        source_type="explanation",
    )

    with pytest.raises(SelectionContextNotFoundError):
        build_selection_context(
            db,
            student_id=1,
            context=context,
        )


def test_explanation_can_be_selected_after_submission() -> None:
    db = MagicMock()
    db.scalar.return_value = _make_quiz_item(
        status="submitted",
    )

    context = _make_context(
        selected_text="By expresses a deadline.",
        source_type="explanation",
    )

    result = build_selection_context(
        db,
        student_id=1,
        context=context,
    )

    assert "By expresses a deadline." in result
