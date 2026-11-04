
"""Pydantic schemas for TOEIC Tutor API."""

from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
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
