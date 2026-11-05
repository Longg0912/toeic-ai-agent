"""Streamlit authentication UI for the TOEIC Tutor Agent.

Features:
- Student registration form.
- Student login form.
- JWT access-token session management.
- Encrypted cookie persistence.
- Restore login after browser refresh.
- Current-user profile.
- Logout.

Passwords are not copied to custom session-state fields.
The JWT signing secret is never used by the frontend.
"""

from __future__ import annotations

import math
import os
import time

from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

import streamlit as st
from dotenv import load_dotenv
from streamlit_cookies_manager import EncryptedCookieManager

from frontend.auth_api_client import (
    AuthAPIClient,
    AuthAPIError,
    LoginResult,
    PublicUser,
)


# =====================================================
# 1. Constants and configuration
# =====================================================

TOKEN_KEY = "toeic_auth_access_token"
EXPIRES_AT_KEY = "toeic_auth_expires_at"

COOKIE_TOKEN_KEY = "access_token"
COOKIE_EXPIRES_AT_KEY = "expires_at"

PROJECT_ROOT = Path(__file__).resolve().parents[1]

COOKIE_PREFIX = "toeic-ai-tutor/"


# =====================================================
# 2. Cookie manager
# =====================================================


def _create_cookie_manager() -> EncryptedCookieManager | None:
    """Create and initialize the encrypted cookie manager."""

    load_dotenv(PROJECT_ROOT / ".env")

    cookie_password = os.getenv("TOEIC_COOKIE_PASSWORD")

    if not cookie_password:
        st.error(
            "Chưa cấu hình TOEIC_COOKIE_PASSWORD trong file .env. "
            "Vui lòng bổ sung mật khẩu mã hóa cookie."
        )
        return None

    cookies = EncryptedCookieManager(
        prefix=COOKIE_PREFIX,
        password=cookie_password,
    )

    if not cookies.ready():
        with st.spinner("Đang khởi tạo phiên đăng nhập..."):
            st.stop()

    return cookies


def _clear_auth_cookies(
    cookies: EncryptedCookieManager,
) -> None:
    """Invalidate authentication cookies instead of deleting them."""

    cookies[COOKIE_TOKEN_KEY] = "logged_out"
    cookies[COOKIE_EXPIRES_AT_KEY] = "0"

    cookies.save()

    # Allow the browser time to process the cookie update.
    time.sleep(0.5)


# =====================================================
# 3. Session management
# =====================================================


def clear_auth_session(
    state: MutableMapping[str, Any],
    cookies: EncryptedCookieManager | None = None,
) -> None:
    """Remove authentication data from session state and cookies."""

    state.pop(TOKEN_KEY, None)
    state.pop(EXPIRES_AT_KEY, None)

    if cookies is not None:
        _clear_auth_cookies(cookies)


def save_auth_session(
    state: MutableMapping[str, Any],
    login_result: LoginResult,
    *,
    cookies: EncryptedCookieManager | None = None,
    now: float | None = None,
) -> None:
    """Save JWT and expiration timestamp to session state and cookies."""

    token = login_result.access_token
    lifetime = login_result.expires_in

    if (
        not isinstance(token, str)
        or not token.strip()
        or type(lifetime) is not int
        or lifetime <= 0
    ):
        raise ValueError("Invalid login session data.")

    issued_at = time.time() if now is None else now
    expires_at = issued_at + lifetime

    state[TOKEN_KEY] = token
    state[EXPIRES_AT_KEY] = expires_at

    if cookies is not None:
        cookies[COOKIE_TOKEN_KEY] = token
        cookies[COOKIE_EXPIRES_AT_KEY] = str(expires_at)
        cookies.save()


def get_active_token(
    state: MutableMapping[str, Any],
    *,
    now: float | None = None,
) -> str | None:
    """Return the JWT if the local session has not expired.

    FastAPI remains responsible for verifying the JWT.
    """

    token = state.get(TOKEN_KEY)
    expires_at = state.get(EXPIRES_AT_KEY)

    if not isinstance(token, str) or not token.strip():
        clear_auth_session(state)
        return None

    if (
        isinstance(expires_at, bool)
        or not isinstance(expires_at, (int, float))
        or not math.isfinite(expires_at)
    ):
        clear_auth_session(state)
        return None

    current_time = time.time() if now is None else now

    if current_time >= expires_at:
        clear_auth_session(state)
        return None

    return token


def restore_auth_session(
    state: MutableMapping[str, Any],
    cookies: EncryptedCookieManager,
    *,
    now: float | None = None,
) -> str | None:
    """Restore a valid authentication session from browser cookies."""

    token = cookies.get(COOKIE_TOKEN_KEY)
    raw_expires_at = cookies.get(COOKIE_EXPIRES_AT_KEY)

    # No authentication cookie exists.
    if token is None and raw_expires_at is None:
        return None

    # Explicitly logged-out sessions must never be restored.
    if token == "logged_out":
        return None

    if (
        not isinstance(token, str)
        or not token.strip()
        or raw_expires_at is None
    ):
        return None

    try:
        expires_at = float(raw_expires_at)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(expires_at):
        return None

    current_time = time.time() if now is None else now

    if current_time >= expires_at:
        return None

    state[TOKEN_KEY] = token
    state[EXPIRES_AT_KEY] = expires_at

    return token


# =====================================================
# 4. Login form
# =====================================================


def _render_login_form(
    client: AuthAPIClient,
    cookies: EncryptedCookieManager,
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
        st.error("Vui lòng nhập đầy đủ email và mật khẩu.")
        return

    try:
        # Authenticate and obtain an access token.
        result = client.login(
            email=email,
            password=password,
        )

        # Verify that the token belongs to an active account.
        user = client.get_me(result.access_token)

        if not user.is_active:
            st.error("Không thể xác thực tài khoản.")
            return

    except AuthAPIError as error:
        st.error(str(error))
        return

    # Save the session only after successful verification.
    save_auth_session(
        st.session_state,
        result,
        cookies=cookies,
    )

    st.rerun()


# =====================================================
# 5. Registration form
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
        st.error("Vui lòng nhập đầy đủ các trường.")
        return

    if password != confirmation:
        st.error("Mật khẩu xác nhận không khớp.")
        return

    if not 12 <= len(password) <= 128:
        st.error("Mật khẩu phải có từ 12 đến 128 ký tự.")
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
# 6. Current user profile
# =====================================================


def _render_profile(
    user: PublicUser,
    cookies: EncryptedCookieManager,
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
            st.session_state,
            cookies,
        )
        st.rerun()


# =====================================================
# 7. Main authentication UI
# =====================================================


def render_authentication(
    api_client: AuthAPIClient | None = None,
) -> None:
    """Render login, registration, or the current profile."""

    st.subheader("Tài khoản TOEIC")

    # Initialize encrypted cookies.
    cookies = _create_cookie_manager()

    if cookies is None:
        return

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

    # First check the current Streamlit session.
    token = get_active_token(st.session_state)

    # If the session is empty, try restoring from cookies.
    if token is None:
        token = restore_auth_session(
            st.session_state,
            cookies,
        )

    if had_token and token is None:
        st.warning(
            "Phiên đăng nhập đã hết hạn. "
            "Vui lòng đăng nhập lại."
        )

    # -------------------------------------------------
    # Authenticated user
    # -------------------------------------------------

    if token is not None:
        try:
            user = client.get_me(token)

            if not user.is_active:
                clear_auth_session(
                    st.session_state,
                    cookies,
                )

                st.warning(
                    "Phiên đăng nhập không còn hợp lệ."
                )

            else:
                _render_profile(
                    user,
                    cookies,
                )
                return

        except AuthAPIError as error:
            if error.status_code in (401, 403):
                clear_auth_session(
                    st.session_state,
                    cookies,
                )

                st.warning(
                    "Phiên đăng nhập không còn hợp lệ. "
                    "Vui lòng đăng nhập lại."
                )

            else:
                # Keep the session if the error is temporary.
                st.error(str(error))

                if st.button(
                    "Đăng xuất",
                    key="toeic_logout_on_error",
                ):
                    clear_auth_session(
                        st.session_state,
                        cookies,
                    )
                    st.rerun()

                return

    # -------------------------------------------------
    # Anonymous user
    # -------------------------------------------------

    login_tab, register_tab = st.tabs(
        ["Đăng nhập", "Đăng ký"]
    )

    with login_tab:
        _render_login_form(
            client,
            cookies,
        )

    with register_tab:
        _render_registration_form(client)