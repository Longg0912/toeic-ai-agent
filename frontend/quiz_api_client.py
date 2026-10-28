
"""HTTP client for TOEIC quiz session APIs."""

import os
from typing import Any

import httpx


DEFAULT_API_BASE_URL = "http://127.0.0.1:8765"


class QuizAPIError(RuntimeError):
    """A safe, user-facing error raised by the quiz API client."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code


class QuizAPIClient:
    """Synchronous client for creating, submitting and reviewing quizzes."""

    def __init__(
        self,
        base_url: str | None = None,
        access_token: str = "",
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        resolved_base_url = (
            base_url
            or os.getenv("TOEIC_API_BASE_URL")
            or DEFAULT_API_BASE_URL
        ).strip().rstrip("/")

        token = access_token.strip()

        if not resolved_base_url:
            raise ValueError("API base URL không được để trống.")

        if not token:
            raise ValueError("access_token không được để trống.")

        self._client = httpx.Client(
            base_url=resolved_base_url,
            timeout=timeout,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            },
            transport=transport,
        )

    def close(self) -> None:
        """Close the underlying HTTPX client."""
        self._client.close()

    def __enter__(self) -> "QuizAPIClient":
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> None:
        self.close()

    @staticmethod
    def _validate_session_id(session_id: int) -> None:
        if isinstance(session_id, bool) or session_id <= 0:
            raise ValueError("session_id phải là số nguyên dương.")

    @staticmethod
    def _build_error(response: httpx.Response) -> QuizAPIError:
        """Translate known HTTP errors into Vietnamese messages."""
        status_code = response.status_code

        try:
            body = response.json()
        except ValueError:
            body = {}

        detail = body.get("detail") if isinstance(body, dict) else None

        if status_code == 401:
            message = (
                "Phiên đăng nhập không hợp lệ hoặc đã hết hạn. "
                "Vui lòng đăng nhập lại."
            )

        elif status_code == 403:
            message = "Bạn không có quyền thực hiện thao tác này."

        elif status_code == 404:
            message = "Không tìm thấy bài luyện TOEIC này."

        elif status_code == 409:
            if isinstance(detail, dict):
                requested = detail.get("requested")
                available = detail.get("available")

                if (
                    isinstance(requested, int)
                    and isinstance(available, int)
                ):
                    message = (
                        f"Hiện chỉ có {available} câu hỏi phù hợp, "
                        f"nhưng bạn yêu cầu {requested} câu. "
                        "Hãy giảm số câu hoặc chọn kỹ năng khác."
                    )
                else:
                    message = (
                        "Bài luyện đã được nộp hoặc không còn "
                        "ở trạng thái có thể thực hiện thao tác này."
                    )
            else:
                message = (
                    "Bài luyện đã được nộp hoặc không còn "
                    "ở trạng thái có thể thực hiện thao tác này."
                )

        elif status_code == 422:
            message = (
                "Dữ liệu gửi lên không hợp lệ. "
                "Vui lòng kiểm tra câu trả lời và thử lại."
            )

        elif status_code >= 500:
            message = (
                "Backend đang gặp lỗi. "
                "Vui lòng thử lại sau."
            )

        else:
            message = (
                f"Không thể thực hiện yêu cầu "
                f"(HTTP {status_code})."
            )

        return QuizAPIError(message, status_code=status_code)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, int] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send an authenticated request and return a JSON object."""
        try:
            response = self._client.request(
                method=method,
                url=path,
                params=params,
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise QuizAPIError(
                "Backend phản hồi quá chậm. Vui lòng thử lại."
            ) from exc
        except httpx.RequestError as exc:
            raise QuizAPIError(
                "Không thể kết nối tới backend. "
                "Hãy kiểm tra xem FastAPI đã chạy chưa."
            ) from exc

        if not response.is_success:
            raise self._build_error(response)

        try:
            data = response.json()
        except ValueError as exc:
            raise QuizAPIError(
                "Backend trả về dữ liệu không hợp lệ.",
                status_code=response.status_code,
            ) from exc

        if not isinstance(data, dict):
            raise QuizAPIError(
                "Định dạng dữ liệu từ backend không hợp lệ.",
                status_code=response.status_code,
            )

        return data

    def create_session(
        self,
        question_count: int = 10,
        skill_code: str | None = None,
    ) -> dict[str, Any]:
        """Create a TOEIC Part 5 practice session."""
        if (
            isinstance(question_count, bool)
            or not isinstance(question_count, int)
            or not 1 <= question_count <= 50
        ):
            raise ValueError("question_count phải nằm trong khoảng 1–50.")

        payload: dict[str, Any] = {
            "question_count": question_count,
        }

        if skill_code is not None:
            normalized_skill_code = skill_code.strip()

            if not normalized_skill_code:
                raise ValueError("skill_code không được để trống.")

            payload["skill_code"] = normalized_skill_code

        return self._request(
            "POST",
            "/quiz-sessions",
            payload=payload,
        )

    def submit_session(
        self,
        session_id: int,
        answers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Submit answers and receive the graded result."""
        self._validate_session_id(session_id)

        if not answers:
            raise ValueError("Danh sách câu trả lời không được để trống.")

        return self._request(
            "POST",
            f"/quiz-sessions/{session_id}/submit",
            payload={"answers": answers},
        )

    def list_sessions(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return the authenticated user's paginated quiz history."""
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError("limit phải nằm trong khoảng 1–100.")

        if (
            isinstance(offset, bool)
            or not isinstance(offset, int)
            or offset < 0
        ):
            raise ValueError("offset phải là số nguyên không âm.")

        return self._request(
            "GET",
            "/quiz-sessions",
            params={
                "limit": limit,
                "offset": offset,
            },
        )

    def get_session(
        self,
        session_id: int,
    ) -> dict[str, Any]:
        """Return one quiz session, including its review data."""
        self._validate_session_id(session_id)

        return self._request(
            "GET",
            f"/quiz-sessions/{session_id}",
        )
