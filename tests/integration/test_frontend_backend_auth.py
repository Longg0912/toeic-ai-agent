
"""Frontend-Backend authentication integration tests.

Real components:
- frontend.auth_api_client.AuthAPIClient
- frontend.auth_ui.render_authentication
- backend.app.main.app (FastAPI)
- SQLAlchemy ORM
- Alembic migrations
- JWT signing and validation

Test isolation:
- Temporary SQLite database
- Test-only JWT secret
- No listening TCP socket
- No production database changes
"""

from collections.abc import Iterator
from pathlib import Path
import time

import httpx
import jwt
import pytest

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from streamlit.testing.v1 import AppTest

import frontend.auth_ui as auth_ui

from backend.app.api.deps import get_db
from backend.app.db.models import User
from backend.app.db.session import make_engine
from backend.app.main import app as fastapi_app

from frontend.auth_api_client import (
    AuthAPIClient,
    AuthAPIError,
    LoginResult,
    PublicUser,
)
from frontend.auth_ui import (
    TOKEN_KEY,
    EXPIRES_AT_KEY,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"

TEST_SECRET = "integration-test-only-" + ("x" * 64)
TEST_PASSWORD = "IntegrationPassword@2026"
TEST_EMAIL = "student@example.com"


# =====================================================
# 1. HTTPX -> FastAPI TestClient bridge
# =====================================================


class FastAPITestTransport(httpx.BaseTransport):
    """Forward synchronous HTTPX requests to real FastAPI.

    AuthAPIClient uses httpx.Client, which is synchronous.
    httpx.ASGITransport is asynchronous, so it cannot be
    passed directly to that synchronous client.

    This adapter calls FastAPI TestClient instead.
    """

    def __init__(
        self,
        test_client: TestClient,
    ) -> None:
        self.test_client = test_client

    def handle_request(
        self,
        request: httpx.Request,
    ) -> httpx.Response:
        """Execute an actual ASGI request through TestClient."""

        backend_response = self.test_client.request(
            method=request.method,
            url=str(request.url),
            headers=dict(request.headers),
            content=request.read(),
            follow_redirects=False,
        )

        return httpx.Response(
            status_code=backend_response.status_code,
            headers=backend_response.headers,
            content=backend_response.content,
            request=request,
        )

    def close(self) -> None:
        """TestClient lifetime belongs to the pytest fixture.

        AuthAPIClient creates and closes an httpx.Client
        for each operation. Closing this bridge must not
        close the shared FastAPI TestClient prematurely.
        """
        return None


# =====================================================
# 2. Isolated database and application fixture
# =====================================================


@pytest.fixture
def integration_stack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[AuthAPIClient, Engine]]:
    """Provide real FastAPI connected to temporary SQLite."""

    # Never use the production JWT secret for tests.
    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        TEST_SECRET,
    )

    database_path = (
        tmp_path / "auth_integration.sqlite3"
    )

    database_url = (
        "sqlite+pysqlite:///"
        f"{database_path.as_posix()}"
    )

    engine = make_engine(database_url)

    # Keep any previous override so it can be restored.
    previous_override = (
        fastapi_app.dependency_overrides.get(get_db)
    )

    try:
        # 1. Apply existing migrations to TEMP SQLite.
        alembic_config = Config(
            str(ALEMBIC_INI)
        )

        with engine.begin() as connection:
            alembic_config.attributes["connection"] = (
                connection
            )

            command.upgrade(
                alembic_config,
                "head",
            )

        # 2. Redirect the real FastAPI database dependency.
        def override_get_db() -> Iterator[Session]:
            with Session(engine) as session:
                yield session

        fastapi_app.dependency_overrides[get_db] = (
            override_get_db
        )

        # 3. Start FastAPI TestClient without a TCP port.
        with TestClient(fastapi_app) as backend_client:
            transport = FastAPITestTransport(
                backend_client
            )

            # 4. Use the real frontend HTTP client.
            frontend_client = AuthAPIClient(
                base_url="http://127.0.0.1:8765",
                transport=transport,
            )

            yield frontend_client, engine

    finally:
        # Restore the previous application configuration.
        if previous_override is None:
            fastapi_app.dependency_overrides.pop(
                get_db,
                None,
            )
        else:
            fastapi_app.dependency_overrides[get_db] = (
                previous_override
            )

        engine.dispose()


# =====================================================
# 3. Test helpers
# =====================================================


def register_test_user(
    client: AuthAPIClient,
    email: str = TEST_EMAIL,
) -> PublicUser:
    return client.register(
        email=email,
        password=TEST_PASSWORD,
    )


def read_db_user(
    engine: Engine,
    user_id: int,
) -> User | None:
    with Session(engine) as session:
        return session.get(User, user_id)


def disable_db_user(
    engine: Engine,
    user_id: int,
) -> None:
    """Disable an account only inside temporary SQLite."""

    with Session(engine) as session:
        user = session.get(User, user_id)

        assert user is not None

        user.is_active = False
        session.commit()


def start_streamlit_ui(
    monkeypatch: pytest.MonkeyPatch,
    api_client: AuthAPIClient,
) -> AppTest:
    """Use the real AuthAPIClient inside Streamlit AppTest."""

    monkeypatch.setattr(
        auth_ui,
        "AuthAPIClient",
        lambda: api_client,
    )

    script = (
        "from frontend.auth_ui "
        "import render_authentication\n"
        "render_authentication()\n"
    )

    return AppTest.from_string(
        script,
        default_timeout=15,
    ).run()


# =====================================================
# Group A - Real Register / Login / Current User
# =====================================================


def test_full_register_login_profile(
    integration_stack,
) -> None:
    """Register -> SQLite -> Login -> JWT -> /auth/me."""

    client, engine = integration_stack

    registered = register_test_user(client)

    assert isinstance(registered, PublicUser)
    assert registered.id > 0
    assert registered.email == TEST_EMAIL
    assert registered.role == "student"
    assert registered.is_active is True

    # The real SQLAlchemy database contains this user.
    with Session(engine) as session:
        db_user = session.get(User, registered.id)

        assert db_user is not None
        assert db_user.email == TEST_EMAIL

    # The real login endpoint verifies the password.
    login_result = client.login(
        TEST_EMAIL,
        TEST_PASSWORD,
    )

    assert isinstance(login_result, LoginResult)
    assert login_result.access_token
    assert login_result.token_type == "bearer"
    assert login_result.expires_in > 0

    # The real /auth/me endpoint verifies the JWT.
    profile = client.get_me(
        login_result.access_token
    )

    assert profile.id == registered.id
    assert profile.email == registered.email
    assert profile.role == "student"


def test_registration_normalizes_email(
    integration_stack,
) -> None:
    """Email normalization works end to end."""

    client, _ = integration_stack

    registered = register_test_user(
        client,
        "Student@Example.COM",
    )

    assert registered.email == "student@example.com"

    login_result = client.login(
        "student@example.com",
        TEST_PASSWORD,
    )

    profile = client.get_me(
        login_result.access_token
    )

    assert profile.id == registered.id


def test_duplicate_registration_returns_409(
    integration_stack,
) -> None:
    """SQLite uniqueness is surfaced through the API client."""

    client, _ = integration_stack

    first = register_test_user(client)

    with pytest.raises(AuthAPIError) as error:
        register_test_user(
            client,
            "STUDENT@example.com",
        )

    assert error.value.status_code == 409
    assert "đã được đăng ký" in str(error.value)

    # The original account must remain usable.
    login = client.login(
        TEST_EMAIL,
        TEST_PASSWORD,
    )

    assert client.get_me(
        login.access_token
    ).id == first.id


def test_invalid_registration_email_returns_422(
    integration_stack,
) -> None:
    client, _ = integration_stack

    with pytest.raises(AuthAPIError) as error:
        register_test_user(
            client,
            "invalid-email",
        )

    assert error.value.status_code == 422
    assert "Dữ liệu không hợp lệ" in str(error.value)


def test_short_registration_password_returns_422(
    integration_stack,
) -> None:
    client, _ = integration_stack

    with pytest.raises(AuthAPIError) as error:
        client.register(
            TEST_EMAIL,
            "short",
        )

    assert error.value.status_code == 422


# =====================================================
# Group B - Login and JWT security
# =====================================================


def test_wrong_password_returns_401(
    integration_stack,
) -> None:
    client, _ = integration_stack

    register_test_user(client)

    with pytest.raises(AuthAPIError) as error:
        client.login(
            TEST_EMAIL,
            "WrongPassword@2026",
        )

    assert error.value.status_code == 401
    assert "Email hoặc mật khẩu" in str(error.value)


def test_unknown_email_returns_401(
    integration_stack,
) -> None:
    client, _ = integration_stack

    with pytest.raises(AuthAPIError) as error:
        client.login(
            "unknown@example.com",
            TEST_PASSWORD,
        )

    assert error.value.status_code == 401


def test_tampered_access_token_returns_401(
    integration_stack,
) -> None:
    """A changed JWT signature cannot authenticate."""

    client, _ = integration_stack

    register_test_user(client)

    login = client.login(
        TEST_EMAIL,
        TEST_PASSWORD,
    )

    pieces = login.access_token.split(".")

    assert len(pieces) == 3

    signature = pieces[2]
    assert signature

    replacement = (
        "A"
        if signature[0] != "A"
        else "B"
    )

    pieces[2] = replacement + signature[1:]

    tampered_token = ".".join(pieces)

    with pytest.raises(AuthAPIError) as error:
        client.get_me(tampered_token)

    assert error.value.status_code == 401


def test_expired_access_token_returns_401(
    integration_stack,
) -> None:
    """FastAPI rejects an expired signed JWT."""

    client, _ = integration_stack

    register_test_user(client)

    login = client.login(
        TEST_EMAIL,
        TEST_PASSWORD,
    )

    # Decode the test token only to prepare a deliberately
    # expired JWT. Never do this in production authorization.
    claims = jwt.decode(
        login.access_token,
        options={"verify_signature": False},
    )

    claims["exp"] = int(time.time()) - 60

    expired_token = jwt.encode(
        claims,
        TEST_SECRET,
        algorithm="HS256",
    )

    with pytest.raises(AuthAPIError) as error:
        client.get_me(expired_token)

    assert error.value.status_code == 401


def test_disabled_account_loses_access(
    integration_stack,
) -> None:
    """A previously issued JWT cannot access an inactive user."""

    client, engine = integration_stack

    registered = register_test_user(client)

    login = client.login(
        TEST_EMAIL,
        TEST_PASSWORD,
    )

    # Confirm access before disabling.
    assert client.get_me(
        login.access_token
    ).id == registered.id

    disable_db_user(
        engine,
        registered.id,
    )

    # The exact same JWT must now fail.
    with pytest.raises(AuthAPIError) as error:
        client.get_me(login.access_token)

    assert error.value.status_code == 401


# =====================================================
# Group C - Account isolation and privacy
# =====================================================


def test_access_tokens_identify_separate_users(
    integration_stack,
) -> None:
    """JWTs must resolve to their respective account."""

    client, _ = integration_stack

    user_a = register_test_user(
        client,
        "a@example.com",
    )

    user_b = register_test_user(
        client,
        "b@example.com",
    )

    login_a = client.login(
        "a@example.com",
        TEST_PASSWORD,
    )

    login_b = client.login(
        "b@example.com",
        TEST_PASSWORD,
    )

    profile_a = client.get_me(
        login_a.access_token
    )

    profile_b = client.get_me(
        login_b.access_token
    )

    assert profile_a.id == user_a.id
    assert profile_b.id == user_b.id
    assert profile_a.id != profile_b.id

    assert profile_a.email == "a@example.com"
    assert profile_b.email == "b@example.com"


def test_public_user_does_not_expose_password_hash(
    integration_stack,
) -> None:
    """Password hash stays in the database, not the frontend."""

    client, engine = integration_stack

    registered = register_test_user(client)

    login = client.login(
        TEST_EMAIL,
        TEST_PASSWORD,
    )

    profile = client.get_me(
        login.access_token
    )

    with Session(engine) as session:
        db_user = session.get(User, registered.id)

        assert db_user is not None

        # Backend stored a password hash, not plaintext.
        assert db_user.password_hash
        assert db_user.password_hash != TEST_PASSWORD

        # It must not appear in the public frontend model.
        assert not hasattr(profile, "password_hash")
        assert db_user.password_hash not in repr(profile)

    assert login.access_token not in repr(login)


# =====================================================
# Group D - Streamlit + real FastAPI integration
# =====================================================


def test_streamlit_registration_uses_real_backend(
    integration_stack,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Streamlit form creates a real user in test SQLite."""

    client, _ = integration_stack

    ui = start_streamlit_ui(
        monkeypatch,
        client,
    )

    ui.text_input(
        key="toeic_register_email"
    ).set_value(TEST_EMAIL)

    ui.text_input(
        key="toeic_register_password"
    ).set_value(TEST_PASSWORD)

    ui.text_input(
        key="toeic_register_confirmation"
    ).set_value(TEST_PASSWORD)

    ui.button(
        key="toeic_register_submit"
    ).click().run()

    assert len(ui.exception) == 0

    assert any(
        "Đăng ký thành công" in element.value
        for element in ui.success
    )

    # No auto-login; but the account now works
    # through the real FastAPI login endpoint.
    login = client.login(
        TEST_EMAIL,
        TEST_PASSWORD,
    )

    profile = client.get_me(
        login.access_token
    )

    assert profile.email == TEST_EMAIL
    assert profile.role == "student"


def test_streamlit_login_profile_logout_real_backend(
    integration_stack,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real login produces a Streamlit session and profile."""

    client, _ = integration_stack

    registered = register_test_user(client)

    ui = start_streamlit_ui(
        monkeypatch,
        client,
    )

    ui.text_input(
        key="toeic_login_email"
    ).set_value(TEST_EMAIL)

    ui.text_input(
        key="toeic_login_password"
    ).set_value(TEST_PASSWORD)

    ui.button(
        key="toeic_login_submit"
    ).click().run()

    ui.run()

    assert len(ui.exception) == 0

    token = ui.session_state[TOKEN_KEY]

    assert isinstance(token, str)
    assert token

    # JWT from Streamlit is accepted by real FastAPI.
    profile = client.get_me(token)

    assert profile.id == registered.id
    assert profile.email == TEST_EMAIL

    # Test the logout button.
    ui.button(
        key="toeic_logout"
    ).click().run()

    assert len(ui.exception) == 0

    # The anonymous form must appear again.
    assert ui.text_input(
        key="toeic_login_email"
    ) is not None


def test_streamlit_wrong_password_does_not_login(
    integration_stack,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real FastAPI 401 cannot create a Streamlit session."""

    client, _ = integration_stack

    register_test_user(client)

    ui = start_streamlit_ui(
        monkeypatch,
        client,
    )

    ui.text_input(
        key="toeic_login_email"
    ).set_value(TEST_EMAIL)

    ui.text_input(
        key="toeic_login_password"
    ).set_value("WrongPassword@2026")

    ui.button(
        key="toeic_login_submit"
    ).click().run()

    assert len(ui.exception) == 0

    assert any(
        "Email hoặc mật khẩu" in element.value
        for element in ui.error
    )

    assert ui.text_input(
        key="toeic_login_email"
    ) is not None


def test_streamlit_rejects_disabled_account_session(
    integration_stack,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Streamlit returns to login when /auth/me returns 401."""

    client, engine = integration_stack

    registered = register_test_user(client)

    login = client.login(
        TEST_EMAIL,
        TEST_PASSWORD,
    )

    ui = start_streamlit_ui(
        monkeypatch,
        client,
    )

    ui.session_state[TOKEN_KEY] = (
        login.access_token
    )

    ui.session_state[EXPIRES_AT_KEY] = (
        time.time() + 1800
    )

    # Change user status in temporary SQLite.
    disable_db_user(
        engine,
        registered.id,
    )

    ui.run()

    assert len(ui.exception) == 0

    assert any(
        "Phiên đăng nhập không còn hợp lệ"
        in element.value
        for element in ui.warning
    )

    assert ui.text_input(
        key="toeic_login_email"
    ) is not None
