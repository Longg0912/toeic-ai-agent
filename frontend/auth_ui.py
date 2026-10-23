
"""Streamlit authentication UI for the TOEIC Tutor Agent.

Features:
- Student registration form.
- Student login form.
- JWT access-token session management.
- Current-user profile.
- Logout.

Passwords are not copied to custom session-state fields.
The JWT signing secret is never used by the frontend.
"""

from __future__ import annotations

import time

from collections.abc import MutableMapping
from typing import Any

import streamlit as st

from frontend.auth_api_client import (
    AuthAPIClient,
    AuthAPIError,
    LoginResult,
    PublicUser,
)


TOKEN_KEY = "toeic_auth_access_token"
EXPIRES_AT_KEY = "toeic_auth_expires_at"


# =====================================================
# 1. Session management
# =====================================================


def clear_auth_session(
    state: MutableMapping[str, Any],
) -> None:
    """Remove only authentication data from the session."""

    state.pop(TOKEN_KEY, None)
    state.pop(EXPIRES_AT_KEY, None)


def save_auth_session(
    state: MutableMapping[str, Any],
    login_result: LoginResult,
    *,
    now: float | None = None,
) -> None:
    """Store a JWT and its estimated expiration timestamp."""

    token = login_result.access_token
    lifetime = login_result.expires_in

    if (
        not isinstance(token, str)
        or not token.strip()
        or type(lifetime) is not int
        or lifetime <= 0
    ):
        raise ValueError(
            "Invalid login session data."
        )

    issued_at = (
        time.time()
        if now is None
        else now
    )

    state[TOKEN_KEY] = token
    state[EXPIRES_AT_KEY] = (
        issued_at + lifetime
    )


def get_active_token(
    state: MutableMapping[str, Any],
    *,
    now: float | None = None,
) -> str | None:
    """Return the JWT if the local session has not expired.

    This is a convenience check for the UI.
    FastAPI remains responsible for JWT verification.
    """

    token = state.get(TOKEN_KEY)
    expires_at = state.get(EXPIRES_AT_KEY)

    if not isinstance(token, str) or not token:
        clear_auth_session(state)
        return None

    if (
        isinstance(expires_at, bool)
        or not isinstance(expires_at, (int, float))
    ):
        clear_auth_session(state)
        return None

    current_time = (
        time.time()
        if now is None
        else now
    )

    if current_time >= expires_at:
        clear_auth_session(state)
        return None

    return token


# =====================================================
# 2. Login form
# =====================================================


def _render_login_form(
    client: AuthAPIClient,
) -> None:
    """Display and handle the student login form."""

    st.markdown("#### Đăng nhập")

    with st.form(
        "toeic_login_form",
        clear_on_submit=True,
    ):
        email = st.text_input(
            "Email đăng nhập",
            placeholder="student@example.com",
            key="toeic_login_email",
        )

        password = st.text_input(
            "Mật khẩu đăng nhập",
            type="password",
            key="toeic_login_password",
        )

        submitted = st.form_submit_button(
            "Đăng nhập",
            key="toeic_login_submit",
            use_container_width=True,
        )

    if not submitted:
        return

    email = email.strip()

    if not email or not password:
        st.error(
            "Vui lòng nhập đầy đủ email và mật khẩu."
        )
        return

    try:
        # First authenticate and obtain an access token.
        result = client.login(
            email=email,
            password=password,
        )

        # Confirm that the token represents
        # an existing, active account.
        user = client.get_me(
            result.access_token
        )

        if not user.is_active:
            st.error(
                "Không thể xác thực tài khoản."
            )
            return

    except AuthAPIError as error:
        st.error(str(error))
        return

    # Only save a token after successful verification.
    save_auth_session(
        st.session_state,
        result,
    )

    st.rerun()


# =====================================================
# 3. Registration form
# =====================================================


def _render_registration_form(
    client: AuthAPIClient,
) -> None:
    """Display and handle student registration."""

    st.markdown("#### Đăng ký tài khoản")

    with st.form(
        "toeic_registration_form",
        clear_on_submit=True,
    ):
        email = st.text_input(
            "Email đăng ký",
            placeholder="student@example.com",
            key="toeic_register_email",
        )

        password = st.text_input(
            "Mật khẩu mới",
            type="password",
            help="Mật khẩu cần có từ 12 đến 128 ký tự.",
            key="toeic_register_password",
        )

        confirmation = st.text_input(
            "Xác nhận mật khẩu",
            type="password",
            key="toeic_register_confirmation",
        )

        submitted = st.form_submit_button(
            "Tạo tài khoản",
            key="toeic_register_submit",
            use_container_width=True,
        )

    if not submitted:
        return

    email = email.strip()

    if not email or not password or not confirmation:
        st.error(
            "Vui lòng nhập đầy đủ các trường."
        )
        return

    if password != confirmation:
        st.error(
            "Mật khẩu xác nhận không khớp."
        )
        return

    if not 12 <= len(password) <= 128:
        st.error(
            "Mật khẩu phải có từ 12 đến 128 ký tự."
        )
        return

    try:
        client.register(
            email=email,
            password=password,
        )

    except AuthAPIError as error:
        st.error(str(error))
        return

    st.success(
        "Đăng ký thành công! "
        "Hãy chuyển sang tab Đăng nhập."
    )


# =====================================================
# 4. Current user profile
# =====================================================


def _render_profile(
    user: PublicUser,
) -> None:
    """Display only public account information."""

    st.success("Bạn đang đăng nhập.")

    st.markdown("#### Hồ sơ học viên")

    st.write(f"**User ID:** {user.id}")
    st.write(f"**Email:** {user.email}")
    st.write(f"**Vai trò:** {user.role}")
    st.write(
        "**Trạng thái:** "
        + (
            "Đang hoạt động"
            if user.is_active
            else "Không hoạt động"
        )
    )

    if st.button(
        "Đăng xuất",
        key="toeic_logout",
        use_container_width=True,
    ):
        clear_auth_session(
            st.session_state
        )
        st.rerun()


# =====================================================
# 5. Main authentication UI
# =====================================================


def render_authentication(
    api_client: AuthAPIClient | None = None,
) -> None:
    """Render login, registration, or the current profile."""

    st.subheader("Tài khoản TOEIC")

    try:
        client = (
            api_client
            if api_client is not None
            else AuthAPIClient()
        )

    except ValueError:
        st.error(
            "Cấu hình địa chỉ Backend không hợp lệ."
        )
        return

    had_token = TOKEN_KEY in st.session_state

    token = get_active_token(
        st.session_state
    )

    if had_token and token is None:
        st.warning(
            "Phiên đăng nhập đã hết hạn. "
            "Vui lòng đăng nhập lại."
        )

    if token is not None:
        try:
            user = client.get_me(token)

            if not user.is_active:
                clear_auth_session(
                    st.session_state
                )
                st.warning(
                    "Phiên đăng nhập không còn hợp lệ."
                )

            else:
                _render_profile(user)
                return

        except AuthAPIError as error:
            if error.status_code in (401, 403):
                clear_auth_session(
                    st.session_state
                )
                st.warning(
                    "Phiên đăng nhập không còn hợp lệ. "
                    "Vui lòng đăng nhập lại."
                )

            else:
                # Do not discard a potentially valid
                # session on transient network errors.
                st.error(str(error))

                if st.button(
                    "Đăng xuất",
                    key="toeic_logout_on_error",
                ):
                    clear_auth_session(
                        st.session_state
                    )
                    st.rerun()

                return

    # Anonymous users see the login/register forms.
    login_tab, register_tab = st.tabs(
        ["Đăng nhập", "Đăng ký"]
    )

    with login_tab:
        _render_login_form(client)

    with register_tab:
        _render_registration_form(client)
