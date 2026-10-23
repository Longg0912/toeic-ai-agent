
"""Tests for the Streamlit authentication HTTP client.

Uses httpx.MockTransport:
- No network access.
- No real FastAPI server.
- No SQLite changes.
- No real passwords or JWTs.
"""

import json

import httpx
import pytest

from frontend.auth_api_client import (
    AuthAPIClient,
    AuthAPIError,
    LoginResult,
    PublicUser,
)


EMAIL = "student@example.com"
PASSWORD = "ExamplePassword@2026"
TEST_TOKEN = "test.jwt.access-token"


def public_user_payload() -> dict:
    """Build a typical UserPublic response."""

    return {
        "id": 15,
        "email": EMAIL,
        "role": "student",
        "is_active": True,
    }


def mock_client(handler) -> AuthAPIClient:
    """Create a client with no external network access."""

    return AuthAPIClient(
        transport=httpx.MockTransport(handler),
    )


def test_register_success_returns_public_user() -> None:
    """POST /auth/register sends the correct request."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/auth/register"
        assert "authorization" not in request.headers

        payload = json.loads(request.content)

        assert payload == {
            "email": EMAIL,
            "password": PASSWORD,
        }

        return httpx.Response(
            201,
            json=public_user_payload(),
        )

    client = mock_client(handler)

    result = client.register(EMAIL, PASSWORD)

    assert isinstance(result, PublicUser)
    assert result.id == 15
    assert result.email == EMAIL
    assert result.role == "student"
    assert result.is_active is True


def test_register_duplicate_email_maps_409() -> None:
    """Duplicate email produces a safe error."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "detail": "Email is already registered.",
            },
        )

    client = mock_client(handler)

    with pytest.raises(AuthAPIError) as error:
        client.register(EMAIL, PASSWORD)

    assert error.value.status_code == 409
    assert "đã được đăng ký" in str(error.value)
    assert PASSWORD not in str(error.value)


def test_login_success_returns_token() -> None:
    """POST /auth/login returns a validated login result."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/auth/login"
        assert "authorization" not in request.headers

        payload = json.loads(request.content)

        assert payload == {
            "email": EMAIL,
            "password": PASSWORD,
        }

        return httpx.Response(
            200,
            json={
                "access_token": TEST_TOKEN,
                "token_type": "bearer",
                "expires_in": 1800,
            },
        )

    client = mock_client(handler)

    result = client.login(EMAIL, PASSWORD)

    assert isinstance(result, LoginResult)
    assert result.access_token == TEST_TOKEN
    assert result.token_type == "bearer"
    assert result.expires_in == 1800

    # Prevent accidental token exposure via repr().
    assert TEST_TOKEN not in repr(result)


def test_login_invalid_credentials_maps_401() -> None:
    """Incorrect login credentials do not leak details."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={
                "detail": "Invalid email or password.",
            },
        )

    client = mock_client(handler)

    with pytest.raises(AuthAPIError) as error:
        client.login(EMAIL, PASSWORD)

    assert error.value.status_code == 401
    assert "Email hoặc mật khẩu" in str(error.value)
    assert PASSWORD not in str(error.value)


def test_get_me_sends_bearer_token() -> None:
    """GET /auth/me sends the JWT in Authorization."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/auth/me"

        assert request.headers["Authorization"] == (
            f"Bearer {TEST_TOKEN}"
        )

        return httpx.Response(
            200,
            json=public_user_payload(),
        )

    client = mock_client(handler)

    result = client.get_me(TEST_TOKEN)

    assert result.id == 15
    assert result.email == EMAIL


def test_get_me_rejects_empty_token_locally() -> None:
    """Do not send a request without a JWT."""

    requests_received = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_received.append(request)
        return httpx.Response(200, json=public_user_payload())

    client = mock_client(handler)

    with pytest.raises(AuthAPIError) as error:
        client.get_me("   ")

    assert error.value.status_code == 401
    assert requests_received == []


def test_get_me_unauthorized_maps_401() -> None:
    """Expired or invalid sessions get a safe error."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={
                "detail": "Could not validate credentials.",
            },
        )

    client = mock_client(handler)

    with pytest.raises(AuthAPIError) as error:
        client.get_me(TEST_TOKEN)

    assert error.value.status_code == 401
    assert "Phiên đăng nhập" in str(error.value)
    assert TEST_TOKEN not in str(error.value)


def test_validation_error_422_is_sanitized() -> None:
    """Do not display raw server validation data."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "detail": f"Invalid password: {PASSWORD}",
            },
        )

    client = mock_client(handler)

    with pytest.raises(AuthAPIError) as error:
        client.register("bad-email", PASSWORD)

    assert error.value.status_code == 422
    assert "Dữ liệu không hợp lệ" in str(error.value)
    assert PASSWORD not in str(error.value)


def test_timeout_is_sanitized() -> None:
    """Timeout errors must not echo sensitive details."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(
            f"Timeout while sending {PASSWORD}",
            request=request,
        )

    client = mock_client(handler)

    with pytest.raises(AuthAPIError) as error:
        client.login(EMAIL, PASSWORD)

    assert error.value.status_code is None
    assert "hết thời gian chờ" in str(error.value)
    assert PASSWORD not in str(error.value)


def test_connection_error_is_sanitized() -> None:
    """Connection errors must not expose request details."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            f"Connection failed for {EMAIL}",
            request=request,
        )

    client = mock_client(handler)

    with pytest.raises(AuthAPIError) as error:
        client.login(EMAIL, PASSWORD)

    assert "Không thể kết nối" in str(error.value)
    assert EMAIL not in str(error.value)
    assert PASSWORD not in str(error.value)


def test_server_error_is_sanitized() -> None:
    """HTTP 5xx errors use a generic safe message."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            text=f"Internal error involving {PASSWORD}",
        )

    client = mock_client(handler)

    with pytest.raises(AuthAPIError) as error:
        client.login(EMAIL, PASSWORD)

    assert error.value.status_code == 503
    assert "Backend đang gặp lỗi" in str(error.value)
    assert PASSWORD not in str(error.value)


def test_invalid_json_response_is_rejected() -> None:
    """A successful HTTP status still requires valid JSON."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"not valid json",
        )

    client = mock_client(handler)

    with pytest.raises(AuthAPIError) as error:
        client.get_me(TEST_TOKEN)

    assert "JSON không hợp lệ" in str(error.value)


def test_missing_user_fields_are_rejected() -> None:
    """An incomplete public user response cannot be used."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": 15,
                "email": EMAIL,
                # role and is_active are missing
            },
        )

    client = mock_client(handler)

    with pytest.raises(AuthAPIError) as error:
        client.get_me(TEST_TOKEN)

    assert "không hợp lệ" in str(error.value)


def test_invalid_login_response_is_rejected() -> None:
    """A login result must contain a valid Bearer token."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "",
                "token_type": "bearer",
                "expires_in": 1800,
            },
        )

    client = mock_client(handler)

    with pytest.raises(AuthAPIError) as error:
        client.login(EMAIL, PASSWORD)

    assert "không hợp lệ" in str(error.value)


def test_redirect_is_not_followed() -> None:
    """Credentials must not follow unexpected redirects."""

    received = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request.url)

        return httpx.Response(
            302,
            headers={
                "Location": "https://example.com/redirect",
            },
        )

    client = mock_client(handler)

    with pytest.raises(AuthAPIError) as error:
        client.login(EMAIL, PASSWORD)

    assert error.value.status_code == 302
    assert len(received) == 1


def test_remote_http_is_rejected() -> None:
    """Nonlocal API hosts must use HTTPS."""

    with pytest.raises(ValueError, match="HTTPS"):
        AuthAPIClient(
            base_url="http://api.example.com",
        )


def test_environment_base_url_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An environment variable can configure remote HTTPS."""

    monkeypatch.setenv(
        "TOEIC_API_BASE_URL",
        "https://api.example.com/",
    )

    client = AuthAPIClient()

    assert client.base_url == "https://api.example.com"


def test_extra_server_fields_are_not_exposed() -> None:
    """Only public account fields enter PublicUser."""

    def handler(request: httpx.Request) -> httpx.Response:
        payload = public_user_payload()

        payload["password_hash"] = "unexpected-secret-hash"
        payload["internal_note"] = "private"

        return httpx.Response(
            200,
            json=payload,
        )

    client = mock_client(handler)

    result = client.get_me(TEST_TOKEN)

    assert isinstance(result, PublicUser)
    assert not hasattr(result, "password_hash")
    assert not hasattr(result, "internal_note")
    assert "unexpected-secret-hash" not in repr(result)
