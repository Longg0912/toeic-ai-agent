
"""Pydantic schemas for TOEIC Tutor API."""

from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class TutorExplainRequest(BaseModel):
    """Request schema for asking AI to explain a TOEIC question."""

    model_config = ConfigDict(extra="forbid")

    question_id: int = Field(
        gt=0,
        description="ID of the TOEIC question to explain.",
    )


class TutorExplainResponse(BaseModel):
    """Response schema containing the AI explanation."""

    model_config = ConfigDict(extra="forbid")

    question_id: int = Field(gt=0)

    correct_option_key: str = Field(
        pattern="^[A-D]$",
    )

    explanation: str = Field(min_length=1)


class TutorSelectionContext(BaseModel):
    """Context describing the text selected by a student."""

    model_config = ConfigDict(extra="forbid")

    selected_text: str = Field(
        min_length=1,
        max_length=2000,
        description="Text selected by the student.",
    )

    source_type: Literal[
        "quiz_question",
        "quiz_option",
        "reading_passage",
        "explanation",
        "general",
    ] = Field(
        default="general",
        description="The type of content containing the selection.",
    )

    quiz_session_id: int | None = Field(
        default=None,
        gt=0,
        description="Quiz session containing the selected content.",
    )

    quiz_item_id: int | None = Field(
        default=None,
        gt=0,
        description="Quiz item containing the selected content.",
    )

    part_number: int | None = Field(
        default=None,
        ge=5,
        le=7,
        description="TOEIC Reading part number.",
    )

    surrounding_text: str | None = Field(
        default=None,
        max_length=6000,
        description="Text surrounding the selected content.",
    )

    @field_validator("selected_text")
    @classmethod
    def validate_selected_text(cls, value: str) -> str:
        """Reject selections containing only whitespace."""

        value = value.strip()

        if not value:
            raise ValueError(
                "Selected text must not be empty."
            )

        return value

    @field_validator("surrounding_text")
    @classmethod
    def validate_surrounding_text(
        cls,
        value: str | None,
    ) -> str | None:
        """Normalize optional surrounding text."""

        if value is None:
            return None

        value = value.strip()

        return value or None

    @model_validator(mode="after")
    def validate_quiz_references(
        self,
    ) -> "TutorSelectionContext":
        """Require quiz session and item IDs together."""

        has_session_id = self.quiz_session_id is not None
        has_item_id = self.quiz_item_id is not None

        if has_session_id != has_item_id:
            raise ValueError(
                "quiz_session_id and quiz_item_id "
                "must be provided together."
            )

        return self


class TutorChatRequest(BaseModel):
    """Request schema for sending a message to AI Tutor."""

    model_config = ConfigDict(extra="forbid")

    chat_session_id: int | None = Field(
        default=None,
        gt=0,
        description="Existing chat session ID, or null to create a new chat.",
    )

    message: str = Field(
        min_length=1,
        max_length=4000,
        description="The student's message.",
    )

    selection_context: TutorSelectionContext | None = Field(
        default=None,
        description=(
            "Optional context describing text selected "
            "by the student."
        ),
    )

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        """Reject messages containing only whitespace."""

        value = value.strip()

        if not value:
            raise ValueError("Message must not be empty.")

        return value


class TutorChatMessagePublic(BaseModel):
    """Public representation of one chat message."""

    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)

    role: Literal["user", "assistant"]

    content: str = Field(min_length=1)

    created_at: datetime


class TutorChatResponse(BaseModel):
    """Response returned after sending a chat message."""

    model_config = ConfigDict(extra="forbid")

    chat_session_id: int = Field(gt=0)

    title: str = Field(min_length=1, max_length=150)

    user_message: TutorChatMessagePublic

    assistant_message: TutorChatMessagePublic


class TutorChatSessionSummary(BaseModel):
    """Summary of one conversation in the chat history."""

    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)

    title: str = Field(min_length=1, max_length=150)

    created_at: datetime

    updated_at: datetime

    message_count: int = Field(ge=0)


class TutorChatSessionListResponse(BaseModel):
    """Paginated list of chat sessions."""

    model_config = ConfigDict(extra="forbid")

    items: list[TutorChatSessionSummary]

    total: int = Field(ge=0)

    limit: int = Field(ge=1, le=100)

    offset: int = Field(ge=0)


class TutorChatSessionDetailResponse(BaseModel):
    """One conversation with its complete message history."""

    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)

    title: str = Field(min_length=1, max_length=150)

    created_at: datetime

    updated_at: datetime

    messages: list[TutorChatMessagePublic]
