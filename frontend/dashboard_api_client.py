
"""HTTP client for the authenticated student dashboard API."""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any

import httpx


DEFAULT_API_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_TIMEOUT_SECONDS = 10.0


class DashboardAPIError(RuntimeError):
    """Safe, user-facing error raised by the Dashboard API client."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code


class DashboardAPIClient:
    """Synchronous authenticated client for Dashboard endpoints."""

    def __init__(
        self,
        base_url: str | None = None,
        access_token: str = "",
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        resolved_base_url = (
            base_url
            if base_url is not None
            else os.getenv(
                "TOEIC_API_BASE_URL",
                DEFAULT_API_BASE_URL,
            )
        )

        if not isinstance(resolved_base_url, str):
            raise ValueError("API base URL phải là chuỗi.")

        resolved_base_url = resolved_base_url.strip().rstrip("/")
        token = access_token.strip()

        if not resolved_base_url:
            raise ValueError("API base URL không được để trống.")

        if not token:
            raise ValueError("access_token không được để trống.")

        if timeout <= 0:
            raise ValueError("HTTP timeout phải lớn hơn 0.")

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

    def __enter__(self) -> "DashboardAPIClient":
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> None:
        self.close()

    # =================================================
    # Validation helpers
    # =================================================

    @staticmethod
    def _require_non_negative_int(
        value: Any,
        field_name: str,
    ) -> None:
        if type(value) is not int or value < 0:
            raise DashboardAPIError(
                f"Dữ liệu Dashboard không hợp lệ: {field_name}."
            )

    @staticmethod
    def _require_percentage(
        value: Any,
        field_name: str,
    ) -> None:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not 0 <= value <= 100
        ):
            raise DashboardAPIError(
                f"Dữ liệu Dashboard không hợp lệ: {field_name}."
            )

    @staticmethod
    def _require_object(
        data: Any,
        context: str,
    ) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise DashboardAPIError(
                f"Backend trả về dữ liệu {context} không hợp lệ."
            )

        return data

    @staticmethod
    def _require_list(
        data: Any,
        context: str,
    ) -> list[Any]:
        if not isinstance(data, list):
            raise DashboardAPIError(
                f"Backend trả về danh sách {context} không hợp lệ."
            )

        return data

    # =================================================
    # Error handling
    # =================================================

    @staticmethod
    def _build_error(
        response: httpx.Response,
    ) -> DashboardAPIError:
        status_code = response.status_code

        if status_code == 401:
            message = (
                "Phiên đăng nhập không hợp lệ hoặc đã hết hạn. "
                "Vui lòng đăng nhập lại."
            )

        elif status_code == 403:
            message = (
                "Tài khoản hiện tại không có quyền "
                "truy cập Dashboard sinh viên."
            )

        elif status_code == 404:
            message = (
                "Không tìm thấy dữ liệu tài khoản sinh viên."
            )

        elif status_code == 422:
            message = (
                "Khoảng thời gian hoặc dữ liệu yêu cầu "
                "không hợp lệ."
            )

        elif status_code >= 500:
            message = (
                "Backend đang gặp lỗi khi tải Dashboard. "
                "Vui lòng thử lại sau."
            )

        else:
            message = (
                f"Không thể tải Dashboard (HTTP {status_code})."
            )

        return DashboardAPIError(
            message,
            status_code=status_code,
        )

    def _request_json(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send an authenticated request and return a JSON object."""

        try:
            response = self._client.request(
                method=method,
                url=endpoint,
                params=params,
            )

        except httpx.TimeoutException:
            raise DashboardAPIError(
                "Backend phản hồi quá chậm. "
                "Vui lòng thử lại sau."
            ) from None

        except httpx.RequestError:
            raise DashboardAPIError(
                "Không thể kết nối tới Backend. "
                "Hãy kiểm tra xem FastAPI đã chạy chưa."
            ) from None

        if not response.is_success:
            raise self._build_error(response)

        try:
            data = response.json()
        except ValueError:
            raise DashboardAPIError(
                "Backend không trả về JSON hợp lệ.",
                status_code=response.status_code,
            ) from None

        return self._require_object(
            data,
            "Dashboard",
        )

    # =================================================
    # Dashboard endpoints
    # =================================================

    def get_overview(self) -> dict[str, Any]:
        """Get high-level learning statistics."""

        data = self._request_json(
            "GET",
            "/dashboard/overview",
        )

        for field in (
            "submitted_quiz_sessions",
            "answered_questions",
            "correct_answers",
            "active_days",
        ):
            self._require_non_negative_int(
                data.get(field),
                field,
            )

        self._require_percentage(
            data.get("accuracy_percent"),
            "accuracy_percent",
        )

        target_score = data.get("target_score")

        if target_score is not None:
            if (
                type(target_score) is not int
                or not 0 <= target_score <= 990
            ):
                raise DashboardAPIError(
                    "Điểm TOEIC mục tiêu không hợp lệ."
                )

        active_plan = data.get("active_plan")

        if active_plan is not None:
            self._require_object(
                active_plan,
                "active_plan",
            )

        return data

    def get_performance(self) -> dict[str, Any]:
        """Get aggregated quiz performance."""

        data = self._request_json(
            "GET",
            "/dashboard/performance",
        )

        for field in (
            "submitted_sessions",
            "answered_questions",
            "correct_answers",
            "incorrect_answers",
            "total_time_spent_seconds",
        ):
            self._require_non_negative_int(
                data.get(field),
                field,
            )

        self._require_percentage(
            data.get("accuracy_percent"),
            "accuracy_percent",
        )

        return data

    def get_skills(self) -> dict[str, Any]:
        """Get performance statistics grouped by skill."""

        data = self._request_json(
            "GET",
            "/dashboard/skills",
        )

        items = self._require_list(
            data.get("items"),
            "skills",
        )

        self._require_non_negative_int(
            data.get("total"),
            "total",
        )

        if data["total"] != len(items):
            raise DashboardAPIError(
                "Tổng số kỹ năng không khớp với dữ liệu trả về."
            )

        for item in items:
            skill = self._require_object(
                item,
                "skill",
            )

            for field in (
                "skill_id",
                "attempt_count",
                "correct_count",
                "incorrect_count",
            ):
                self._require_non_negative_int(
                    skill.get(field),
                    field,
                )

            for field in ("code", "name", "category"):
                if (
                    not isinstance(skill.get(field), str)
                    or not skill[field].strip()
                ):
                    raise DashboardAPIError(
                        f"Thông tin kỹ năng thiếu trường {field}."
                    )

            self._require_percentage(
                skill.get("accuracy_percent"),
                "accuracy_percent",
            )

            if type(skill.get("is_weak")) is not bool:
                raise DashboardAPIError(
                    "Trạng thái kỹ năng yếu không hợp lệ."
                )

        return data

    def get_activity(
        self,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        """Get daily activity for an inclusive date range."""

        if (
            not isinstance(start_date, date)
            or isinstance(start_date, datetime)
            or not isinstance(end_date, date)
            or isinstance(end_date, datetime)
        ):
            raise ValueError(
                "start_date và end_date phải là datetime.date."
            )

        if start_date > end_date:
            raise ValueError(
                "start_date không được sau end_date."
            )

        data = self._request_json(
            "GET",
            "/dashboard/activity",
            params={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        )

        for field in (
            "total_active_days",
            "total_submitted_sessions",
            "total_answered_questions",
        ):
            self._require_non_negative_int(
                data.get(field),
                field,
            )

        days = self._require_list(
            data.get("days"),
            "activity",
        )

        for item in days:
            day = self._require_object(
                item,
                "activity day",
            )

            if not isinstance(day.get("activity_date"), str):
                raise DashboardAPIError(
                    "Ngày hoạt động không hợp lệ."
                )

            for field in (
                "submitted_sessions",
                "answered_questions",
                "correct_answers",
            ):
                self._require_non_negative_int(
                    day.get(field),
                    field,
                )

            self._require_percentage(
                day.get("accuracy_percent"),
                "accuracy_percent",
            )

        return data

    def get_study_plan(self) -> dict[str, Any]:
        """Get active study plan progress and upcoming tasks."""

        data = self._request_json(
            "GET",
            "/dashboard/study-plan",
        )

        for field in (
            "total_tasks",
            "completed_tasks",
            "pending_tasks",
            "skipped_tasks",
        ):
            self._require_non_negative_int(
                data.get(field),
                field,
            )

        self._require_percentage(
            data.get("completion_percent"),
            "completion_percent",
        )

        plan = data.get("plan")

        if plan is not None:
            self._require_object(
                plan,
                "study plan",
            )

        upcoming_tasks = self._require_list(
            data.get("upcoming_tasks"),
            "upcoming tasks",
        )

        for task in upcoming_tasks:
            self._require_object(
                task,
                "upcoming task",
            )

        return data
