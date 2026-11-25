"""Streamlit custom component for selecting TOEIC question text."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit.components.v1 as components


_COMPONENT_DIR = (
    Path(__file__).resolve().parent
    / "components"
    / "text_selection_tutor"
)

_component = components.declare_component(
    "toeic_text_selection_tutor",
    path=str(_COMPONENT_DIR),
)

_ALLOWED_SOURCE_TYPES = {
    "quiz_question",
    "quiz_option",
}


def _normalize_selection_event(value: Any) -> dict[str, str] | None:
    """Validate the value returned by the browser component."""

    if value is None:
        return None

    if not isinstance(value, dict):
        return None

    selected_text = value.get("selected_text")
    source_type = value.get("source_type")
    surrounding_text = value.get("surrounding_text", "")
    event_id = value.get("event_id")

    if not isinstance(selected_text, str):
        return None

    selected_text = selected_text.strip()

    if not selected_text or len(selected_text) > 2000:
        return None

    if source_type not in _ALLOWED_SOURCE_TYPES:
        return None

    if not isinstance(surrounding_text, str):
        return None

    surrounding_text = surrounding_text.strip()

    if len(surrounding_text) > 6000:
        surrounding_text = surrounding_text[:6000]

    if not isinstance(event_id, str) or not event_id.strip():
        return None

    if len(event_id) > 80:
        return None

    return {
        "selected_text": selected_text,
        "source_type": source_type,
        "surrounding_text": surrounding_text,
        "event_id": event_id,
    }


def render_text_selection_component(
    question_text: str,
    options: list[dict[str, str]],
    *,
    key: str,
    height: int = 300,
) -> dict[str, str] | None:
    """Render selectable question and option text.

    The component returns a normalized selection event only after the
    learner selects text and presses the component's "Hỏi AI" button.
    """

    if not isinstance(question_text, str):
        raise ValueError("question_text phải là chuỗi.")

    if not isinstance(options, list):
        raise ValueError("options phải là danh sách.")

    normalized_options: list[dict[str, str]] = []

    for option in options:
        if not isinstance(option, dict):
            raise ValueError("Mỗi option phải là dictionary.")

        option_key = option.get("option_key")
        content = option.get("content")

        if (
            not isinstance(option_key, str)
            or not option_key.strip()
            or not isinstance(content, str)
        ):
            raise ValueError("Dữ liệu option không hợp lệ.")

        normalized_options.append(
            {
                "option_key": option_key.strip(),
                "content": content,
            }
        )

    if isinstance(height, bool) or not isinstance(height, int):
        raise ValueError("height phải là số nguyên.")

    if height < 180 or height > 900:
        raise ValueError("height phải nằm trong khoảng 180 đến 900.")

    value = _component(
        question_text=question_text,
        options=normalized_options,
        height=height,
        key=key,
        default=None,
    )

    return _normalize_selection_event(value)
