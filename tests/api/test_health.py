
"""Tests for the FastAPI health endpoint."""

from fastapi.testclient import TestClient

from backend.app.main import app


def test_health_returns_ok() -> None:
    """The health endpoint must return HTTP 200 and valid JSON."""

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["content-type"].startswith(
        "application/json"
    )


def test_health_is_documented_in_openapi() -> None:
    """The health endpoint must appear in OpenAPI documentation."""

    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200

    schema = response.json()

    assert "/health" in schema["paths"]
    assert "get" in schema["paths"]["/health"]
