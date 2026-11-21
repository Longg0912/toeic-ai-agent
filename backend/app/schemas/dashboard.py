
"""Response schemas for the student learning dashboard."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.study_plans import (
    StudyPlanPublic,
    StudyPlanTaskPublic,
)


class DashboardOverviewResponse(BaseModel):
    """High-level learning statistics for the authenticated student."""

    model_config = ConfigDict(extra="forbid")

    target_score: int | None = Field(
        default=None,
        ge=0,
        le=990,
    )

    active_plan: StudyPlanPublic | None = None

    submitted_quiz_sessions: int = Field(ge=0)

    answered_questions: int = Field(ge=0)

    correct_answers: int = Field(ge=0)

    accuracy_percent: float = Field(
        ge=0,
        le=100,
    )

    active_days: int = Field(ge=0)


class DashboardPerformanceResponse(BaseModel):
    """Aggregated quiz performance for the authenticated student."""

    model_config = ConfigDict(extra="forbid")

    submitted_sessions: int = Field(ge=0)

    answered_questions: int = Field(ge=0)

    correct_answers: int = Field(ge=0)

    incorrect_answers: int = Field(ge=0)

    accuracy_percent: float = Field(
        ge=0,
        le=100,
    )

    total_time_spent_seconds: int = Field(ge=0)


class DashboardSkillItem(BaseModel):
    """Learning performance for one TOEIC skill."""

    model_config = ConfigDict(extra="forbid")

    skill_id: int

    code: str

    name: str

    category: str

    attempt_count: int = Field(ge=0)

    correct_count: int = Field(ge=0)

    incorrect_count: int = Field(ge=0)

    accuracy_percent: float = Field(
        ge=0,
        le=100,
    )

    is_weak: bool


class DashboardSkillsResponse(BaseModel):
    """Skill-level learning statistics."""

    model_config = ConfigDict(extra="forbid")

    items: list[DashboardSkillItem] = Field(
        default_factory=list,
    )

    total: int = Field(ge=0)


class DashboardActivityDay(BaseModel):
    """Learning activity aggregated for one calendar day."""

    model_config = ConfigDict(extra="forbid")

    activity_date: date

    submitted_sessions: int = Field(ge=0)

    answered_questions: int = Field(ge=0)

    correct_answers: int = Field(ge=0)

    accuracy_percent: float = Field(
        ge=0,
        le=100,
    )


class DashboardActivityResponse(BaseModel):
    """Daily learning activity over a requested date range."""

    model_config = ConfigDict(extra="forbid")

    start_date: date

    end_date: date

    days: list[DashboardActivityDay] = Field(
        default_factory=list,
    )

    total_active_days: int = Field(ge=0)

    total_submitted_sessions: int = Field(ge=0)

    total_answered_questions: int = Field(ge=0)


class DashboardStudyPlanResponse(BaseModel):
    """Progress summary for the authenticated student's active plan."""

    model_config = ConfigDict(extra="forbid")

    plan: StudyPlanPublic | None = None

    total_tasks: int = Field(ge=0)

    completed_tasks: int = Field(ge=0)

    pending_tasks: int = Field(ge=0)

    skipped_tasks: int = Field(ge=0)

    completion_percent: float = Field(
        ge=0,
        le=100,
    )

    upcoming_tasks: list[StudyPlanTaskPublic] = Field(
        default_factory=list,
    )
