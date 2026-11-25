
"""Streamlit UI for creating and managing TOEIC study plans."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable

import streamlit as st

from frontend.auth_ui import get_active_token
from frontend.study_plan_api_client import (
    StudyPlanAPIClient,
    StudyPlanAPIError,
)


STATUS_LABELS = {
    "active": "Đang hoạt động",
    "paused": "Đã tạm dừng",
    "completed": "Đã hoàn thành",
    "cancelled": "Đã hủy",
}

TASK_TYPE_LABELS = {
    "practice": "Luyện tập",
    "review": "Ôn tập",
    "quiz": "Kiểm tra",
}

TASK_STATUS_LABELS = {
    "pending": "Chưa hoàn thành",
    "completed": "Đã hoàn thành",
    "skipped": "Đã bỏ qua",
}


def _format_date(value: str) -> str:
    """Format an ISO date for display."""
    try:
        return date.fromisoformat(value).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return value


def _render_create_form(
    client: StudyPlanAPIClient,
) -> None:
    """Render and process the study plan creation form."""

    st.subheader("Tạo kế hoạch học tập")

    with st.form(
        "toeic_create_study_plan_form",
        clear_on_submit=False,
    ):
        title = st.text_input(
            "Tên kế hoạch",
            value="Kế hoạch luyện thi TOEIC",
            max_chars=200,
            key="toeic_plan_title",
        )

        col1, col2 = st.columns(2)

        with col1:
            target_score = st.number_input(
                "Điểm TOEIC mục tiêu",
                min_value=0,
                max_value=990,
                value=750,
                step=5,
                key="toeic_plan_target_score",
            )

            start_date = st.date_input(
                "Ngày bắt đầu",
                value=date.today(),
                key="toeic_plan_start_date",
            )

        with col2:
            daily_minutes = st.number_input(
                "Thời gian học mỗi ngày (phút)",
                min_value=1,
                max_value=1440,
                value=60,
                step=5,
                key="toeic_plan_daily_minutes",
            )

            end_date = st.date_input(
                "Ngày kết thúc",
                value=date.today() + timedelta(days=30),
                min_value=date.today(),
                key="toeic_plan_end_date",
            )

        submitted = st.form_submit_button(
            "Tạo kế hoạch",
            width="stretch",
        )

    if not submitted:
        return

    clean_title = title.strip()

    if not clean_title:
        st.error("Vui lòng nhập tên kế hoạch.")
        return

    if end_date < start_date:
        st.error("Ngày kết thúc không được trước ngày bắt đầu.")
        return

    try:
        plan = client.create_study_plan(
            title=clean_title,
            target_score=int(target_score),
            start_date=start_date,
            end_date=end_date,
            daily_minutes=int(daily_minutes),
        )

    except (StudyPlanAPIError, ValueError) as error:
        st.error(str(error))
        return

    st.success(
        f'Đã tạo kế hoạch "{plan["title"]}" thành công.'
    )
    st.rerun()


def _render_plan_list(
    plans_data: dict[str, Any],
) -> int | None:
    """Render the student's plans and return the selected plan ID."""

    st.subheader("Danh sách kế hoạch")

    plans = plans_data["items"]

    st.caption(
        f'Tổng số kế hoạch: {plans_data["total"]}'
    )

    if not plans:
        st.info(
            "Bạn chưa có kế hoạch học tập nào. "
            "Hãy tạo kế hoạch đầu tiên."
        )
        return None

    rows = [
        {
            "Tên kế hoạch": plan["title"],
            "Điểm mục tiêu": plan["target_score"],
            "Bắt đầu": _format_date(plan["start_date"]),
            "Kết thúc": _format_date(plan["end_date"]),
            "Phút/ngày": plan["daily_minutes"],
            "Trạng thái": STATUS_LABELS[plan["status"]],
        }
        for plan in plans
    ]

    st.dataframe(
        rows,
        width="stretch",
        hide_index=True,
    )

    plan_by_id = {
        plan["id"]: plan
        for plan in plans
    }

    selected_id = st.selectbox(
        "Chọn kế hoạch để xem chi tiết",
        options=list(plan_by_id),
        format_func=lambda plan_id: (
            f'{plan_by_id[plan_id]["title"]} '
            f'({STATUS_LABELS[plan_by_id[plan_id]["status"]]})'
        ),
        key="toeic_selected_study_plan_id",
    )

    return selected_id


def _render_plan_detail(
    client: StudyPlanAPIClient,
    plan_id: int,
) -> None:
    """Render plan details, tasks, and lifecycle actions."""

    st.subheader("Chi tiết kế hoạch")

    try:
        plan = client.get_study_plan_detail(plan_id)

    except (StudyPlanAPIError, ValueError) as error:
        st.error(str(error))
        return

    st.markdown(f'### {plan["title"]}')

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Điểm mục tiêu",
        plan["target_score"],
    )

    col2.metric(
        "Thời gian mỗi ngày",
        f'{plan["daily_minutes"]} phút',
    )

    col3.metric(
        "Trạng thái",
        STATUS_LABELS[plan["status"]],
    )

    col1, col2 = st.columns(2)

    col1.write(
        f'**Ngày bắt đầu:** {_format_date(plan["start_date"])}'
    )

    col2.write(
        f'**Ngày kết thúc:** {_format_date(plan["end_date"])}'
    )

    _render_lifecycle_actions(client, plan)

    st.divider()
    st.markdown("#### Lịch nhiệm vụ học tập")

    tasks = plan["tasks"]

    if not tasks:
        st.info("Kế hoạch chưa có nhiệm vụ học tập.")
        return

    rows = []

    for task in tasks:
        skill = task["skill"]

        skill_name = (
            skill["name"]
            if skill is not None
            else "Kỹ năng tổng hợp"
        )

        rows.append(
            {
                "Ngày": _format_date(task["scheduled_date"]),
                "Loại nhiệm vụ": TASK_TYPE_LABELS[task["task_type"]],
                "Kỹ năng": skill_name,
                "Thời lượng (phút)": task["estimated_minutes"],
                "Số câu mục tiêu": task["target_question_count"],
                "Trạng thái": TASK_STATUS_LABELS[task["status"]],
            }
        )

    st.dataframe(
        rows,
        width="stretch",
        hide_index=True,
    )

    completed = sum(
        task["status"] == "completed"
        for task in tasks
    )

    completion = (
        completed / len(tasks)
        if tasks
        else 0.0
    )

    st.progress(
        completion,
        text=f"Hoàn thành {completed}/{len(tasks)} nhiệm vụ",
    )


def _run_lifecycle_action(
    action: Callable[[int], dict[str, Any]],
    plan_id: int,
    success_message: str,
) -> None:
    """Execute one lifecycle action and refresh the UI."""

    try:
        action(plan_id)

    except (StudyPlanAPIError, ValueError) as error:
        st.error(str(error))
        return

    st.success(success_message)
    st.rerun()


def _render_lifecycle_actions(
    client: StudyPlanAPIClient,
    plan: dict[str, Any],
) -> None:
    """Display lifecycle actions allowed by the current plan status."""

    plan_id = plan["id"]
    status = plan["status"]

    st.markdown("#### Quản lý trạng thái")

    if status == "active":
        col1, col2 = st.columns(2)

        if col1.button(
            "Tạm dừng kế hoạch",
            key=f"toeic_pause_plan_{plan_id}",
            width="stretch",
        ):
            _run_lifecycle_action(
                client.pause_study_plan,
                plan_id,
                "Đã tạm dừng kế hoạch học tập.",
            )

        if col2.button(
            "Hoàn thành kế hoạch",
            key=f"toeic_complete_plan_{plan_id}",
            width="stretch",
        ):
            st.session_state[
                f"toeic_confirm_complete_{plan_id}"
            ] = True

        if st.session_state.get(
            f"toeic_confirm_complete_{plan_id}",
            False,
        ):
            st.warning(
                "Bạn có chắc chắn muốn đánh dấu kế hoạch này "
                "là đã hoàn thành?"
            )

            confirm_col, cancel_col = st.columns(2)

            if confirm_col.button(
                "Xác nhận hoàn thành",
                key=f"toeic_confirm_complete_button_{plan_id}",
                width="stretch",
            ):
                st.session_state[
                    f"toeic_confirm_complete_{plan_id}"
                ] = False

                _run_lifecycle_action(
                    client.complete_study_plan,
                    plan_id,
                    "Đã hoàn thành kế hoạch học tập.",
                )

            if cancel_col.button(
                "Hủy",
                key=f"toeic_cancel_complete_{plan_id}",
                width="stretch",
            ):
                st.session_state[
                    f"toeic_confirm_complete_{plan_id}"
                ] = False
                st.rerun()

    elif status == "paused":
        if st.button(
            "Tiếp tục kế hoạch",
            key=f"toeic_resume_plan_{plan_id}",
            width="stretch",
        ):
            _run_lifecycle_action(
                client.resume_study_plan,
                plan_id,
                "Đã tiếp tục kế hoạch học tập.",
            )

    elif status == "completed":
        st.success("Kế hoạch này đã hoàn thành.")

    elif status == "cancelled":
        st.info("Kế hoạch này đã bị hủy.")


def render_study_plan_interface(
    api_base_url: str,
) -> None:
    """Render the authenticated student's study planner."""

    st.header("🗓️ Study Planner")

    token = get_active_token(st.session_state)

    if not token:
        st.info(
            "Vui lòng đăng nhập để quản lý kế hoạch học tập."
        )
        return

    st.caption(
        "Tạo kế hoạch TOEIC cá nhân hóa, theo dõi lịch học "
        "và quản lý tiến độ của bạn."
    )

    try:
        with StudyPlanAPIClient(
            base_url=api_base_url,
            access_token=token,
        ) as client:

            _render_create_form(client)

            st.divider()

            plans_data = client.get_study_plans(
                limit=20,
                offset=0,
            )

            selected_plan_id = _render_plan_list(
                plans_data
            )

            if selected_plan_id is not None:
                st.divider()

                _render_plan_detail(
                    client,
                    selected_plan_id,
                )

    except (StudyPlanAPIError, ValueError) as error:
        st.error(str(error))
