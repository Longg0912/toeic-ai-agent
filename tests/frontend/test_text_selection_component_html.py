"""Static regression checks for the browser text-selection component."""

from pathlib import Path


HTML_PATH = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "components"
    / "text_selection_tutor"
    / "index.html"
)


def test_component_uses_content_based_frame_height() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")
    assert "root.getBoundingClientRect().height" in html
    assert "new ResizeObserver(setFrameHeight)" in html


def test_ask_ai_toolbar_is_hidden_until_text_is_selected() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")
    assert "#selection-toolbar" in html
    assert "display: none" in html
    assert "toolbar.classList.add(\"visible\")" in html


def test_selection_change_event_is_supported() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")
    assert 'document.addEventListener("selectionchange"' in html
    assert 'root.addEventListener("mouseup"' in html


def test_selection_is_preserved_when_clicking_ask_ai() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")
    assert 'askButton.addEventListener("pointerdown"' in html
    assert "event.preventDefault()" in html


def test_component_keeps_supported_quiz_source_types() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")
    assert '"quiz_question"' in html
    assert '"quiz_option"' in html
