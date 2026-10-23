
"""HTTP client for the TOEIC Tutor authentication APIs.

Supported operations:
- POST /auth/register
- POST /auth/login
- GET  /auth/me

This module contains no Streamlit UI and does not
store passwords, JWT signing keys, or login sessions.
"""

from __future__ import annotations

import os

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import httpx


DEFAULT_API_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_TIMEOUT_SECONDS = 10.0


class AuthAPIError(Exception):
    """Safe, user-facing API error.

    Raw responses and request credentials are not
    included in this exception.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class PublicUser:
    """Public account information returned by FastAPI."""

    id: int
    email: str
    role: str
    is_active: bool


@dataclass(frozen=True)
class LoginResult:
    """Successful login response.

    The access token is intentionally hidden from repr().
    """

    access_token: str = field(repr=False)
    token_type: str
    expires_in: int


def _parse_public_user(data: dict[str, Any]) -> PublicUser:
    """Validate the expected public user response."""

    user_id = data.get("id")
    email = data.get("email")
    role = data.get("role")
    is_active = data.get("is_active")

    if (
        type(user_id) is not int
        or user_id <= 0
        or not isinstance(email, str)
        or not email
        or role not in ("student", "admin")
        or type(is_active) is not bool
    ):
        raise AuthAPIError(
            "Phản hồi thông tin tài khoản từ Backend không hợp lệ."
        )

    # Explicitly select public fields.
    # Extra fields received from Backend are not propagated.
    return PublicUser(
        id=user_id,
        email=email,
        role=role,
        is_active=is_active,
    )


def _parse_login_result(data: dict[str, Any]) -> LoginResult:
    """Validate the expected JWT login response."""

    token = data.get("access_token")
    token_type = data.get("token_type")
    expires_in = data.get("expires_in")

    if (
        not isinstance(token, str)
        or not token
        or token_type != "bearer"
        or type(expires_in) is not int
        or expires_in <= 0
    ):
        raise AuthAPIError(
            "Phản hồi đăng nhập từ Backend không hợp lệ."
        )

    return LoginResult(
        access_token=token,
        token_type=token_type,
        expires_in=expires_in,
    )


class AuthAPIClient:
    """Synchronous HTTP client for the authentication API."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        configured_url = (
            base_url
            if base_url is not None
            else os.getenv(
                "TOEIC_API_BASE_URL",
                DEFAULT_API_BASE_URL,
            )
        )

        if not isinstance(configured_url, str):
            raise ValueError("Invalid Backend API URL.")

        configured_url = configured_url.strip().rstrip("/")

        try:
            parsed = urlsplit(configured_url)
            host = parsed.hostname
            # Accessing port also validates malformed port syntax.
            parsed.port
        except ValueError:
            raise ValueError(
                "Invalid Backend API URL."
            ) from None

        if (
            parsed.scheme not in ("http", "https")
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "Backend API URL must be an HTTP(S) origin."
            )

        local_hosts = {
            "localhost",
            "127.0.0.1",
            "::1",
        }

        if (
            parsed.scheme == "http"
            and host not in local_hosts
        ):
            raise ValueError(
                "HTTPS is required for nonlocal Backend APIs."
            )

        if timeout <= 0:
            raise ValueError(
                "HTTP timeout must be positive."
            )

        self.base_url = configured_url
        self.timeout = timeout

        # Optional dependency injection for httpx.MockTransport.
        self._transport = transport

    @staticmethod
    def _http_error_message(
        status_code: int,
        endpoint: str,
    ) -> str:
        """Map backend status codes to safe UI messages."""

        if status_code == 401:
            if endpoint == "/auth/login":
                return (
                    "Email hoặc mật khẩu không đúng."
                )

            return (
                "Phiên đăng nhập không hợp lệ "
                "hoặc đã hết hạn."
            )

        if status_code == 403:
            return "Bạn không có quyền thực hiện thao tác này."

        if status_code == 409:
            return "Email này đã được đăng ký."

        if status_code == 422:
            return (
                "Dữ liệu không hợp lệ. "
                "Vui lòng kiểm tra thông tin đã nhập."
            )

        if status_code == 429:
            return (
                "Có quá nhiều yêu cầu. "
                "Vui lòng thử lại sau."
            )

        if 500 <= status_code <= 599:
            return (
                "Backend đang gặp lỗi. "
                "Vui lòng thử lại sau."
            )

        return (
            "Yêu cầu tới Backend không thành công "
            f"(HTTP {status_code})."
        )

    def _request_json(
        self,
        method: str,
        endpoint: str,
        *,
        expected_status: int,
        payload: dict[str, str] | None = None,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        """Send one HTTP request and parse a JSON object.

        Raises AuthAPIError instead of exposing raw
        HTTP responses, exceptions, or credentials.
        """

        headers = {
            "Accept": "application/json",
        }

        if access_token is not None:
            if (
                not isinstance(access_token, str)
                or not access_token.strip()
            ):
                raise AuthAPIError(
                    "Bạn cần đăng nhập để tiếp tục.",
                    status_code=401,
                )

            headers["Authorization"] = (
                f"Bearer {access_token}"
            )

        try:
            with httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                transport=self._transport,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = client.request(
                    method,
                    endpoint,
                    json=payload,
                    headers=headers,
                )

        except httpx.TimeoutException:
            raise AuthAPIError(
                "Kết nối tới Backend đã hết thời gian chờ."
            ) from None

        except httpx.RequestError:
            raise AuthAPIError(
                "Không thể kết nối tới Backend. "
                "Vui lòng kiểm tra FastAPI đang chạy."
            ) from None

        if response.status_code != expected_status:
            raise AuthAPIError(
                self._http_error_message(
                    response.status_code,
                    endpoint,
                ),
                status_code=response.status_code,
            )

        try:
            data = response.json()
        except (ValueError, UnicodeDecodeError):
            raise AuthAPIError(
                "Backend trả về dữ liệu JSON không hợp lệ.",
                status_code=response.status_code,
            ) from None

        if not isinstance(data, dict):
            raise AuthAPIError(
                "Backend trả về cấu trúc dữ liệu không hợp lệ.",
                status_code=response.status_code,
            )

        return data

    def register(
        self,
        email: str,
        password: str,
    ) -> PublicUser:
        """Register a student account through FastAPI."""

        data = self._request_json(
            "POST",
            "/auth/register",
            expected_status=201,
            payload={
                "email": email,
                "password": password,
            },
        )

        return _parse_public_user(data)

    def login(
        self,
        email: str,
        password: str,
    ) -> LoginResult:
        """Authenticate and receive a signed JWT."""

        data = self._request_json(
            "POST",
            "/auth/login",
            expected_status=200,
            payload={
                "email": email,
                "password": password,
            },
        )

        return _parse_login_result(data)

    def get_me(
        self,
        access_token: str,
    ) -> PublicUser:
        """Load the current account using a Bearer JWT."""

        if (
            not isinstance(access_token, str)
            or not access_token.strip()
        ):
            raise AuthAPIError(
                "Bạn cần đăng nhập để tiếp tục.",
                status_code=401,
            )

        data = self._request_json(
            "GET",
            "/auth/me",
            expected_status=200,
            access_token=access_token,
        )

        return _parse_public_user(data)
