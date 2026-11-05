
"""Unit tests for Gemini multi-turn chat service."""

from types import SimpleNamespace

import pytest
from google.genai import types

from backend.app.services.tutor_tools import ToolInputError
from backend.app.services.gemini_tutor import (
    CHAT_SYSTEM_INSTRUCTION,
    GeminiConfigurationError,
    GeminiServiceError,
    chat_with_tutor,
)
from backend.app.services.gemini_tutor import (
    build_gemini_tool,
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
def test_build_gemini_tool_contains_all_registered_tools() -> None:
    """Gemini declarations contain all six registered tools."""

    from backend.app.services.tutor_tools import (
        TUTOR_TOOL_REGISTRY,
    )

    gemini_tool = build_gemini_tool()

    declared_names = {
        declaration.name
        for declaration in gemini_tool.function_declarations
    }

    registered_names = {
        definition.name
        for definition in TUTOR_TOOL_REGISTRY.get_all()
    }

    assert declared_names == registered_names

    assert len(declared_names) == 6


def test_gemini_tool_declarations_exclude_student_id() -> None:
    """Gemini must not receive student_id as a tool argument."""

    gemini_tool = build_gemini_tool()

    for declaration in gemini_tool.function_declarations:
        schema = declaration.parameters_json_schema

        properties = schema.get("properties", {})

        assert "student_id" not in properties

        assert "user_id" not in properties


def test_gemini_tool_declarations_preserve_required_arguments() -> None:
    """Required arguments are preserved from Tool Registry."""

    from backend.app.services.tutor_tools import (
        TUTOR_TOOL_REGISTRY,
    )

    gemini_tool = build_gemini_tool()

    declarations = {
        declaration.name: declaration
        for declaration in gemini_tool.function_declarations
    }

    for definition in TUTOR_TOOL_REGISTRY.get_all():
        declaration = declarations[definition.name]

        assert (
            declaration.parameters_json_schema["required"]
            == definition.parameters.get("required", [])
        )


def test_gemini_tool_declarations_preserve_parameter_types() -> None:
    """Parameter types remain consistent with the registry."""

    gemini_tool = build_gemini_tool()

    for declaration in gemini_tool.function_declarations:
        schema = declaration.parameters_json_schema

        for name, property_schema in schema.get(
            "properties",
            {},
        ).items():
            assert property_schema["type"] in {
                "string",
                "integer",
                "boolean",
                "number",
                "array",
                "object",
            }

def test_chat_executes_gemini_function_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Backend executes Gemini function calls with authenticated ID."""

    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")

    captured_calls = []
    captured_requests = []

    function_call = types.FunctionCall(
        name="get_student_profile",
        args={},
        id="call-001",
    )

    first_response = SimpleNamespace(
        text=None,
        candidates=[
            SimpleNamespace(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=function_call,
                        )
                    ],
                )
            )
        ],
    )

    second_response = SimpleNamespace(
        text="Bạn chưa thiết lập hồ sơ học tập.",
        candidates=[],
    )

    class FakeModels:
        def __init__(self):
            self.responses = [
                first_response,
                second_response,
            ]

        def generate_content(self, **kwargs):
            captured_requests.append(kwargs)
            return self.responses.pop(0)

    class FakeClient:
        def __init__(self, api_key):
            self.models = FakeModels()

    def fake_execute(
        name,
        arguments,
        db,
        student_id,
    ):
        captured_calls.append(
            {
                "name": name,
                "arguments": arguments,
                "db": db,
                "student_id": student_id,
            }
        )

        return {
            "profile_found": False,
            "target_score": None,
        }

    monkeypatch.setattr(
        "backend.app.services.gemini_tutor.genai.Client",
        FakeClient,
    )

    monkeypatch.setattr(
        "backend.app.services.gemini_tutor."
        "TUTOR_TOOL_REGISTRY.execute",
        fake_execute,
    )

    fake_db = object()

    result = chat_with_tutor(
        [
            {
                "role": "user",
                "content": "Hãy kiểm tra hồ sơ học tập của tôi.",
            }
        ],
        db=fake_db,
        student_id=123,
    )

    assert result == "Bạn chưa thiết lập hồ sơ học tập."

    assert len(captured_calls) == 1

    assert captured_calls[0]["name"] == "get_student_profile"

    assert captured_calls[0]["student_id"] == 123

    assert captured_calls[0]["db"] is fake_db

    assert len(captured_requests) == 2

    function_response_content = (
        captured_requests[1]["contents"][-1]
    )

    function_response = (
        function_response_content.parts[0].function_response
    )

    assert function_response.name == "get_student_profile"

    assert function_response.response == {
        "result": {
            "profile_found": False,
            "target_score": None,
        }
    }


def test_chat_executes_multiple_function_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multiple tool calls in one Gemini response are executed."""

    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")

    executed_names = []

    first_response = SimpleNamespace(
        text=None,
        candidates=[
            SimpleNamespace(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name="get_student_profile",
                                args={},
                                id="call-001",
                            )
                        ),
                        types.Part(
                            function_call=types.FunctionCall(
                                name="get_weak_skills",
                                args={"limit": 3},
                                id="call-002",
                            )
                        ),
                    ],
                )
            )
        ],
    )

    final_response = SimpleNamespace(
        text="Đây là kết quả phân tích của bạn.",
        candidates=[],
    )

    class FakeModels:
        def __init__(self):
            self.responses = [
                first_response,
                final_response,
            ]

        def generate_content(self, **kwargs):
            return self.responses.pop(0)

    class FakeClient:
        def __init__(self, api_key):
            self.models = FakeModels()

    def fake_execute(name, arguments, db, student_id):
        executed_names.append(name)
        return {"success": True}

    monkeypatch.setattr(
        "backend.app.services.gemini_tutor.genai.Client",
        FakeClient,
    )

    monkeypatch.setattr(
        "backend.app.services.gemini_tutor."
        "TUTOR_TOOL_REGISTRY.execute",
        fake_execute,
    )

    result = chat_with_tutor(
        [
            {
                "role": "user",
                "content": "Phân tích tình hình học tập của tôi.",
            }
        ],
        db=object(),
        student_id=123,
    )

    assert result == "Đây là kết quả phân tích của bạn."

    assert executed_names == [
        "get_student_profile",
        "get_weak_skills",
    ]


def test_chat_returns_tool_validation_error_to_gemini(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid tool arguments are returned safely to Gemini."""

    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")

    first_response = SimpleNamespace(
        text=None,
        candidates=[
            SimpleNamespace(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name="get_weak_skills",
                                args={"limit": "invalid"},
                                id="call-001",
                            )
                        )
                    ],
                )
            )
        ],
    )

    final_response = SimpleNamespace(
        text="Tôi chưa thể lấy dữ liệu kỹ năng.",
        candidates=[],
    )

    class FakeModels:
        def __init__(self):
            self.responses = [
                first_response,
                final_response,
            ]

        def generate_content(self, **kwargs):
            return self.responses.pop(0)

    class FakeClient:
        def __init__(self, api_key):
            self.models = FakeModels()

    def fake_execute(name, arguments, db, student_id):
        raise ToolInputError(
            "Argument 'limit' must be an integer."
        )

    monkeypatch.setattr(
        "backend.app.services.gemini_tutor.genai.Client",
        FakeClient,
    )

    monkeypatch.setattr(
        "backend.app.services.gemini_tutor."
        "TUTOR_TOOL_REGISTRY.execute",
        fake_execute,
    )

    result = chat_with_tutor(
        [
            {
                "role": "user",
                "content": "Kiểm tra kỹ năng yếu của tôi.",
            }
        ],
        db=object(),
        student_id=123,
    )

    assert result == "Tôi chưa thể lấy dữ liệu kỹ năng."