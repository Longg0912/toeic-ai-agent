"""Streamlit UI for multi-turn TOEIC AI Tutor chat."""

from __future__ import annotations

import hashlib
from typing import Any

import streamlit as st

from frontend.auth_ui import get_active_token
from frontend.quiz_ui import ACTIVE_QUIZ_KEY
from frontend.tutor_api_client import (
    TutorAPIClient,
    TutorAPIError,
)


# =====================================================
# Session state keys
# =====================================================

ACTIVE_SESSION_KEY = "toeic_tutor_active_session"
MESSAGES_KEY = "toeic_tutor_messages"
TOKEN_FINGERPRINT_KEY = "toeic_tutor_token_fingerprint"
SELECTOR_VERSION_KEY = "toeic_tutor_selector_version"


# =====================================================
# Session state helpers
# =====================================================

def _reset_chat_state() -> None:
    """Clear the local chat UI state."""

    st.session_state[ACTIVE_SESSION_KEY] = None
    st.session_state[MESSAGES_KEY] = []

    st.session_state[SELECTOR_VERSION_KEY] = (
        st.session_state.get(SELECTOR_VERSION_KEY, 0) + 1
    )


def _sync_user_state(token: str) -> None:
    """Prevent cached conversations from carrying across accounts."""

    fingerprint = hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()

    previous_fingerprint = st.session_state.get(
        TOKEN_FINGERPRINT_KEY
    )

    if previous_fingerprint != fingerprint:
        _reset_chat_state()

        st.session_state[TOKEN_FINGERPRINT_KEY] = (
            fingerprint
        )


def _render_messages(
    messages: list[dict[str, Any]],
) -> None:
    """Render the conversation messages."""

    if not messages:
        st.info(
            "Xin chào! Tôi là gia sư TOEIC AI. "
            "Bạn có thể hỏi tôi về ngữ pháp, từ vựng, "
            "cấu trúc câu hoặc cách làm bài TOEIC."
        )
        return

    for message in messages:
        role = message["role"]

        with st.chat_message(role):
            st.markdown(message["content"])


def _session_label(
    session_id: int | None,
    labels: dict[int, str],
) -> str:
    if session_id is None:
        return "＋ Hội thoại mới"

    return labels.get(
        session_id,
        f"Hội thoại #{session_id}",
    )


# =====================================================
# Main Tutor UI
# =====================================================

def render_tutor_interface(
    api_base_url: str,
) -> None:
    """Render the authenticated multi-turn Tutor interface."""

    token = get_active_token(st.session_state)

    # The authentication UI is responsible for login.
    if not token:
        return

    _sync_user_state(token)

    st.header("🤖 Gia sư AI TOEIC")

    st.caption(
        "Đặt câu hỏi về ngữ pháp, từ vựng, "
        "cấu trúc câu và chiến lược làm bài TOEIC."
    )

    try:
        with TutorAPIClient(
            base_url=api_base_url,
            access_token=token,
        ) as client:

            # -----------------------------------------
            # 1. Load the current user's chat sessions
            # -----------------------------------------

            sessions_data = client.list_sessions(
                limit=50,
                offset=0,
            )

            sessions = sessions_data["items"]
            total_sessions = sessions_data["total"]

            session_labels = {
                item["id"]: (
                    f'{item["title"][:45]}'
                    f' · {item["message_count"]} tin nhắn'
                )
                for item in sessions
            }

            session_ids = [
                item["id"]
                for item in sessions
            ]

            # -----------------------------------------
            # 2. Conversation list and chat area
            # -----------------------------------------

            history_col, chat_col = st.columns(
                [1, 2.2],
                gap="large",
            )

            with history_col:
                st.subheader("Lịch sử hội thoại")

                if st.button(
                    "＋ Cuộc trò chuyện mới",
                    key="toeic_tutor_new_chat",
                    use_container_width=True,
                ):
                    _reset_chat_state()
                    st.rerun()

                active_session_id = st.session_state.get(
                    ACTIVE_SESSION_KEY
                )

                selector_version = st.session_state.get(
                    SELECTOR_VERSION_KEY,
                    0,
                )

                selector_key = (
                    f"toeic_tutor_session_selector_"
                    f"{total_sessions}_{selector_version}"
                )

                options: list[int | None] = (
                    [None] + session_ids
                )

                if active_session_id in session_ids:
                    default_index = options.index(
                        active_session_id
                    )
                else:
                    default_index = 0

                selected_session_id = st.selectbox(
                    "Chọn hội thoại",
                    options=options,
                    index=default_index,
                    format_func=lambda value: _session_label(
                        value,
                        session_labels,
                    ),
                    key=selector_key,
                    disabled=not session_ids,
                )

                st.caption(
                    f"Tổng số hội thoại: {total_sessions}"
                )

            # -----------------------------------------
            # 3. Load selected conversation if changed
            # -----------------------------------------

            active_session_id = st.session_state.get(
                ACTIVE_SESSION_KEY
            )

            if selected_session_id != active_session_id:
                if selected_session_id is None:
                    st.session_state[ACTIVE_SESSION_KEY] = None
                    st.session_state[MESSAGES_KEY] = []

                else:
                    detail = client.get_session(
                        selected_session_id
                    )

                    st.session_state[ACTIVE_SESSION_KEY] = (
                        detail["id"]
                    )

                    st.session_state[MESSAGES_KEY] = (
                        detail["messages"]
                    )

            # -----------------------------------------
            # 4. Display conversation
            # -----------------------------------------

            with chat_col:
                current_session_id = st.session_state.get(
                    ACTIVE_SESSION_KEY
                )

                if current_session_id is not None:
                    current_title = session_labels.get(
                        current_session_id,
                        "Hội thoại TOEIC",
                    )

                    st.subheader(
                        current_title.split(" · ")[0]
                    )
                else:
                    st.subheader("Hội thoại mới")

                messages = st.session_state.get(
                    MESSAGES_KEY,
                    [],
                )

                _render_messages(messages)

            # -----------------------------------------
            # 5. Prevent answer leakage during a quiz
            # -----------------------------------------

            active_quiz = st.session_state.get(
                ACTIVE_QUIZ_KEY
            )

            quiz_in_progress = (
                isinstance(active_quiz, dict)
                and active_quiz.get("status") == "in_progress"
            )

            if quiz_in_progress:
                st.warning(
                    "Bạn đang làm bài kiểm tra TOEIC. "
                    "Để tránh vô tình tiết lộ đáp án, "
                    "hãy nộp bài trước khi sử dụng khung chat AI."
                )
                return

            # -----------------------------------------
            # 6. Chat input and Gemini response
            # -----------------------------------------

            prompt = st.chat_input(
                "Nhập câu hỏi TOEIC của bạn..."
            )

            if prompt:
                current_session_id = st.session_state.get(
                    ACTIVE_SESSION_KEY
                )

                with st.spinner(
                    "Gia sư AI đang suy nghĩ..."
                ):
                    response = client.send_message(
                        message=prompt,
                        chat_session_id=current_session_id,
                    )

                # Save the returned session ID.
                st.session_state[ACTIVE_SESSION_KEY] = (
                    response["chat_session_id"]
                )

                # Add the user and assistant messages.
                updated_messages = list(
                    st.session_state.get(MESSAGES_KEY, [])
                )

                updated_messages.append(
                    response["user_message"]
                )

                updated_messages.append(
                    response["assistant_message"]
                )

                st.session_state[MESSAGES_KEY] = (
                    updated_messages
                )

                st.rerun()

    except TutorAPIError as error:
        st.error(str(error))

    except ValueError as error:
        st.error(str(error))