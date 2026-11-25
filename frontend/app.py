
"""Streamlit application for TOEIC AI Tutor."""

import os

import streamlit as st

from frontend.api_client import check_backend_health
from frontend.auth_ui import render_authentication
from frontend.dashboard_ui import render_dashboard_interface
from frontend.quiz_ui import render_quiz_interface
from frontend.study_plan_ui import render_study_plan_interface
from frontend.tutor_ui import render_tutor_interface


DEFAULT_API_URL = "http://127.0.0.1:8765"

API_BASE_URL = (
    os.getenv("TOEIC_API_BASE_URL") or DEFAULT_API_URL
).strip().rstrip("/")


# =====================================================
# 1. Navigation configuration
# =====================================================

PAGES = [
    "Dashboard",
    "Study Planner",
    "AI Tutor",
    "TOEIC Quiz",
]


# =====================================================
# 2. Backend health check
# =====================================================

def render_backend_status() -> None:
    """Render backend connection status in the sidebar."""

    with st.expander("Trạng thái hệ thống", expanded=False):
        st.caption(f"FastAPI Backend: {API_BASE_URL}")

        if st.button(
            "Kiểm tra kết nối",
            key="toeic_backend_health_check",
            type="primary",
            width="stretch",
        ):
            with st.spinner("Đang kết nối FastAPI..."):
                result = check_backend_health(API_BASE_URL)

            if result.healthy:
                st.success(result.message)
            else:
                st.error(result.message)


# =====================================================
# 3. Page rendering
# =====================================================

def render_selected_page(page: str) -> None:
    """Render the selected application page."""

    if page == "Dashboard":
        render_dashboard_interface(API_BASE_URL)

    elif page == "Study Planner":
        render_study_plan_interface(API_BASE_URL)

    elif page == "AI Tutor":
        render_tutor_interface(API_BASE_URL)

    elif page == "TOEIC Quiz":
        render_quiz_interface(API_BASE_URL)

    else:
        st.error("Trang được chọn không tồn tại.")


# =====================================================
# 4. Main application
# =====================================================

def main() -> None:
    """Render the TOEIC AI Tutor application."""

    st.set_page_config(
        page_title="TOEIC AI Tutor",
        page_icon="📘",
        layout="centered",
    )

    st.title("📘 TOEIC AI Tutor")

    st.write(
        "Hệ thống gia sư AI cá nhân hóa hỗ trợ "
        "học và luyện thi TOEIC."
    )

    # -------------------------------------------------
    # Sidebar navigation
    # -------------------------------------------------

    with st.sidebar:
        st.title("📚 Điều hướng")

        selected_page = st.radio(
            "Chọn chức năng",
            options=PAGES,
            index=0,
            key="toeic_main_navigation",
        )

        st.divider()

        render_backend_status()

    # -------------------------------------------------
    # Authentication
    # -------------------------------------------------

    render_authentication()

    st.divider()

    # -------------------------------------------------
    # Selected application page
    # -------------------------------------------------

    render_selected_page(selected_page)


if __name__ == "__main__":
    main()
