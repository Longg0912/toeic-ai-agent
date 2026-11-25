"""HTTP client for the Gemini TOEIC Tutor API."""

import os
from typing import Any

import httpx


DEFAULT_API_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_TIMEOUT = 60.0


class TutorAPIError(RuntimeError):
    """A safe, user-facing error raised by the Tutor API client."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code


class TutorAPIClient:
    """Synchronous authenticated client for TOEIC Tutor endpoints."""

    def __init__(
        self,
        base_url: str | None = None,
        access_token: str = "",
        timeout: float = DEFAULT_TIMEOUT,
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

    def __enter__(self) -> "TutorAPIClient":
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
    def _validate_positive_id(
        value: int,
        field_name: str,
    ) -> None:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
        ):
            raise ValueError(
                f"{field_name} phải là số nguyên dương."
            )

    @staticmethod
    def _validate_chat_message(message: str) -> str:
        if not isinstance(message, str):
            raise ValueError("Tin nhắn phải là chuỗi ký tự.")

        normalized = message.strip()

        if not normalized:
            raise ValueError("Tin nhắn không được để trống.")

        if len(normalized) > 4000:
            raise ValueError(
                "Tin nhắn không được vượt quá 4000 ký tự."
            )

        return normalized
    @staticmethod
    def _validate_selection_context(
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate and normalize a text-selection context."""

        if not isinstance(context, dict):
            raise ValueError(
                "selection_context phải là dictionary."
            )

        allowed_fields = {
            "selected_text",
            "source_type",
            "quiz_session_id",
            "quiz_item_id",
            "part_number",
            "surrounding_text",
        }

        unknown_fields = set(context) - allowed_fields

        if unknown_fields:
            raise ValueError(
                "selection_context chứa trường không được hỗ trợ."
            )

        selected_text = context.get("selected_text")

        if not isinstance(selected_text, str):
            raise ValueError("selected_text phải là chuỗi.")

        selected_text = selected_text.strip()

        if not selected_text:
            raise ValueError("selected_text không được để trống.")

        if len(selected_text) > 2000:
            raise ValueError(
                "selected_text không được vượt quá 2000 ký tự."
            )

        source_type = context.get("source_type")

        allowed_source_types = {
            "quiz_question",
            "quiz_option",
            "reading_passage",
            "explanation",
            "general",
        }

        if source_type not in allowed_source_types:
            raise ValueError("source_type không hợp lệ.")

        normalized: dict[str, Any] = {
            "selected_text": selected_text,
            "source_type": source_type,
        }

        quiz_session_id = context.get("quiz_session_id")
        quiz_item_id = context.get("quiz_item_id")

        if (quiz_session_id is None) != (quiz_item_id is None):
            raise ValueError(
                "quiz_session_id và quiz_item_id "
                "phải được cung cấp cùng nhau."
            )

        for field_name, value in (
            ("quiz_session_id", quiz_session_id),
            ("quiz_item_id", quiz_item_id),
        ):
            if value is not None:
                if (
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or value <= 0
                ):
                    raise ValueError(
                        f"{field_name} phải là số nguyên dương."
                    )

                normalized[field_name] = value

        part_number = context.get("part_number")

        if part_number is not None:
            if (
                isinstance(part_number, bool)
                or not isinstance(part_number, int)
                or part_number not in (5, 6, 7)
            ):
                raise ValueError(
                    "part_number chỉ được nhận giá trị 5, 6 hoặc 7."
                )

            normalized["part_number"] = part_number

        surrounding_text = context.get("surrounding_text")

        if surrounding_text is not None:
            if not isinstance(surrounding_text, str):
                raise ValueError(
                    "surrounding_text phải là chuỗi."
                )

            surrounding_text = surrounding_text.strip()

            if len(surrounding_text) > 6000:
                raise ValueError(
                    "surrounding_text không được vượt quá 6000 ký tự."
                )

            normalized["surrounding_text"] = surrounding_text

        return normalized
    # =================================================
    # Error handling
    # =================================================

    @staticmethod
    def _build_error(
        response: httpx.Response,
    ) -> TutorAPIError:
        """Translate HTTP errors into safe Vietnamese messages."""

        status_code = response.status_code

        if status_code == 401:
            message = (
                "Phiên đăng nhập không hợp lệ hoặc đã hết hạn. "
                "Vui lòng đăng nhập lại."
            )

        elif status_code == 403:
            message = (
                "Bạn không có quyền truy cập tài nguyên này."
            )

        elif status_code == 404:
            message = (
                "Không tìm thấy câu hỏi hoặc hội thoại "
                "hoặc bạn không có quyền truy cập."
            )

        elif status_code == 409:
            message = (
                "Câu hỏi chưa đủ dữ liệu để Gemini giải thích."
            )

        elif status_code == 422:
            message = (
                "Dữ liệu gửi lên không hợp lệ. "
                "Vui lòng kiểm tra lại."
            )

        elif status_code == 502:
            message = (
                "Gemini hiện không thể tạo phản hồi. "
                "Vui lòng thử lại sau."
            )

        elif status_code == 503:
            message = (
                "Dịch vụ gia sư AI chưa được cấu hình đầy đủ. "
                "Vui lòng liên hệ quản trị viên."
            )

        elif status_code >= 500:
            message = (
                "Backend đang gặp lỗi khi xử lý yêu cầu. "
                "Vui lòng thử lại sau."
            )

        else:
            message = (
                f"Không thể gọi gia sư AI (HTTP {status_code})."
            )

        return TutorAPIError(
            message,
            status_code=status_code,
        )

    def _request_json(
        self,
        method: str,
        endpoint: str,
        *,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send an authenticated request and return a JSON object."""

        try:
            response = self._client.request(
                method,
                endpoint,
                json=payload,
                params=params,
            )

        except httpx.TimeoutException:
            raise TutorAPIError(
                "Gemini phản hồi quá chậm. "
                "Vui lòng thử lại sau."
            ) from None

        except httpx.RequestError:
            raise TutorAPIError(
                "Không thể kết nối tới backend. "
                "Hãy kiểm tra xem FastAPI đã chạy chưa."
            ) from None

        if not response.is_success:
            raise self._build_error(response)

        try:
            data = response.json()
        except ValueError:
            raise TutorAPIError(
                "Backend trả về dữ liệu không hợp lệ.",
                status_code=response.status_code,
            ) from None

        if not isinstance(data, dict):
            raise TutorAPIError(
                "Định dạng dữ liệu từ Tutor API không hợp lệ.",
                status_code=response.status_code,
            )

        return data

    # =================================================
    # Existing question explanation API
    # =================================================

    def explain_question(
        self,
        question_id: int,
    ) -> dict[str, Any]:
        """Request a Vietnamese AI explanation for a TOEIC question."""

        self._validate_positive_id(
            question_id,
            "question_id",
        )

        data = self._request_json(
            "POST",
            "/tutor/explain",
            payload={
                "question_id": question_id,
            },
        )

        returned_question_id = data.get("question_id")
        correct_option_key = data.get("correct_option_key")
        explanation = data.get("explanation")

        if (
            isinstance(returned_question_id, bool)
            or not isinstance(returned_question_id, int)
            or returned_question_id != question_id
            or correct_option_key not in ("A", "B", "C", "D")
            or not isinstance(explanation, str)
            or not explanation.strip()
        ):
            raise TutorAPIError(
                "Dữ liệu lời giải từ Tutor API không đầy đủ."
            )

        return {
            "question_id": returned_question_id,
            "correct_option_key": correct_option_key,
            "explanation": explanation,
        }

    # =================================================
    # Multi-turn chat API
    # =================================================

    @staticmethod
    def _parse_chat_message(
        data: Any,
        expected_role: str | None = None,
    ) -> dict[str, Any]:
        """Validate one chat message returned by the backend."""

        if not isinstance(data, dict):
            raise TutorAPIError(
                "Dữ liệu tin nhắn từ backend không hợp lệ."
            )

        message_id = data.get("id")
        role = data.get("role")
        content = data.get("content")
        created_at = data.get("created_at")

        if (
            isinstance(message_id, bool)
            or not isinstance(message_id, int)
            or message_id <= 0
            or role not in ("user", "assistant")
            or (
                expected_role is not None
                and role != expected_role
            )
            or not isinstance(content, str)
            or not content.strip()
            or not isinstance(created_at, str)
        ):
            raise TutorAPIError(
                "Dữ liệu tin nhắn từ backend không đầy đủ."
            )

        return {
            "id": message_id,
            "role": role,
            "content": content,
            "created_at": created_at,
        }

    def send_message(
        self,
        message: str,
        chat_session_id: int | None = None,
        selection_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a message, optionally with selected-text context."""

        normalized_message = self._validate_chat_message(message)

        payload: dict[str, Any] = {
            "message": normalized_message,
        }

        if chat_session_id is not None:
            self._validate_positive_id(
                chat_session_id,
                "chat_session_id",
            )
            payload["chat_session_id"] = chat_session_id

        if selection_context is not None:
            payload["selection_context"] = (
                self._validate_selection_context(
                    selection_context
                )
            )

        data = self._request_json(
            "POST",
            "/tutor/chat",
            payload=payload,
        )

        returned_session_id = data.get("chat_session_id")
        title = data.get("title")

        if (
            isinstance(returned_session_id, bool)
            or not isinstance(returned_session_id, int)
            or returned_session_id <= 0
            or not isinstance(title, str)
            or not title.strip()
        ):
            raise TutorAPIError(
                "Dữ liệu hội thoại từ Tutor API không đầy đủ."
            )

        user_message = self._parse_chat_message(
            data.get("user_message"),
            expected_role="user",
        )

        assistant_message = self._parse_chat_message(
            data.get("assistant_message"),
            expected_role="assistant",
        )

        return {
            "chat_session_id": returned_session_id,
            "title": title,
            "user_message": user_message,
            "assistant_message": assistant_message,
        }

    def list_sessions(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List the current user's Tutor chat sessions."""

        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 50
        ):
            raise ValueError("limit phải là số nguyên từ 1 đến 50.")

        if (
            isinstance(offset, bool)
            or not isinstance(offset, int)
            or offset < 0
        ):
            raise ValueError("offset phải là số nguyên không âm.")

        data = self._request_json(
            "GET",
            "/tutor/sessions",
            params={"limit": limit, "offset": offset},
        )

        items = data.get("items")
        total = data.get("total")
        returned_limit = data.get("limit")
        returned_offset = data.get("offset")

        if (
            not isinstance(items, list)
            or isinstance(total, bool)
            or not isinstance(total, int)
            or total < 0
            or returned_limit != limit
            or returned_offset != offset
        ):
            raise TutorAPIError(
                "Dữ liệu danh sách hội thoại từ Tutor API không đầy đủ."
            )

        parsed_items: list[dict[str, Any]] = []

        for item in items:
            if not isinstance(item, dict):
                raise TutorAPIError(
                    "Dữ liệu một hội thoại từ Tutor API không hợp lệ."
                )

            session_id = item.get("id")
            title = item.get("title")
            message_count = item.get("message_count")
            created_at = item.get("created_at")
            updated_at = item.get("updated_at")

            if (
                isinstance(session_id, bool)
                or not isinstance(session_id, int)
                or session_id <= 0
                or not isinstance(title, str)
                or not title.strip()
                or isinstance(message_count, bool)
                or not isinstance(message_count, int)
                or message_count < 0
                or not isinstance(created_at, str)
                or not isinstance(updated_at, str)
            ):
                raise TutorAPIError(
                    "Dữ liệu một hội thoại từ Tutor API không đầy đủ."
                )

            parsed_items.append(
                {
                    "id": session_id,
                    "title": title,
                    "message_count": message_count,
                    "created_at": created_at,
                    "updated_at": updated_at,
                }
            )

        return {
            "items": parsed_items,
            "total": total,
            "limit": returned_limit,
            "offset": returned_offset,
        }

    def get_session(
        self,
        session_id: int,
    ) -> dict[str, Any]:
        """Get one chat session and all its messages."""

        self._validate_positive_id(
            session_id,
            "session_id",
        )

        data = self._request_json(
            "GET",
            f"/tutor/sessions/{session_id}",
        )

        returned_id = data.get("id")
        title = data.get("title")
        created_at = data.get("created_at")
        updated_at = data.get("updated_at")
        messages = data.get("messages")

        if (
            isinstance(returned_id, bool)
            or not isinstance(returned_id, int)
            or returned_id != session_id
            or not isinstance(title, str)
            or not title.strip()
            or not isinstance(created_at, str)
            or not isinstance(updated_at, str)
            or not isinstance(messages, list)
        ):
            raise TutorAPIError(
                "Dữ liệu chi tiết hội thoại không đầy đủ."
            )

        parsed_messages = [
            self._parse_chat_message(item)
            for item in messages
        ]

        return {
            "id": returned_id,
            "title": title,
            "created_at": created_at,
            "updated_at": updated_at,
            "messages": parsed_messages,
        }