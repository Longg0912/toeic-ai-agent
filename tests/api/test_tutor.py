
"""Integration tests for POST /tutor/explain."""

from collections.abc import Iterator
from hashlib import sha256
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.db.models import (
    Question,
    QuestionOption,
    QuestionSkill,
    Skill,
    User,
)
from backend.app.db.session import make_engine
from backend.app.main import app
from backend.app.security.jwt_tokens import (
    JWTSettings,
    create_access_token,
)
from backend.app.services.gemini_tutor import (
    GeminiConfigurationError,
    GeminiServiceError,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = PROJECT_ROOT / "alembic.ini"

TEST_SECRET = "test-secret-key-that-is-at-least-32-bytes-long"
TEST_SKILL_CODE = "TEST_TUTOR_GRAMMAR"


def _insert_question(
    session: Session,
    *,
    skill_id: int,
    content: str,
    review_status: str = "approved",
    permission_status: str = "granted",
    visibility: str = "public",
    owner_user_id: int | None = None,
    option_keys: tuple[str, ...] = ("A", "B", "C", "D"),
) -> Question:
    """Insert a synthetic TOEIC question for Tutor API tests."""

    question = Question(
        part=5,
        content=content,
        explanation="Test explanation: option B is correct.",
        correct_option_key="B",
        difficulty=2,
        review_status=review_status,
        source_type="ai_generated",
        source_name="tutor-api-test",
        source_reference=f"test:tutor:{content}",
        usage_permission_status=permission_status,
        visibility=visibility,
        owner_user_id=owner_user_id,
        content_hash=sha256(
            content.encode("utf-8")
        ).hexdigest(),
    )

    session.add(question)
    session.flush()

    for key in option_keys:
        session.add(
            QuestionOption(
                question_id=question.id,
                option_key=key,
                content=f"Option {key}",
            )
        )

    session.add(
        QuestionSkill(
            question_id=question.id,
            skill_id=skill_id,
        )
    )

    session.flush()
    return question


@pytest.fixture
def tutor_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[
    tuple[
        TestClient,
        dict[str, int],
        dict[str, str],
        dict[str, str],
    ]
]:
    """Create an isolated database and authenticated test clients."""

    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET)

    database_path = tmp_path / "tutor_api.sqlite3"
    database_url = (
        f"sqlite+pysqlite:///{database_path.as_posix()}"
    )

    test_engine = make_engine(database_url)
    config = Config(str(ALEMBIC_CONFIG))
    previous_overrides = app.dependency_overrides.copy()

    try:
        # Apply real Alembic migrations to the temporary database.
        with test_engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        # Create test users, skill, and questions.
        with Session(test_engine) as session:
            owner = User(
                email="tutor-owner@example.com",
                password_hash="test-only-hash",
                role="student",
                is_active=True,
            )

            other_user = User(
                email="tutor-other@example.com",
                password_hash="test-only-hash",
                role="student",
                is_active=True,
            )

            session.add_all([owner, other_user])
            session.flush()

            owner_id = owner.id
            other_user_id = other_user.id

            skill = Skill(
                code=TEST_SKILL_CODE,
                name="Tutor Test Grammar",
                category="grammar",
            )

            session.add(skill)
            session.flush()

            skill_id = skill.id

            public_question = _insert_question(
                session,
                skill_id=skill_id,
                content="Public approved question.",
            )

            private_question = _insert_question(
                session,
                skill_id=skill_id,
                content="Private owner question.",
                visibility="private",
                owner_user_id=owner_id,
            )

            pending_question = _insert_question(
                session,
                skill_id=skill_id,
                content="Pending question.",
                review_status="pending_review",
            )

            restricted_question = _insert_question(
                session,
                skill_id=skill_id,
                content="Restricted question.",
                permission_status="restricted",
            )

            incomplete_question = _insert_question(
                session,
                skill_id=skill_id,
                content="Incomplete question.",
                option_keys=("A", "B", "C"),
            )

            question_ids = {
                "public": public_question.id,
                "private": private_question.id,
                "pending": pending_question.id,
                "restricted": restricted_question.id,
                "incomplete": incomplete_question.id,
                "owner": owner_id,
                "other_user": other_user_id,
            }

            session.commit()

        # Generate test-only JWT access tokens.
        jwt_settings = JWTSettings(
            secret_key=TEST_SECRET,
        )

        owner_token = create_access_token(
            owner_id,
            settings=jwt_settings,
        )

        other_token = create_access_token(
            other_user_id,
            settings=jwt_settings,
        )

        owner_headers = {
            "Authorization": f"Bearer {owner_token}",
        }

        other_headers = {
            "Authorization": f"Bearer {other_token}",
        }

        # Override the database dependency for API requests.
        def override_get_db() -> Iterator[Session]:
            with Session(test_engine) as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as client:
            yield (
                client,
                question_ids,
                owner_headers,
                other_headers,
            )

    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        test_engine.dispose()


def test_tutor_explain_success(
    tutor_client: tuple[
        TestClient,
        dict[str, int],
        dict[str, str],
        dict[str, str],
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An authorized user receives a Gemini explanation."""

    client, question_ids, owner_headers, _ = tutor_client

    captured_data: dict[str, object] = {}

    def fake_explain(**kwargs: object) -> str:
        """Replace Gemini with a deterministic test response."""

        captured_data.update(kwargs)
        return "Đây là lời giải kiểm thử bằng tiếng Việt."

    monkeypatch.setattr(
        "backend.app.api.routes.tutor.explain_toeic_question",
        fake_explain,
    )

    response = client.post(
        "/tutor/explain",
        json={
            "question_id": question_ids["public"],
        },
        headers=owner_headers,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["question_id"] == question_ids["public"]
    assert data["correct_option_key"] == "B"
    assert data["explanation"] == (
        "Đây là lời giải kiểm thử bằng tiếng Việt."
    )

    # Verify that the official answer came from the database.
    assert captured_data["correct_option_key"] == "B"

    assert captured_data["question_content"] == (
        "Public approved question."
    )

    assert captured_data["existing_explanation"] == (
        "Test explanation: option B is correct."
    )

    options = captured_data["options"]

    assert isinstance(options, list)
    assert [
        option["option_key"]
        for option in options
    ] == ["A", "B", "C", "D"]

    assert captured_data["skill_codes"] == [
        TEST_SKILL_CODE,
    ]


def test_tutor_requires_authentication(
    tutor_client: tuple[
        TestClient,
        dict[str, int],
        dict[str, str],
        dict[str, str],
    ],
) -> None:
    """Requests without JWT must be rejected."""

    client, question_ids, _, _ = tutor_client

    response = client.post(
        "/tutor/explain",
        json={
            "question_id": question_ids["public"],
        },
    )

    assert response.status_code == 401


def test_tutor_question_not_found(
    tutor_client: tuple[
        TestClient,
        dict[str, int],
        dict[str, str],
        dict[str, str],
    ],
) -> None:
    """A nonexistent question returns HTTP 404."""

    client, _, owner_headers, _ = tutor_client

    response = client.post(
        "/tutor/explain",
        json={
            "question_id": 999999,
        },
        headers=owner_headers,
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    "question_type",
    [
        "pending",
        "restricted",
    ],
)
def test_tutor_rejects_ineligible_public_questions(
    tutor_client: tuple[
        TestClient,
        dict[str, int],
        dict[str, str],
        dict[str, str],
    ],
    question_type: str,
) -> None:
    """Pending or restricted public questions are inaccessible."""

    client, question_ids, owner_headers, _ = tutor_client

    response = client.post(
        "/tutor/explain",
        json={
            "question_id": question_ids[question_type],
        },
        headers=owner_headers,
    )

    assert response.status_code == 404


def test_tutor_private_question_owner_access(
    tutor_client: tuple[
        TestClient,
        dict[str, int],
        dict[str, str],
        dict[str, str],
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The owner can access their own private question."""

    client, question_ids, owner_headers, _ = tutor_client

    monkeypatch.setattr(
        "backend.app.api.routes.tutor.explain_toeic_question",
        lambda **kwargs: "Private question explanation.",
    )

    response = client.post(
        "/tutor/explain",
        json={
            "question_id": question_ids["private"],
        },
        headers=owner_headers,
    )

    assert response.status_code == 200
    assert response.json()["explanation"] == (
        "Private question explanation."
    )


def test_tutor_private_question_rejects_other_user(
    tutor_client: tuple[
        TestClient,
        dict[str, int],
        dict[str, str],
        dict[str, str],
    ],
) -> None:
    """Another user cannot access a private question."""

    client, question_ids, _, other_headers = tutor_client

    response = client.post(
        "/tutor/explain",
        json={
            "question_id": question_ids["private"],
        },
        headers=other_headers,
    )

    assert response.status_code == 404


def test_tutor_rejects_incomplete_options(
    tutor_client: tuple[
        TestClient,
        dict[str, int],
        dict[str, str],
        dict[str, str],
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Incomplete questions must not be sent to Gemini."""

    client, question_ids, owner_headers, _ = tutor_client

    def unexpected_gemini_call(**kwargs: object) -> str:
        pytest.fail("Gemini must not be called for incomplete questions.")

    monkeypatch.setattr(
        "backend.app.api.routes.tutor.explain_toeic_question",
        unexpected_gemini_call,
    )

    response = client.post(
        "/tutor/explain",
        json={
            "question_id": question_ids["incomplete"],
        },
        headers=owner_headers,
    )

    assert response.status_code == 409


def test_tutor_handles_gemini_configuration_error(
    tutor_client: tuple[
        TestClient,
        dict[str, int],
        dict[str, str],
        dict[str, str],
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing Gemini configuration returns HTTP 503."""

    client, question_ids, owner_headers, _ = tutor_client

    def raise_configuration_error(**kwargs: object) -> str:
        raise GeminiConfigurationError(
            "Test configuration error."
        )

    monkeypatch.setattr(
        "backend.app.api.routes.tutor.explain_toeic_question",
        raise_configuration_error,
    )

    response = client.post(
        "/tutor/explain",
        json={
            "question_id": question_ids["public"],
        },
        headers=owner_headers,
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "AI Tutor service is not configured."
    )


def test_tutor_handles_gemini_service_error(
    tutor_client: tuple[
        TestClient,
        dict[str, int],
        dict[str, str],
        dict[str, str],
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gemini service failures return HTTP 502."""

    client, question_ids, owner_headers, _ = tutor_client

    def raise_service_error(**kwargs: object) -> str:
        raise GeminiServiceError(
            "Test Gemini service error."
        )

    monkeypatch.setattr(
        "backend.app.api.routes.tutor.explain_toeic_question",
        raise_service_error,
    )

    response = client.post(
        "/tutor/explain",
        json={
            "question_id": question_ids["public"],
        },
        headers=owner_headers,
    )

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "AI Tutor could not generate an explanation."
    )
def test_tutor_chat_creates_session_and_saves_messages(
    tutor_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A new conversation saves both user and assistant messages."""

    client, _, owner_headers, _ = tutor_client

    captured: dict[str, object] = {}

    def fake_chat(messages: list[dict[str, str]]) -> str:
        captured["messages"] = messages
        return "Chào bạn! Tôi có thể giúp bạn học TOEIC."

    monkeypatch.setattr(
        "backend.app.api.routes.tutor_chat.chat_with_tutor",
        fake_chat,
    )

    response = client.post(
        "/tutor/chat",
        json={
            "message": "Tôi muốn học thì hiện tại hoàn thành.",
        },
        headers=owner_headers,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["chat_session_id"] > 0
    assert data["title"] == (
        "Tôi muốn học thì hiện tại hoàn thành."
    )
    assert data["user_message"]["role"] == "user"
    assert data["assistant_message"]["role"] == "assistant"
    assert data["assistant_message"]["content"] == (
        "Chào bạn! Tôi có thể giúp bạn học TOEIC."
    )

    assert captured["messages"] == [
        {
            "role": "user",
            "content": "Tôi muốn học thì hiện tại hoàn thành.",
        }
    ]

    # Verify that the conversation was persisted.
    detail_response = client.get(
        f"/tutor/sessions/{data['chat_session_id']}",
        headers=owner_headers,
    )

    assert detail_response.status_code == 200

    messages = detail_response.json()["messages"]

    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


def test_tutor_chat_preserves_multi_turn_history(
    tutor_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The next Gemini request includes previous conversation messages."""

    client, _, owner_headers, _ = tutor_client

    monkeypatch.setattr(
        "backend.app.api.routes.tutor_chat.chat_with_tutor",
        lambda messages: "Phản hồi đầu tiên.",
    )

    first_response = client.post(
        "/tutor/chat",
        json={
            "message": "Thì hiện tại hoàn thành là gì?",
        },
        headers=owner_headers,
    )

    assert first_response.status_code == 200

    session_id = first_response.json()["chat_session_id"]

    captured: dict[str, object] = {}

    def fake_second_chat(
        messages: list[dict[str, str]],
    ) -> str:
        captured["messages"] = messages
        return "Since thường đi với một mốc thời gian bắt đầu."

    monkeypatch.setattr(
        "backend.app.api.routes.tutor_chat.chat_with_tutor",
        fake_second_chat,
    )

    second_response = client.post(
        "/tutor/chat",
        json={
            "chat_session_id": session_id,
            "message": "Từ since được sử dụng như thế nào?",
        },
        headers=owner_headers,
    )

    assert second_response.status_code == 200

    assert captured["messages"] == [
        {
            "role": "user",
            "content": "Thì hiện tại hoàn thành là gì?",
        },
        {
            "role": "assistant",
            "content": "Phản hồi đầu tiên.",
        },
        {
            "role": "user",
            "content": "Từ since được sử dụng như thế nào?",
        },
    ]


def test_tutor_chat_requires_authentication(
    tutor_client,
) -> None:
    """Chat APIs require a valid JWT."""

    client, _, _, _ = tutor_client

    post_response = client.post(
        "/tutor/chat",
        json={
            "message": "Xin chào.",
        },
    )

    list_response = client.get("/tutor/sessions")

    assert post_response.status_code == 401
    assert list_response.status_code == 401


def test_tutor_chat_rejects_invalid_payload(
    tutor_client,
) -> None:
    """Empty messages and client-supplied user IDs are rejected."""

    client, _, owner_headers, _ = tutor_client

    empty_response = client.post(
        "/tutor/chat",
        json={
            "message": "   ",
        },
        headers=owner_headers,
    )

    extra_field_response = client.post(
        "/tutor/chat",
        json={
            "message": "Xin chào.",
            "user_id": 999,
        },
        headers=owner_headers,
    )

    assert empty_response.status_code == 422
    assert extra_field_response.status_code == 422


def test_tutor_chat_enforces_session_owner(
    tutor_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A different user cannot read or continue another user's session."""

    client, _, owner_headers, other_headers = tutor_client

    monkeypatch.setattr(
        "backend.app.api.routes.tutor_chat.chat_with_tutor",
        lambda messages: "Phản hồi kiểm thử.",
    )

    create_response = client.post(
        "/tutor/chat",
        json={
            "message": "Hãy giúp tôi học TOEIC.",
        },
        headers=owner_headers,
    )

    assert create_response.status_code == 200

    session_id = create_response.json()["chat_session_id"]

    read_response = client.get(
        f"/tutor/sessions/{session_id}",
        headers=other_headers,
    )

    continue_response = client.post(
        "/tutor/chat",
        json={
            "chat_session_id": session_id,
            "message": "Tôi muốn hỏi tiếp.",
        },
        headers=other_headers,
    )

    assert read_response.status_code == 404
    assert continue_response.status_code == 404


def test_tutor_chat_lists_only_current_user_sessions(
    tutor_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The session list is paginated and scoped to the current user."""

    client, _, owner_headers, other_headers = tutor_client

    monkeypatch.setattr(
        "backend.app.api.routes.tutor_chat.chat_with_tutor",
        lambda messages: "Phản hồi kiểm thử.",
    )

    for message in [
        "Học ngữ pháp TOEIC.",
        "Học từ vựng TOEIC.",
    ]:
        response = client.post(
            "/tutor/chat",
            json={"message": message},
            headers=owner_headers,
        )
        assert response.status_code == 200

    owner_response = client.get(
        "/tutor/sessions?limit=1&offset=0",
        headers=owner_headers,
    )

    other_response = client.get(
        "/tutor/sessions",
        headers=other_headers,
    )

    assert owner_response.status_code == 200
    assert owner_response.json()["total"] == 2
    assert len(owner_response.json()["items"]) == 1
    assert owner_response.json()["items"][0]["message_count"] == 2

    assert other_response.status_code == 200
    assert other_response.json()["total"] == 0


def test_tutor_chat_handles_gemini_configuration_error(
    tutor_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Gemini configuration error returns HTTP 503."""

    client, _, owner_headers, _ = tutor_client

    def raise_configuration_error(
        messages: list[dict[str, str]],
    ) -> str:
        raise GeminiConfigurationError(
            "Test configuration error."
        )

    monkeypatch.setattr(
        "backend.app.api.routes.tutor_chat.chat_with_tutor",
        raise_configuration_error,
    )

    response = client.post(
        "/tutor/chat",
        json={"message": "Xin chào."},
        headers=owner_headers,
    )

    assert response.status_code == 503

    # A failed request must not create a chat session.
    list_response = client.get(
        "/tutor/sessions",
        headers=owner_headers,
    )

    assert list_response.json()["total"] == 0


def test_tutor_chat_handles_gemini_service_error(
    tutor_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Gemini generation error returns HTTP 502."""

    client, _, owner_headers, _ = tutor_client

    def raise_service_error(
        messages: list[dict[str, str]],
    ) -> str:
        raise GeminiServiceError(
            "Test Gemini service error."
        )

    monkeypatch.setattr(
        "backend.app.api.routes.tutor_chat.chat_with_tutor",
        raise_service_error,
    )

    response = client.post(
        "/tutor/chat",
        json={"message": "Xin chào."},
        headers=owner_headers,
    )

    assert response.status_code == 502


def test_tutor_chat_rejects_unknown_session(
    tutor_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A nonexistent session ID returns HTTP 404."""

    client, _, owner_headers, _ = tutor_client

    monkeypatch.setattr(
        "backend.app.api.routes.tutor_chat.chat_with_tutor",
        lambda messages: "Không nên được gọi.",
    )

    response = client.post(
        "/tutor/chat",
        json={
            "chat_session_id": 999999,
            "message": "Tôi muốn hỏi tiếp.",
        },
        headers=owner_headers,
    )

    assert response.status_code == 404