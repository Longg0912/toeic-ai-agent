
"""HTTP client for TOEIC study plan APIs."""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any

import httpx


DEFAULT_API_BASE_URL = "http://127.0.0.1:8765"


class StudyPlanAPIError(RuntimeError):
    """Safe, user-facing error raised by the study plan API client."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code


class StudyPlanAPIClient:
    """Synchronous HTTP client for study plan endpoints."""

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

        if timeout <= 0:
            raise ValueError("timeout phải lớn hơn 0.")

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

    def __enter__(self) -> "StudyPlanAPIClient":
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> None:
        self.close()

    @staticmethod
    def _validate_plan_id(plan_id: int) -> None:
        if (
            isinstance(plan_id, bool)
            or not isinstance(plan_id, int)
            or plan_id <= 0
        ):
            raise ValueError("plan_id phải là số nguyên dương.")

    @staticmethod
    def _validate_pagination(
        limit: int,
        offset: int,
    ) -> None:
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

    @staticmethod
    def _validate_date(
        value: date,
        field_name: str,
    ) -> None:
        if not isinstance(value, date) or isinstance(value, datetime):
            raise ValueError(
                f"{field_name} phải là datetime.date."
            )

    @staticmethod
    def _validate_plan_response(
        data: dict[str, Any],
    ) -> None:
        """Validate the public study plan response structure."""

        required_fields = {
            "id",
            "title",
            "target_score",
            "start_date",
            "end_date",
            "daily_minutes",
            "status",
            "created_at",
            "updated_at",
        }

        if not required_fields.issubset(data):
            raise StudyPlanAPIError(
                "Backend trả về thông tin kế hoạch học tập không đầy đủ."
            )

        if (
            type(data["id"]) is not int
            or data["id"] <= 0
            or not isinstance(data["title"], str)
            or type(data["target_score"]) is not int
            or not 0 <= data["target_score"] <= 990
            or not isinstance(data["start_date"], str)
            or not isinstance(data["end_date"], str)
            or type(data["daily_minutes"]) is not int
            or data["daily_minutes"] <= 0
            or data["status"] not in {
                "active",
                "paused",
                "completed",
                "cancelled",
            }
            or not isinstance(data["created_at"], str)
            or not isinstance(data["updated_at"], str)
        ):
            raise StudyPlanAPIError(
                "Backend trả về dữ liệu kế hoạch học tập không hợp lệ."
            )

    @classmethod
    def _validate_task_response(
        cls,
        task: Any,
    ) -> None:
        """Validate one public study plan task."""

        required_fields = {
            "id",
            "skill_id",
            "skill",
            "task_type",
            "scheduled_date",
            "estimated_minutes",
            "target_question_count",
            "status",
            "completed_at",
        }

        if not isinstance(task, dict) or not required_fields.issubset(task):
            raise StudyPlanAPIError(
                "Backend trả về dữ liệu nhiệm vụ học tập không hợp lệ."
            )

        if (
            type(task["id"]) is not int
            or task["id"] <= 0
            or (
                task["skill_id"] is not None
                and (
                    type(task["skill_id"]) is not int
                    or task["skill_id"] <= 0
                )
            )
            or task["task_type"] not in {
                "practice",
                "review",
                "quiz",
            }
            or not isinstance(task["scheduled_date"], str)
            or type(task["estimated_minutes"]) is not int
            or task["estimated_minutes"] <= 0
            or type(task["target_question_count"]) is not int
            or task["target_question_count"] <= 0
            or task["status"] not in {
                "pending",
                "completed",
                "skipped",
            }
            or (
                task["completed_at"] is not None
                and not isinstance(task["completed_at"], str)
            )
        ):
            raise StudyPlanAPIError(
                "Backend trả về dữ liệu nhiệm vụ học tập không hợp lệ."
            )

        skill = task["skill"]

        if skill is not None:
            skill_fields = {"id", "code", "name", "category"}

            if (
                not isinstance(skill, dict)
                or not skill_fields.issubset(skill)
                or type(skill["id"]) is not int
                or not isinstance(skill["code"], str)
                or not isinstance(skill["name"], str)
                or not isinstance(skill["category"], str)
            ):
                raise StudyPlanAPIError(
                    "Backend trả về thông tin kỹ năng không hợp lệ."
                )

    @staticmethod
    def _build_error(
        response: httpx.Response,
    ) -> StudyPlanAPIError:
        """Translate HTTP errors into safe Vietnamese messages."""

        status_code = response.status_code

        if status_code == 401:
            message = (
                "Phiên đăng nhập không hợp lệ hoặc đã hết hạn. "
                "Vui lòng đăng nhập lại."
            )

        elif status_code == 403:
            message = (
                "Bạn không có quyền thực hiện thao tác này."
            )

        elif status_code == 404:
            message = "Không tìm thấy kế hoạch học tập."

        elif status_code == 409:
            message = (
                "Không thể thực hiện thao tác do trạng thái "
                "kế hoạch học tập hiện tại không phù hợp. "
                "Hãy kiểm tra lại trạng thái kế hoạch."
            )

        elif status_code == 422:
            message = (
                "Dữ liệu không hợp lệ. "
                "Vui lòng kiểm tra thông tin kế hoạch học tập."
            )

        elif status_code >= 500:
            message = (
                "Backend đang gặp lỗi. "
                "Vui lòng thử lại sau."
            )

        else:
            message = (
                "Không thể thực hiện yêu cầu "
                f"(HTTP {status_code})."
            )

        return StudyPlanAPIError(
            message,
            status_code=status_code,
        )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, int] | None = None,
        payload: dict[str, Any] | None = None,
        expected_status: int = 200,
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
            raise StudyPlanAPIError(
                "Backend phản hồi quá chậm. Vui lòng thử lại."
            ) from exc

        except httpx.RequestError as exc:
            raise StudyPlanAPIError(
                "Không thể kết nối tới backend. "
                "Hãy kiểm tra xem FastAPI đã chạy chưa."
            ) from exc

        if response.status_code != expected_status:
            raise self._build_error(response)

        try:
            data = response.json()

        except (ValueError, UnicodeDecodeError) as exc:
            raise StudyPlanAPIError(
                "Backend trả về dữ liệu JSON không hợp lệ.",
                status_code=response.status_code,
            ) from exc

        if not isinstance(data, dict):
            raise StudyPlanAPIError(
                "Backend trả về cấu trúc dữ liệu không hợp lệ.",
                status_code=response.status_code,
            )

        return data

    def create_study_plan(
        self,
        title: str,
        target_score: int,
        start_date: date,
        end_date: date,
        daily_minutes: int,
    ) -> dict[str, Any]:
        """Create a personalized study plan."""

        if not isinstance(title, str) or not title.strip():
            raise ValueError("title không được để trống.")

        if len(title.strip()) > 200:
            raise ValueError("title không được vượt quá 200 ký tự.")

        if (
            isinstance(target_score, bool)
            or not isinstance(target_score, int)
            or not 0 <= target_score <= 990
        ):
            raise ValueError(
                "target_score phải là số nguyên từ 0 đến 990."
            )

        self._validate_date(start_date, "start_date")
        self._validate_date(end_date, "end_date")

        if end_date < start_date:
            raise ValueError(
                "end_date không được trước start_date."
            )

        if (
            isinstance(daily_minutes, bool)
            or not isinstance(daily_minutes, int)
            or daily_minutes <= 0
        ):
            raise ValueError(
                "daily_minutes phải là số nguyên dương."
            )

        data = self._request_json(
            "POST",
            "/study-plans",
            payload={
                "title": title.strip(),
                "target_score": target_score,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "daily_minutes": daily_minutes,
            },
            expected_status=201,
        )

        self._validate_plan_response(data)
        return data

    def get_study_plans(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return the authenticated student's paginated study plans."""

        self._validate_pagination(limit, offset)

        data = self._request_json(
            "GET",
            "/study-plans",
            params={
                "limit": limit,
                "offset": offset,
            },
        )

        required_fields = {"items", "total", "limit", "offset"}

        if (
            not required_fields.issubset(data)
            or not isinstance(data["items"], list)
            or type(data["total"]) is not int
            or data["total"] < 0
            or data["limit"] != limit
            or data["offset"] != offset
        ):
            raise StudyPlanAPIError(
                "Backend trả về danh sách kế hoạch không hợp lệ."
            )

        for plan in data["items"]:
            if not isinstance(plan, dict):
                raise StudyPlanAPIError(
                    "Backend trả về một kế hoạch không hợp lệ."
                )
            self._validate_plan_response(plan)

        return data

    def get_study_plan_detail(
        self,
        plan_id: int,
    ) -> dict[str, Any]:
        """Return one study plan and its scheduled tasks."""

        self._validate_plan_id(plan_id)

        data = self._request_json(
            "GET",
            f"/study-plans/{plan_id}",
        )

        self._validate_plan_response(data)

        if not isinstance(data.get("tasks"), list):
            raise StudyPlanAPIError(
                "Backend không trả về danh sách nhiệm vụ hợp lệ."
            )

        for task in data["tasks"]:
            self._validate_task_response(task)

        return data

    def pause_study_plan(
        self,
        plan_id: int,
    ) -> dict[str, Any]:
        """Pause an active study plan."""

        return self._change_plan_status(plan_id, "pause")

    def resume_study_plan(
        self,
        plan_id: int,
    ) -> dict[str, Any]:
        """Resume a paused study plan."""

        return self._change_plan_status(plan_id, "resume")

    def complete_study_plan(
        self,
        plan_id: int,
    ) -> dict[str, Any]:
        """Complete an active study plan."""

        return self._change_plan_status(plan_id, "complete")

    def _change_plan_status(
        self,
        plan_id: int,
        action: str,
    ) -> dict[str, Any]:
        """Call a study plan lifecycle endpoint."""

        self._validate_plan_id(plan_id)

        if action not in {"pause", "resume", "complete"}:
            raise ValueError("Thao tác trạng thái kế hoạch không hợp lệ.")

        data = self._request_json(
            "POST",
            f"/study-plans/{plan_id}/{action}",
        )

        self._validate_plan_response(data)
        return data
