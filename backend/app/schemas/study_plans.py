
"""Request and response schemas for TOEIC study plans."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


StudyPlanStatus = Literal[
    "active",
    "paused",
    "completed",
    "cancelled",
]

StudyPlanTaskType = Literal[
    "practice",
    "review",
    "quiz",
]

StudyPlanTaskStatus = Literal[
    "pending",
    "completed",
    "skipped",
]


class StudyPlanCreateRequest(BaseModel):
    """Request payload for creating a study plan."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        min_length=1,
        max_length=200,
    )

    target_score: int = Field(
        ge=0,
        le=990,
        strict=True,
    )

    start_date: date

    end_date: date

    daily_minutes: int = Field(
        gt=0,
        strict=True,
    )


class StudyPlanSkillPublic(BaseModel):
    """Public skill information attached to a task."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    category: str


class StudyPlanTaskPublic(BaseModel):
    """Public representation of one scheduled task."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    skill_id: int | None
    skill: StudyPlanSkillPublic | None
    task_type: StudyPlanTaskType
    scheduled_date: date
    estimated_minutes: int
    target_question_count: int
    status: StudyPlanTaskStatus
    completed_at: datetime | None


class StudyPlanPublic(BaseModel):
    """Summary information for one study plan."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    target_score: int
    start_date: date
    end_date: date
    daily_minutes: int
    status: StudyPlanStatus
    created_at: datetime
    updated_at: datetime


class StudyPlanDetailResponse(StudyPlanPublic):
    """Study plan details including its scheduled tasks."""

    tasks: list[StudyPlanTaskPublic]


class StudyPlanListResponse(BaseModel):
    """Paginated list of the authenticated student's plans."""

    items: list[StudyPlanPublic]
    total: int
    limit: int
    offset: int


class AdaptiveStudyPlanResponse(BaseModel):
    """Result returned after adapting a study plan."""

    plan_id: int
    updated_task_count: int
    prioritized_skill_ids: list[int]
