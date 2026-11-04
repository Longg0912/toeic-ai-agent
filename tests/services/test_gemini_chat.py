
"""Unit tests for Gemini multi-turn chat service."""

from types import SimpleNamespace

import pytest

from backend.app.services.gemini_tutor import (
    CHAT_SYSTEM_INSTRUCTION,
    GeminiConfigurationError,
    GeminiServiceError,
    chat_with_tutor,
)


def test_chat_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chat service requires a Gemini API key."""

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(GeminiConfigurationError):
        chat_with_tutor([
            {
                "role": "user",
                "content": "Explain since and for.",
            }
        ])


def test_chat_requires_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chat service requires a model name."""

    monkeypatch.setenv(
        "GEMINI_API_KEY",
        "test-api-key",
    )

    monkeypatch.setenv("GEMINI_MODEL", "")

    with pytest.raises(GeminiConfigurationError):
        chat_with_tutor([
            {
                "role": "user",
                "content": "Explain since and for.",
            }
        ])


def test_chat_rejects_empty_conversation() -> None:
    """An empty conversation is invalid."""

    with pytest.raises(ValueError):
        chat_with_tutor([])


def test_chat_rejects_invalid_role() -> None:
    """Only user and assistant roles are supported."""

    with pytest.raises(ValueError):
        chat_with_tutor([
            {
                "role": "system",
                "content": "Invalid role.",
            }
        ])


def test_chat_rejects_empty_message() -> None:
    """Messages must contain non-empty text."""

    with pytest.raises(ValueError):
        chat_with_tutor([
            {
                "role": "user",
                "content": "   ",
            }
        ])


def test_chat_sends_multi_turn_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Previous user and assistant messages reach Gemini."""

    monkeypatch.setenv(
        "GEMINI_API_KEY",
        "test-api-key",
    )

    monkeypatch.setenv(
        "GEMINI_MODEL",
        "gemini-test-model",
    )

    captured: dict[str, object] = {}

    class FakeModels:
        def generate_content(self, **kwargs: object):
            captured.update(kwargs)

            return SimpleNamespace(
                text="Since is used with a starting point.",
            )

    class FakeClient:
        def __init__(self, api_key: str):
            assert api_key == "test-api-key"
            self.models = FakeModels()

    monkeypatch.setattr(
        "backend.app.services.gemini_tutor.genai.Client",
        FakeClient,
    )

    result = chat_with_tutor([
        {
            "role": "user",
            "content": "Explain since and for.",
        },
        {
            "role": "assistant",
            "content": "Since uses a starting point.",
        },
        {
            "role": "user",
            "content": "Give me another example.",
        },
    ])

    assert result == "Since is used with a starting point."

    contents = captured["contents"]

    assert [item.role for item in contents] == [
        "user",
        "model",
        "user",
    ]

    assert [
        item.parts[0].text
        for item in contents
    ] == [
        "Explain since and for.",
        "Since uses a starting point.",
        "Give me another example.",
    ]

    config = captured["config"]

    assert config.system_instruction == CHAT_SYSTEM_INSTRUCTION


def test_chat_handles_empty_gemini_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty Gemini response is treated as a service error."""

    monkeypatch.setenv(
        "GEMINI_API_KEY",
        "test-api-key",
    )

    class FakeModels:
        def generate_content(self, **kwargs: object):
            return SimpleNamespace(text=None)

    class FakeClient:
        def __init__(self, api_key: str):
            self.models = FakeModels()

    monkeypatch.setattr(
        "backend.app.services.gemini_tutor.genai.Client",
        FakeClient,
    )

    with pytest.raises(GeminiServiceError):
        chat_with_tutor([
            {
                "role": "user",
                "content": "Explain present perfect.",
            }
        ])


def test_chat_handles_gemini_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gemini SDK errors are converted to service errors."""

    monkeypatch.setenv(
        "GEMINI_API_KEY",
        "test-api-key",
    )

    class FakeModels:
        def generate_content(self, **kwargs: object):
            raise RuntimeError("Simulated Gemini failure")

    class FakeClient:
        def __init__(self, api_key: str):
            self.models = FakeModels()

    monkeypatch.setattr(
        "backend.app.services.gemini_tutor.genai.Client",
        FakeClient,
    )

    with pytest.raises(GeminiServiceError):
        chat_with_tutor([
            {
                "role": "user",
                "content": "Explain present perfect.",
            }
        ])
