
"""Request and response schemas for TOEIC quiz sessions."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.questions import Part5OptionPublic


QuizSessionStatus = Literal["in_progress", "submitted", "abandoned"]
OptionKey = Literal["A", "B", "C", "D"]


class QuizSessionCreateRequest(BaseModel):
    """Parameters for creating a TOEIC Part 5 practice session."""

    model_config = ConfigDict(extra="forbid")

    question_count: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Number of questions to include, from 1 to 50.",
    )
    skill_code: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="Optional skill code used to filter questions.",
    )


class QuizSessionItemPublic(BaseModel):
    """One question assigned to a practice session."""

    id: int
    question_id: int
    position: int
    content: str
    difficulty: int | None
    options: list[Part5OptionPublic]
    skill_codes: list[str]


class QuizSessionCreateResponse(BaseModel):
    """Public response after creating a practice session."""

    id: int
    status: str
    started_at: datetime
    question_count: int
    items: list[QuizSessionItemPublic]


class QuizSessionAnswerInput(BaseModel):
    """One answer submitted for a quiz item."""

    model_config = ConfigDict(extra="forbid")

    quiz_item_id: int = Field(gt=0)
    selected_option_key: OptionKey
    time_spent_seconds: int | None = Field(default=None, ge=0)


class QuizSessionSubmitRequest(BaseModel):
    """Answers submitted for an entire quiz session."""

    model_config = ConfigDict(extra="forbid")

    answers: list[QuizSessionAnswerInput] = Field(min_length=1)


class QuizSessionSubmitItemPublic(BaseModel):
    """Graded result for one quiz item."""

    quiz_item_id: int
    question_id: int
    position: int
    content: str
    difficulty: int | None
    options: list[Part5OptionPublic]
    skill_codes: list[str]
    selected_option_key: OptionKey
    correct_option_key: OptionKey
    is_correct: bool
    explanation: str | None


class QuizSessionSubmitResponse(BaseModel):
    """Graded result for a completed quiz session."""

    session_id: int
    status: Literal["submitted"]
    finished_at: datetime
    total_questions: int
    answered_count: int
    correct_count: int
    accuracy_percent: float
    items: list[QuizSessionSubmitItemPublic]


class QuizSessionHistoryItemPublic(BaseModel):
    """Summary of one practice session."""

    id: int
    status: QuizSessionStatus
    started_at: datetime
    finished_at: datetime | None
    question_count: int
    answered_count: int
    correct_count: int | None = None
    accuracy_percent: float | None = None


class QuizSessionHistoryListResponse(BaseModel):
    """Paginated history for the authenticated user."""

    items: list[QuizSessionHistoryItemPublic]
    total: int
    limit: int
    offset: int


class QuizSessionDetailItemPublic(BaseModel):
    """One question in the history detail response."""

    quiz_item_id: int
    question_id: int
    position: int
    content: str
    difficulty: int | None
    options: list[Part5OptionPublic]
    skill_codes: list[str]

    # These values remain null until the session is submitted.
    selected_option_key: OptionKey | None = None
    correct_option_key: OptionKey | None = None
    is_correct: bool | None = None
    explanation: str | None = None


class QuizSessionDetailResponse(QuizSessionHistoryItemPublic):
    """Detailed review of one practice session."""

    items: list[QuizSessionDetailItemPublic]
