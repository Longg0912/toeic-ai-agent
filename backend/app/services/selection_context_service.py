
"""Build secure context for text-selection AI tutoring."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.db.models.quiz import QuizItem, QuizSession
from backend.app.schemas.tutor import TutorSelectionContext


class SelectionContextNotFoundError(Exception):
    """Raised when the requested quiz item is unavailable to the user."""


class SelectionTextMismatchError(Exception):
    """Raised when selected text does not belong to the requested item."""


def _normalize_text(value: str) -> str:
    """Normalize whitespace and case for selection matching."""

    return re.sub(r"\s+", " ", value).strip().casefold()


def _contains_selection(source: str, selected_text: str) -> bool:
    """Check whether selected text exists in a source string."""

    normalized_source = _normalize_text(source)
    normalized_selection = _normalize_text(selected_text)

    if not normalized_source or not normalized_selection:
        return False

    return normalized_selection in normalized_source


def _get_options(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    """Return safe option data from a frozen question snapshot."""

    raw_options = snapshot.get("options", [])

    if not isinstance(raw_options, list):
        return []

    options: list[dict[str, str]] = []

    for option in raw_options:
        if not isinstance(option, dict):
            continue

        option_key = option.get("option_key")
        content = option.get("content")

        if (
            isinstance(option_key, str)
            and isinstance(content, str)
        ):
            options.append(
                {
                    "option_key": option_key,
                    "content": content,
                }
            )

    return options


def build_selection_context(
    db: Session,
    *,
    student_id: int,
    context: TutorSelectionContext,
) -> str:
    """Build a trusted AI context for selected text.

    For quiz-linked selections, all learning content is loaded from
    the database. Client-provided surrounding text is not trusted.

    Correct answers and explanations are only included after the
    quiz session has been submitted.
    """

    if context.quiz_session_id is None:
        parts = [
            "SOURCE: General learning content",
            "SELECTED TEXT:",
            context.selected_text,
        ]

        if context.surrounding_text:
            parts.extend(
                [
                    "SURROUNDING TEXT:",
                    context.surrounding_text,
                ]
            )

        return "\n".join(parts)

    statement = (
        select(QuizItem)
        .join(
            QuizSession,
            QuizSession.id == QuizItem.quiz_session_id,
        )
        .where(
            QuizItem.id == context.quiz_item_id,
            QuizSession.id == context.quiz_session_id,
            QuizSession.user_id == student_id,
        )
        .options(
            selectinload(QuizItem.session),
            selectinload(QuizItem.attempts),
        )
    )

    quiz_item = db.scalar(statement)

    if quiz_item is None:
        raise SelectionContextNotFoundError(
            "Quiz item not found."
        )

    session = quiz_item.session
    snapshot = quiz_item.question_snapshot

    if not isinstance(snapshot, dict):
        raise SelectionContextNotFoundError(
            "Quiz question content is unavailable."
        )

    question_content = snapshot.get("content")

    if not isinstance(question_content, str):
        raise SelectionContextNotFoundError(
            "Quiz question content is unavailable."
        )

    options = _get_options(snapshot)

    # Verify the selected text against the actual quiz item.
    searchable_sources = [question_content]

    searchable_sources.extend(
        option["content"]
        for option in options
    )

    if context.source_type == "quiz_question":
        searchable_sources = [question_content]

    elif context.source_type == "quiz_option":
        searchable_sources = [
            option["content"]
            for option in options
        ]

    elif context.source_type == "explanation":
        explanation = snapshot.get("explanation")

        if (
            session.status != "submitted"
            or not isinstance(explanation, str)
        ):
            raise SelectionContextNotFoundError(
                "Explanation is unavailable before submission."
            )

        searchable_sources = [explanation]

    if not any(
        _contains_selection(source, context.selected_text)
        for source in searchable_sources
    ):
        raise SelectionTextMismatchError(
            "Selected text does not belong to this quiz item."
        )

    # Use the actual Part number from the database.
    question_part = quiz_item.question.part

    if (
        context.part_number is not None
        and context.part_number != question_part
    ):
        raise SelectionTextMismatchError(
            "Part number does not match the quiz question."
        )

    lines = [
        "SOURCE: TOEIC Quiz Practice",
        f"QUIZ SESSION ID: {session.id}",
        f"QUIZ SESSION STATUS: {session.status}",
        f"QUESTION POSITION: {quiz_item.position}",
        f"TOEIC PART: {question_part}",
        "",
        "SELECTED TEXT:",
        context.selected_text,
        "",
        "QUESTION CONTENT:",
        question_content,
        "",
        "ANSWER OPTIONS:",
    ]

    for option in options:
        lines.append(
            f'{option["option_key"]}. {option["content"]}'
        )

    # Include the student's latest submitted answer if available.
    attempts = sorted(
        quiz_item.attempts,
        key=lambda attempt: attempt.attempt_number,
    )

    if attempts:
        latest_attempt = attempts[-1]

        lines.extend(
            [
                "",
                "STUDENT'S LATEST ANSWER:",
                latest_attempt.selected_option_key,
            ]
        )

    # Never expose the answer key during an unfinished quiz.
    if session.status == "submitted":
        lines.extend(
            [
                "",
                "OFFICIAL CORRECT ANSWER:",
                quiz_item.answer_key_snapshot,
            ]
        )

        explanation = snapshot.get("explanation")

        if isinstance(explanation, str) and explanation.strip():
            lines.extend(
                [
                    "",
                    "EXISTING EXPLANATION:",
                    explanation,
                ]
            )

    return "\n".join(lines)
