
"""Streamlit UI for the personalized TOEIC student dashboard."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import streamlit as st

from frontend.auth_ui import get_active_token
from frontend.dashboard_api_client import (
    DashboardAPIClient,
    DashboardAPIError,
)


def _format_minutes(seconds: int) -> str:
    """Convert seconds into a readable duration."""
    minutes = seconds // 60
    hours, remaining_minutes = divmod(minutes, 60)

    if hours:
        return f"{hours} giờ {remaining_minutes} phút"

    return f"{remaining_minutes} phút"


def _render_overview(data: dict[str, Any]) -> None:
    """Render high-level learning statistics."""

    st.subheader("Tổng quan học tập")

    target_score = data.get("target_score")
    active_plan = data.get("active_plan")

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Điểm TOEIC mục tiêu",
        target_score if target_score is not None else "Chưa đặt",
    )

    col2.metric(
        "Bài luyện đã nộp",
        data["submitted_quiz_sessions"],
    )

    col3.metric(
        "Số ngày hoạt động",
        data["active_days"],
    )

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Tổng câu đã trả lời",
        data["answered_questions"],
    )

    col2.metric(
        "Số câu đúng",
        data["correct_answers"],
    )

    col3.metric(
        "Độ chính xác",
        f'{data["accuracy_percent"]:.2f}%',
    )

    if active_plan is None:
        st.info(
            "Bạn chưa có kế hoạch học tập đang hoạt động. "
            "Hãy tạo một kế hoạch để bắt đầu học có lộ trình."
        )
    else:
        st.success(
            f'Kế hoạch đang hoạt động: '
            f'{active_plan.get("title", "Kế hoạch TOEIC")}'
        )


def _render_performance(data: dict[str, Any]) -> None:
    """Render aggregated quiz performance."""

    st.subheader("Hiệu suất luyện tập")

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Bài đã nộp",
        data["submitted_sessions"],
    )

    col2.metric(
        "Câu trả lời đúng",
        data["correct_answers"],
    )

    col3.metric(
        "Câu trả lời sai",
        data["incorrect_answers"],
    )

    col1, col2 = st.columns(2)

    col1.metric(
        "Độ chính xác",
        f'{data["accuracy_percent"]:.2f}%',
    )

    col2.metric(
        "Tổng thời gian luyện tập",
        _format_minutes(data["total_time_spent_seconds"]),
    )


def _render_skills(data: dict[str, Any]) -> None:
    """Render skill-level performance and weak skills."""

    st.subheader("Phân tích kỹ năng")

    items = data["items"]

    if not items:
        st.info(
            "Chưa có dữ liệu kỹ năng. "
            "Hãy hoàn thành một số bài luyện để xem phân tích."
        )
        return

    weak_skills = [
        item for item in items
        if item["is_weak"]
    ]

    if weak_skills:
        st.warning(
            "Các kỹ năng cần ưu tiên ôn tập: "
            + ", ".join(item["name"] for item in weak_skills)
        )
    else:
        st.success(
            "Chưa phát hiện kỹ năng yếu trong dữ liệu hiện tại."
        )

    rows = []

    for item in items:
        rows.append(
            {
                "Kỹ năng": item["name"],
                "Mã kỹ năng": item["code"],
                "Nhóm": item["category"],
                "Số lần làm": item["attempt_count"],
                "Số câu đúng": item["correct_count"],
                "Số câu sai": item["incorrect_count"],
                "Độ chính xác (%)": item["accuracy_percent"],
                "Cần ôn tập": (
                    "Có" if item["is_weak"] else "Không"
                ),
            }
        )

    st.dataframe(
        rows,
        use_container_width=True,
        hide_index=True,
    )


def _render_activity(
    data: dict[str, Any],
) -> None:
    """Render daily learning activity."""

    st.subheader("Hoạt động học tập")

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Ngày có hoạt động",
        data["total_active_days"],
    )

    col2.metric(
        "Bài luyện đã nộp",
        data["total_submitted_sessions"],
    )

    col3.metric(
        "Câu đã trả lời",
        data["total_answered_questions"],
    )

    days = data["days"]

    if not days:
        st.info(
            "Chưa có hoạt động học tập trong khoảng thời gian này."
        )
        return

    chart_data = {
        item["activity_date"]: item["answered_questions"]
        for item in days
    }

    st.caption("Số câu trả lời theo ngày")

    st.bar_chart(
        chart_data,
        x_label="Ngày",
        y_label="Số câu trả lời",
    )

    rows = [
        {
            "Ngày": item["activity_date"],
            "Bài đã nộp": item["submitted_sessions"],
            "Câu đã trả lời": item["answered_questions"],
            "Câu đúng": item["correct_answers"],
            "Độ chính xác (%)": item["accuracy_percent"],
        }
        for item in days
    ]

    with st.expander("Xem dữ liệu hoạt động chi tiết"):
        st.dataframe(
            rows,
            use_container_width=True,
            hide_index=True,
        )


def _render_study_plan(
    data: dict[str, Any],
) -> None:
    """Render active study plan progress and upcoming tasks."""

    st.subheader("Kế hoạch học tập")

    plan = data.get("plan")

    if plan is None:
        st.info(
            "Bạn chưa có kế hoạch học tập đang hoạt động."
        )
        return

    st.markdown(
        f'**{plan.get("title", "Kế hoạch TOEIC")}**'
    )

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Tổng nhiệm vụ",
        data["total_tasks"],
    )

    col2.metric(
        "Đã hoàn thành",
        data["completed_tasks"],
    )

    col3.metric(
        "Đang chờ",
        data["pending_tasks"],
    )

    completion = data["completion_percent"]

    st.progress(
        completion / 100,
        text=f"Tiến độ hoàn thành: {completion:.1f}%",
    )

    st.caption(
        f'Nhiệm vụ đã bỏ qua: {data["skipped_tasks"]}'
    )

    upcoming_tasks = data["upcoming_tasks"]

    st.markdown("#### Nhiệm vụ sắp tới")

    if not upcoming_tasks:
        st.info("Không có nhiệm vụ sắp tới.")
        return

    task_type_labels = {
        "practice": "Luyện tập",
        "review": "Ôn tập",
        "quiz": "Kiểm tra",
    }

    task_status_labels = {
        "pending": "Chưa hoàn thành",
        "completed": "Đã hoàn thành",
        "skipped": "Đã bỏ qua",
    }

    rows = []

    for task in upcoming_tasks:
        skill = task.get("skill")

        skill_name = (
            skill.get("name", "Chung")
            if isinstance(skill, dict)
            else "Chung"
        )

        rows.append(
            {
                "Ngày": task["scheduled_date"],
                "Loại nhiệm vụ": task_type_labels.get(
                    task["task_type"],
                    task["task_type"],
                ),
                "Kỹ năng": skill_name,
                "Thời lượng (phút)": task["estimated_minutes"],
                "Số câu mục tiêu": task["target_question_count"],
                "Trạng thái": task_status_labels.get(
                    task["status"],
                    task["status"],
                ),
            }
        )

    st.dataframe(
        rows,
        use_container_width=True,
        hide_index=True,
    )


def render_dashboard_interface(
    api_base_url: str,
) -> None:
    """Render the authenticated student's dashboard."""

    token = get_active_token(st.session_state)

    if not token:
        st.info(
            "Vui lòng đăng nhập để xem Dashboard học tập."
        )
        return

    st.header("📊 Dashboard học tập")

    st.caption(
        "Theo dõi tiến độ, hiệu suất và các kỹ năng TOEIC "
        "cần ưu tiên cải thiện."
    )

    period_options = {
        "7 ngày gần nhất": 7,
        "30 ngày gần nhất": 30,
        "90 ngày gần nhất": 90,
    }

    selected_period = st.selectbox(
        "Khoảng thời gian thống kê",
        options=list(period_options.keys()),
        index=1,
        key="toeic_dashboard_period",
    )

    today = date.today()
    days_count = period_options[selected_period]

    start_date = today - timedelta(days=days_count - 1)

    if st.button(
        "🔄 Làm mới Dashboard",
        key="toeic_dashboard_refresh",
        use_container_width=True,
    ):
        st.rerun()

    try:
        with DashboardAPIClient(
            base_url=api_base_url,
            access_token=token,
        ) as client:

            with st.spinner("Đang tải dữ liệu học tập..."):
                overview = client.get_overview()
                performance = client.get_performance()
                skills = client.get_skills()
                activity = client.get_activity(
                    start_date=start_date,
                    end_date=today,
                )
                study_plan = client.get_study_plan()

    except (DashboardAPIError, ValueError) as error:
        st.error(str(error))
        return

    _render_overview(overview)

    st.divider()

    _render_performance(performance)

    st.divider()

    _render_skills(skills)

    st.divider()

    _render_activity(activity)

    st.divider()

    _render_study_plan(study_plan)
