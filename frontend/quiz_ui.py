"""Streamlit UI for TOEIC Part 5 practice and quiz history."""

from typing import Any

import streamlit as st

from frontend.auth_ui import get_active_token
from frontend.quiz_api_client import QuizAPIClient, QuizAPIError


ACTIVE_QUIZ_KEY = "toeic_active_quiz"
RESULT_KEY = "toeic_quiz_result"
HISTORY_KEY = "toeic_quiz_history"
DETAIL_KEY = "toeic_quiz_history_detail"


SKILL_OPTIONS = [
    ("Tất cả kỹ năng", None),
    ("Ngữ pháp - Đại từ", "GRAMMAR_PRONOUNS"),
    ("Ngữ pháp - Dạng từ", "GRAMMAR_WORD_FORM"),
    ("Ngữ pháp - Thì", "GRAMMAR_TENSES"),
    ("Ngữ pháp - Giới từ", "GRAMMAR_PREPOSITIONS"),
    (
        "Ngữ pháp - Hòa hợp chủ vị",
        "GRAMMAR_SUBJECT_VERB_AGREEMENT",
    ),
    ("Ngữ pháp - Mệnh đề quan hệ", "GRAMMAR_RELATIVE_CLAUSES"),
    ("Ngữ pháp - Động từ nguyên mẫu", "GRAMMAR_INFINITIVES"),
    ("Ngữ pháp - Danh động từ", "GRAMMAR_GERUNDS"),
    ("Ngữ pháp - Bị động", "GRAMMAR_PASSIVE_VOICE"),
    ("Ngữ pháp - So sánh", "GRAMMAR_COMPARISON"),
    ("Ngữ pháp - Đảo ngữ", "GRAMMAR_INVERSION"),
    (
        "Ngữ pháp - Liên từ và mệnh đề",
        "GRAMMAR_CLAUSES_CONJUNCTIONS",
    ),
    (
        "Ngữ pháp - Lượng từ và từ hạn định",
        "GRAMMAR_QUANTIFIERS_DETERMINERS",
    ),
    ("Ngữ pháp - Cấu trúc song song", "GRAMMAR_PARALLELISM"),
    (
        "Ngữ pháp - Mệnh đề phân từ",
        "GRAMMAR_PARTICIPLE_CLAUSES",
    ),
    ("Ngữ pháp - Câu giả định", "GRAMMAR_SUBJUNCTIVE"),
    ("Từ vựng - Kinh doanh", "VOCAB_BUSINESS"),
]


STATUS_LABELS = {
    "in_progress": "Đang làm",
    "submitted": "Đã nộp",
    "abandoned": "Đã bỏ dở",
}


def _get_client(api_base_url: str, token: str) -> QuizAPIClient:
    """Create an authenticated quiz API client."""
    return QuizAPIClient(
        base_url=api_base_url,
        access_token=token,
    )


def _render_create_form(api_base_url: str, token: str) -> None:
    """Display the form used to create a new practice session."""
    st.subheader("Bắt đầu bài luyện")

    skill_labels = [label for label, _ in SKILL_OPTIONS]
    skill_codes = {
        label: code for label, code in SKILL_OPTIONS
    }

    with st.form("toeic_create_session_form"):
        question_count = st.slider(
            "Số câu hỏi",
            min_value=1,
            max_value=50,
            value=10,
            help="Số câu hỏi Part 5 trong bài luyện.",
        )

        selected_skill = st.selectbox(
            "Kỹ năng",
            options=skill_labels,
            index=0,
        )

        start_clicked = st.form_submit_button(
            "Bắt đầu luyện tập",
            type="primary",
            use_container_width=True,
        )

    if not start_clicked:
        return

    skill_code = skill_codes[selected_skill]

    try:
        with _get_client(api_base_url, token) as client:
            session_data = client.create_session(
                question_count=question_count,
                skill_code=skill_code,
            )
    except (QuizAPIError, ValueError) as exc:
        st.error(str(exc))
        return

    st.session_state[ACTIVE_QUIZ_KEY] = session_data
    st.session_state[RESULT_KEY] = None

    # A new session must not display an old session's review.
    st.session_state[DETAIL_KEY] = None

    st.rerun()


def _render_active_quiz(
    api_base_url: str,
    token: str,
    quiz: dict[str, Any],
) -> None:
    """Render questions and submit the user's answers."""
    session_id = quiz["id"]
    items = sorted(
        quiz.get("items", []),
        key=lambda item: item["position"],
    )

    st.subheader(f"Bài luyện #{session_id}")
    st.caption(
        f"{len(items)} câu hỏi · Chọn một đáp án cho mỗi câu."
    )

    if not items:
        st.warning("Bài luyện hiện không có câu hỏi.")
        return

    with st.form(f"toeic_submit_quiz_{session_id}"):
        for item in items:
            item_id = item["id"]
            position = item["position"]
            answer_key = f"toeic_answer_{session_id}_{item_id}"

            st.markdown(f"**Câu {position}**")
            st.write(item["content"])

            option_map = {
                option["option_key"]: option["content"]
                for option in item.get("options", [])
            }
            option_keys = list(option_map.keys())

            st.radio(
                "Chọn đáp án",
                options=option_keys,
                index=None,
                format_func=lambda key, mapping=option_map: (
                    f"{key}. {mapping[key]}"
                ),
                key=answer_key,
            )

            skill_codes = item.get("skill_codes", [])
            if skill_codes:
                st.caption(
                    "Kỹ năng: " + ", ".join(skill_codes)
                )

            st.divider()

        submit_clicked = st.form_submit_button(
            "Nộp bài và xem kết quả",
            type="primary",
            use_container_width=True,
        )

    if not submit_clicked:
        return

    answers: list[dict[str, Any]] = []
    unanswered_positions: list[int] = []

    for item in items:
        answer_key = (
            f"toeic_answer_{session_id}_{item['id']}"
        )
        selected_key = st.session_state.get(answer_key)

        if selected_key is None:
            unanswered_positions.append(item["position"])
            continue

        answers.append(
            {
                "quiz_item_id": item["id"],
                "selected_option_key": selected_key,
            }
        )

    if unanswered_positions:
        positions = ", ".join(
            str(position) for position in unanswered_positions
        )
        st.warning(
            f"Bạn chưa trả lời câu: {positions}. "
            "Hãy hoàn thành các câu này trước khi nộp bài."
        )
        return

    try:
        with _get_client(api_base_url, token) as client:
            result = client.submit_session(
                session_id=session_id,
                answers=answers,
            )
    except (QuizAPIError, ValueError) as exc:
        st.error(str(exc))
        return

    st.session_state[RESULT_KEY] = result
    st.session_state[ACTIVE_QUIZ_KEY] = None

    # Clear the selected answers from this completed session.
    for item in items:
        answer_key = (
            f"toeic_answer_{session_id}_{item['id']}"
        )
        st.session_state.pop(answer_key, None)

    st.rerun()


def _render_review_items(
    items: list[dict[str, Any]],
    *,
    submitted: bool,
) -> None:
    """Display questions, options and review information."""
    for item in sorted(
        items,
        key=lambda value: value["position"],
    ):
        with st.container(border=True):
            st.markdown(f"**Câu {item['position']}**")
            st.write(item["content"])

            selected_key = item.get("selected_option_key")
            correct_key = item.get("correct_option_key")
            is_correct = item.get("is_correct")

            for option in item.get("options", []):
                key = option["option_key"]
                content = option["content"]

                if submitted and key == correct_key:
                    prefix = "✅ Đáp án đúng"
                elif submitted and key == selected_key:
                    prefix = "❌ Bạn đã chọn"
                else:
                    prefix = "•"

                st.write(f"{prefix} — {key}. {content}")

            if submitted and selected_key is not None:
                if is_correct:
                    st.success("Bạn trả lời đúng.")
                elif correct_key is not None:
                    st.error(
                        f"Bạn chọn {selected_key}; "
                        f"đáp án đúng là {correct_key}."
                    )

            explanation = item.get("explanation")
            if submitted and explanation:
                st.markdown("**Giải thích:**")
                st.write(explanation)

            skill_codes = item.get("skill_codes", [])
            if skill_codes:
                st.caption(
                    "Kỹ năng: " + ", ".join(skill_codes)
                )


def _render_result(result: dict[str, Any]) -> None:
    """Display the score and review after submission."""
    st.divider()
    st.subheader("Kết quả bài luyện")

    total = result["total_questions"]
    answered = result["answered_count"]
    correct = result["correct_count"]
    accuracy = result["accuracy_percent"]

    col1, col2, col3 = st.columns(3)

    col1.metric("Số câu đúng", f"{correct}/{total}")
    col2.metric("Độ chính xác", f"{accuracy:.2f}%")
    col3.metric("Đã trả lời", f"{answered}/{total}")

    st.caption(f"Mã bài luyện: {result['session_id']}")

    _render_review_items(
        result.get("items", []),
        submitted=True,
    )

    if st.button(
        "Ẩn kết quả",
        key="toeic_hide_result",
    ):
        st.session_state[RESULT_KEY] = None
        st.rerun()


def _history_label(item: dict[str, Any]) -> str:
    """Format a quiz session for the history selector."""
    status = STATUS_LABELS.get(
        item["status"],
        item["status"],
    )

    started_at = item.get("started_at", "")

    return (
        f"Bài #{item['id']} · {status} · {started_at}"
    )


def _render_history_detail(
    detail: dict[str, Any],
) -> None:
    """Display a saved session without revealing unfinished answers."""
    st.divider()
    st.subheader(f"Chi tiết bài luyện #{detail['id']}")

    status = detail["status"]
    total = detail["question_count"]
    answered = detail["answered_count"]

    col1, col2 = st.columns(2)
    col1.metric("Số câu hỏi", total)
    col2.metric("Đã trả lời", answered)

    if status == "submitted":
        col1, col2 = st.columns(2)
        col1.metric(
            "Số câu đúng",
            f"{detail['correct_count']}/{total}",
        )
        accuracy = detail.get("accuracy_percent")
        if accuracy is not None:
            col2.metric(
                "Độ chính xác",
                f"{accuracy:.2f}%",
            )

        _render_review_items(
            detail.get("items", []),
            submitted=True,
        )
    else:
        st.info(
            "Bài này chưa được nộp. "
            "Đáp án đúng và lời giải chưa được hiển thị."
        )
        _render_review_items(
            detail.get("items", []),
            submitted=False,
        )


def _render_history(
    api_base_url: str,
    token: str,
) -> None:
    """Display the authenticated user's quiz history."""
    st.subheader("Lịch sử luyện tập")

    if st.button(
        "Tải lịch sử",
        key="toeic_load_history",
        type="primary",
    ):
        try:
            with _get_client(api_base_url, token) as client:
                history = client.list_sessions(
                    limit=20,
                    offset=0,
                )
        except (QuizAPIError, ValueError) as exc:
            st.error(str(exc))
        else:
            st.session_state[HISTORY_KEY] = history
            st.session_state[DETAIL_KEY] = None

    history = st.session_state.get(HISTORY_KEY)

    if not history:
        st.info(
            "Nhấn 'Tải lịch sử' để xem các bài luyện đã thực hiện."
        )
        return

    items = history.get("items", [])
    total = history.get("total", len(items))

    st.caption(f"Tìm thấy {total} bài luyện.")

    if not items:
        st.info("Bạn chưa có bài luyện nào.")
        return

    status_labels = STATUS_LABELS

    rows = []
    for item in items:
        rows.append(
            {
                "Mã bài": item["id"],
                "Trạng thái": status_labels.get(
                    item["status"],
                    item["status"],
                ),
                "Thời gian bắt đầu": item["started_at"],
                "Số câu": item["question_count"],
                "Đã trả lời": item["answered_count"],
                "Số câu đúng": item.get("correct_count"),
                "Độ chính xác (%)": item.get("accuracy_percent"),
            }
        )

    st.dataframe(
        rows,
        use_container_width=True,
        hide_index=True,
    )

    item_by_id = {
        item["id"]: item for item in items
    }

    selected_session_id = st.selectbox(
        "Chọn bài luyện muốn xem lại",
        options=list(item_by_id.keys()),
        format_func=lambda session_id, lookup=item_by_id: (
            _history_label(lookup[session_id])
        ),
        key="toeic_history_session_selector",
    )

    if st.button(
        "Xem lại bài đã chọn",
        key="toeic_review_history",
    ):
        try:
            with _get_client(api_base_url, token) as client:
                detail = client.get_session(
                    selected_session_id
                )
        except (QuizAPIError, ValueError) as exc:
            st.error(str(exc))
        else:
            st.session_state[DETAIL_KEY] = detail

    detail = st.session_state.get(DETAIL_KEY)

    if (
        detail
        and detail.get("id") == selected_session_id
    ):
        _render_history_detail(detail)


def render_quiz_interface(api_base_url: str) -> None:
    """Render the quiz interface for an authenticated user."""
    token = get_active_token(st.session_state)
    if not token:
        st.info(
            "Vui lòng đăng nhập để bắt đầu luyện TOEIC "
            "và xem lịch sử bài làm."
        )
        return

    st.header("📝 Luyện thi TOEIC Part 5")

    practice_tab, history_tab = st.tabs(
        ["Luyện tập", "Lịch sử bài làm"]
    )

    with practice_tab:
        active_quiz = st.session_state.get(ACTIVE_QUIZ_KEY)

        if (
            active_quiz
            and active_quiz.get("status") == "in_progress"
        ):
            _render_active_quiz(
                api_base_url,
                token,
                active_quiz,
            )
        else:
            _render_create_form(
                api_base_url,
                token,
            )

        result = st.session_state.get(RESULT_KEY)

        if result:
            _render_result(result)

    with history_tab:
        _render_history(
            api_base_url,
            token,
        )