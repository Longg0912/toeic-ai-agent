"""Streamlit application for TOEIC AI Tutor."""

import os

import streamlit as st

from frontend.api_client import check_backend_health
from frontend.auth_ui import render_authentication
from frontend.quiz_ui import render_quiz_interface


DEFAULT_API_URL = "http://127.0.0.1:8765"

API_BASE_URL = (
    os.getenv("TOEIC_API_BASE_URL") or DEFAULT_API_URL
).strip().rstrip("/")


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

    with st.container(border=True):
        st.subheader("Trạng thái hệ thống")
        st.caption(f"FastAPI Backend: {API_BASE_URL}")

        if st.button(
            "Kiểm tra kết nối",
            type="primary",
            use_container_width=True,
        ):
            with st.spinner("Đang kết nối FastAPI..."):
                result = check_backend_health(API_BASE_URL)

            if result.healthy:
                st.success(result.message)
            else:
                st.error(result.message)

    st.divider()

    render_authentication()

    st.divider()

    render_quiz_interface(API_BASE_URL)


if __name__ == "__main__":
    main()