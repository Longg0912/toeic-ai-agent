
"""Tests for the Streamlit frontend API client."""

import httpx
import pytest

from frontend.api_client import check_backend_health


BASE_URL = "http://127.0.0.1:8765"


def mock_response(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    *,
    json_data: dict | None = None,
    content: bytes | None = None,
) -> None:
    """Replace httpx.get with a controlled response."""

    request = httpx.Request(
        "GET",
        f"{BASE_URL}/health",
    )

    if content is not None:
        response = httpx.Response(
            status_code,
            content=content,
            request=request,
        )
    else:
        response = httpx.Response(
            status_code,
            json=json_data,
            request=request,
        )

    def fake_get(
        url: str,
        *,
        timeout: float,
    ) -> httpx.Response:
        assert url == f"{BASE_URL}/health"
        assert timeout == 3.0
        return response

    monkeypatch.setattr(httpx, "get", fake_get)


def test_health_connection_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid health response indicates success."""

    mock_response(
        monkeypatch,
        200,
        json_data={"status": "ok"},
    )

    result = check_backend_health(BASE_URL)

    assert result.healthy is True
    assert result.message == "Kết nối FastAPI thành công!"


def test_health_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP error responses must be handled."""

    mock_response(
        monkeypatch,
        503,
        json_data={"detail": "Unavailable"},
    )

    result = check_backend_health(BASE_URL)

    assert result.healthy is False
    assert "503" in result.message


def test_health_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Connection errors must not crash the frontend."""

    def fake_get(
        url: str,
        *,
        timeout: float,
    ) -> httpx.Response:
        raise httpx.ConnectError(
            "Connection refused",
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    result = check_backend_health(BASE_URL)

    assert result.healthy is False
    assert "Không thể kết nối" in result.message


def test_health_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid JSON must be handled safely."""

    mock_response(
        monkeypatch,
        200,
        content=b"not valid json",
    )

    result = check_backend_health(BASE_URL)

    assert result.healthy is False
    assert "JSON" in result.message


def test_health_unexpected_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected JSON data must not indicate success."""

    mock_response(
        monkeypatch,
        200,
        json_data={"status": "error"},
    )

    result = check_backend_health(BASE_URL)

    assert result.healthy is False
