
"""HTTP client utilities for communicating with the FastAPI backend."""

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class HealthResult:
    """Result of checking the backend health endpoint."""

    healthy: bool
    message: str


def check_backend_health(base_url: str) -> HealthResult:
    """Check whether the FastAPI backend responds correctly.

    Args:
        base_url: Backend URL, for example http://127.0.0.1:8765.

    Returns:
        HealthResult describing success or failure.
    """

    url = f"{base_url.rstrip('/')}/health"

    try:
        response = httpx.get(
            url,
            timeout=3.0,
        )

        response.raise_for_status()

    except httpx.HTTPStatusError as exc:
        return HealthResult(
            healthy=False,
            message=(
                "Backend trả về mã HTTP "
                f"{exc.response.status_code}."
            ),
        )

    except (httpx.RequestError, httpx.InvalidURL):
        return HealthResult(
            healthy=False,
            message=(
                "Không thể kết nối đến FastAPI. "
                "Hãy kiểm tra server và địa chỉ API."
            ),
        )

    try:
        data = response.json()

    except ValueError:
        return HealthResult(
            healthy=False,
            message="Backend không trả về JSON hợp lệ.",
        )

    if not isinstance(data, dict) or data.get("status") != "ok":
        return HealthResult(
            healthy=False,
            message="Backend trả về trạng thái không hợp lệ.",
        )

    return HealthResult(
        healthy=True,
        message="Kết nối FastAPI thành công!",
    )
