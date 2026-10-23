
"""Tests for Streamlit authentication UI and session state.

These tests:
- Do not require a running FastAPI server.
- Do not access the production database.
- Do not use real access tokens or passwords.
"""

import time

import pytest

from streamlit.testing.v1 import AppTest

import frontend.auth_ui as auth_ui

from frontend.auth_api_client import (
    AuthAPIError,
    LoginResult,
    PublicUser,
)

from frontend.auth_ui import (
    TOKEN_KEY,
    EXPIRES_AT_KEY,
    clear_auth_session,
    get_active_token,
    save_auth_session,
)


EMAIL = "student@example.com"
PASSWORD = "ExamplePassword@2026"
TEST_TOKEN = "test.jwt.access-token"


class FakeAuthAPIClient:
    """In-memory substitute for AuthAPIClient."""

    def __init__(self) -> None:
        self.login_calls = []
        self.register_calls = []
        self.get_me_calls = []

        self.login_error = None
        self.register_error = None
        self.get_me_error = None

    def login(
        self,
        email: str,
        password: str,
    ) -> LoginResult:
        self.login_calls.append((email, password))

        if self.login_error is not None:
            raise self.login_error

        return LoginResult(
            access_token=TEST_TOKEN,
            token_type="bearer",
            expires_in=1800,
        )

    def register(
        self,
        email: str,
        password: str,
    ) -> PublicUser:
        self.register_calls.append((email, password))

        if self.register_error is not None:
            raise self.register_error

        return PublicUser(
            id=15,
            email=email,
            role="student",
            is_active=True,
        )

    def get_me(
        self,
        access_token: str,
    ) -> PublicUser:
        self.get_me_calls.append(access_token)

        if self.get_me_error is not None:
            raise self.get_me_error

        return PublicUser(
            id=15,
            email=EMAIL,
            role="student",
            is_active=True,
        )


def start_test_app(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeAuthAPIClient,
) -> AppTest:
    """Launch only the authentication UI inside AppTest."""

    monkeypatch.setattr(
        auth_ui,
        "AuthAPIClient",
        lambda: fake_client,
    )

    return AppTest.from_string(
        "from frontend.auth_ui import render_authentication\n"
        "render_authentication()\n",
        default_timeout=10,
    ).run()


def fill_login_form(app: AppTest) -> None:
    """Simulate entering login credentials."""

    app.text_input(
        key="toeic_login_email"
    ).set_value(EMAIL)

    app.text_input(
        key="toeic_login_password"
    ).set_value(PASSWORD)


def fill_registration_form(
    app: AppTest,
    *,
    confirmation: str = PASSWORD,
) -> None:
    """Simulate entering registration information."""

    app.text_input(
        key="toeic_register_email"
    ).set_value(EMAIL)

    app.text_input(
        key="toeic_register_password"
    ).set_value(PASSWORD)

    app.text_input(
        key="toeic_register_confirmation"
    ).set_value(confirmation)


# =====================================================
# Group A — Session-state unit tests
# =====================================================


def test_save_session_stores_token_and_expiration() -> None:
    """Only the token and expiration are stored."""

    state = {}

    result = LoginResult(
        access_token=TEST_TOKEN,
        token_type="bearer",
        expires_in=1800,
    )

    save_auth_session(
        state,
        result,
        now=1000,
    )

    assert state == {
        TOKEN_KEY: TEST_TOKEN,
        EXPIRES_AT_KEY: 2800,
    }

    assert PASSWORD not in repr(state)


def test_clear_session_keeps_unrelated_state() -> None:
    """Logout must not delete unrelated Streamlit data."""

    state = {
        TOKEN_KEY: TEST_TOKEN,
        EXPIRES_AT_KEY: 2800,
        "theme_preference": "dark",
    }

    clear_auth_session(state)

    assert TOKEN_KEY not in state
    assert EXPIRES_AT_KEY not in state
    assert state["theme_preference"] == "dark"


def test_expired_session_is_cleared() -> None:
    """Local expiration removes the existing token."""

    state = {
        TOKEN_KEY: TEST_TOKEN,
        EXPIRES_AT_KEY: 2000,
    }

    token = get_active_token(
        state,
        now=2000,
    )

    assert token is None
    assert TOKEN_KEY not in state
    assert EXPIRES_AT_KEY not in state


def test_missing_expiration_is_rejected() -> None:
    """A token without a valid expiration is not usable."""

    state = {
        TOKEN_KEY: TEST_TOKEN,
    }

    assert get_active_token(
        state,
        now=1000,
    ) is None

    assert TOKEN_KEY not in state


def test_invalid_login_result_is_not_saved() -> None:
    """Reject invalid token or lifetime."""

    state = {}

    invalid = LoginResult(
        access_token="",
        token_type="bearer",
        expires_in=1800,
    )

    with pytest.raises(ValueError):
        save_auth_session(state, invalid)

    assert TOKEN_KEY not in state


# =====================================================
# Group B — Streamlit UI tests
# =====================================================


def test_anonymous_ui_renders_login_and_register(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Anonymous users can see both forms."""

    fake = FakeAuthAPIClient()

    app = start_test_app(
        monkeypatch,
        fake,
    )

    assert len(app.exception) == 0

    assert app.text_input(
        key="toeic_login_email"
    ) is not None

    assert app.text_input(
        key="toeic_register_email"
    ) is not None

    assert fake.login_calls == []
    assert fake.register_calls == []


def test_successful_login_displays_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Correct credentials create a session and profile."""

    fake = FakeAuthAPIClient()
    app = start_test_app(monkeypatch, fake)

    fill_login_form(app)

    app.button(
        key="toeic_login_submit"
    ).click().run()

    # Also handle a Streamlit rerun after login.
    app.run()

    assert len(app.exception) == 0

    assert fake.login_calls == [
        (EMAIL, PASSWORD)
    ]

    assert TEST_TOKEN in fake.get_me_calls

    assert app.session_state[TOKEN_KEY] == TEST_TOKEN

    assert app.button(
        key="toeic_logout"
    ) is not None


def test_failed_login_does_not_create_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An invalid password cannot create a login session."""

    fake = FakeAuthAPIClient()

    fake.login_error = AuthAPIError(
        "Email hoặc mật khẩu không đúng.",
        status_code=401,
    )

    app = start_test_app(monkeypatch, fake)

    fill_login_form(app)

    app.button(
        key="toeic_login_submit"
    ).click().run()

    assert len(app.exception) == 0

    assert fake.login_calls == [
        (EMAIL, PASSWORD)
    ]

    assert fake.get_me_calls == []


def test_registration_password_mismatch_stops_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Confirmation mismatch must not call register()."""

    fake = FakeAuthAPIClient()
    app = start_test_app(monkeypatch, fake)

    fill_registration_form(
        app,
        confirmation="DifferentPassword@2026",
    )

    app.button(
        key="toeic_register_submit"
    ).click().run()

    assert len(app.exception) == 0

    assert fake.register_calls == []

    assert any(
    "không khớp" in element.value
    for element in app.error
    )


def test_registration_success_does_not_auto_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Registration succeeds without automatically saving a JWT."""

    fake = FakeAuthAPIClient()
    app = start_test_app(monkeypatch, fake)

    fill_registration_form(app)

    app.button(
        key="toeic_register_submit"
    ).click().run()

    assert len(app.exception) == 0

    assert fake.register_calls == [
        (EMAIL, PASSWORD)
    ]

    assert fake.login_calls == []

    assert any(
        "Đăng ký thành công" in element.value
        for element in app.success
    )


def test_logout_removes_authentication_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clicking logout removes the JWT from session state."""

    fake = FakeAuthAPIClient()
    app = start_test_app(monkeypatch, fake)

    app.session_state[TOKEN_KEY] = TEST_TOKEN
    app.session_state[EXPIRES_AT_KEY] = (
        time.time() + 1800
    )

    app.run()

    assert len(app.exception) == 0

    app.button(
        key="toeic_logout"
    ).click().run()

    assert len(app.exception) == 0

    # Anonymous forms must appear after logout.
    assert app.text_input(
        key="toeic_login_email"
    ) is not None


def test_expired_session_shows_login_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Locally expired sessions return to anonymous UI."""

    fake = FakeAuthAPIClient()
    app = start_test_app(monkeypatch, fake)

    app.session_state[TOKEN_KEY] = TEST_TOKEN
    app.session_state[EXPIRES_AT_KEY] = (
        time.time() - 10
    )

    app.run()

    assert len(app.exception) == 0

    assert app.text_input(
        key="toeic_login_email"
    ) is not None


def test_backend_401_rejects_existing_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Backend revocation or invalid JWT forces a new login."""

    fake = FakeAuthAPIClient()

    fake.get_me_error = AuthAPIError(
        "Phiên đăng nhập không hợp lệ.",
        status_code=401,
    )

    app = start_test_app(monkeypatch, fake)

    app.session_state[TOKEN_KEY] = TEST_TOKEN
    app.session_state[EXPIRES_AT_KEY] = (
        time.time() + 1800
    )

    app.run()

    assert len(app.exception) == 0

    assert app.text_input(
        key="toeic_login_email"
    ) is not None


def test_transient_backend_error_keeps_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A network failure must not silently log out the user."""

    fake = FakeAuthAPIClient()

    fake.get_me_error = AuthAPIError(
        "Không thể kết nối tới Backend."
    )

    app = start_test_app(monkeypatch, fake)

    app.session_state[TOKEN_KEY] = TEST_TOKEN
    app.session_state[EXPIRES_AT_KEY] = (
        time.time() + 1800
    )

    app.run()

    assert len(app.exception) == 0

    assert app.session_state[TOKEN_KEY] == TEST_TOKEN

    assert app.button(
        key="toeic_logout_on_error"
    ) is not None
