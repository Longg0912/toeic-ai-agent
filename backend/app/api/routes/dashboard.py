"""Authenticated student dashboard API endpoints."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.api.authorization import require_role
from backend.app.api.deps import get_db
from backend.app.db.models import User
from backend.app.schemas.dashboard import (
    DashboardActivityResponse,
    DashboardOverviewResponse,
    DashboardPerformanceResponse,
    DashboardSkillsResponse,
    DashboardStudyPlanResponse,
)
from backend.app.services.dashboard_service import (
    DashboardStudentNotFoundError,
    get_dashboard_activity,
    get_dashboard_overview,
    get_dashboard_performance,
    get_dashboard_skills,
    get_dashboard_study_plan,
)


router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
)


def _handle_dashboard_service_error(
    exc: Exception,
) -> None:
    """Translate dashboard service errors into HTTP errors."""

    if isinstance(exc, DashboardStudentNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student account not found.",
        ) from None

    if isinstance(exc, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from None

    raise exc


@router.get(
    "/overview",
    response_model=DashboardOverviewResponse,
    summary="Get the authenticated student's dashboard overview",
)
def get_dashboard_overview_endpoint(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        User,
        Depends(require_role("student")),
    ],
) -> DashboardOverviewResponse:
    """Return high-level learning statistics."""

    try:
        return get_dashboard_overview(
            db,
            student_id=current_user.id,
        )
    except (DashboardStudentNotFoundError, ValueError) as exc:
        _handle_dashboard_service_error(exc)


@router.get(
    "/performance",
    response_model=DashboardPerformanceResponse,
    summary="Get the authenticated student's quiz performance",
)
def get_dashboard_performance_endpoint(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        User,
        Depends(require_role("student")),
    ],
) -> DashboardPerformanceResponse:
    """Return quiz performance statistics."""

    try:
        return get_dashboard_performance(
            db,
            student_id=current_user.id,
        )
    except (DashboardStudentNotFoundError, ValueError) as exc:
        _handle_dashboard_service_error(exc)


@router.get(
    "/skills",
    response_model=DashboardSkillsResponse,
    summary="Get the authenticated student's skill statistics",
)
def get_dashboard_skills_endpoint(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        User,
        Depends(require_role("student")),
    ],
) -> DashboardSkillsResponse:
    """Return learning performance grouped by skill."""

    try:
        return get_dashboard_skills(
            db,
            student_id=current_user.id,
        )
    except (DashboardStudentNotFoundError, ValueError) as exc:
        _handle_dashboard_service_error(exc)


@router.get(
    "/activity",
    response_model=DashboardActivityResponse,
    summary="Get the authenticated student's daily learning activity",
)
def get_dashboard_activity_endpoint(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        User,
        Depends(require_role("student")),
    ],
    start_date: Annotated[
        date,
        Query(description="First activity date, inclusive."),
    ],
    end_date: Annotated[
        date,
        Query(description="Last activity date, inclusive."),
    ],
) -> DashboardActivityResponse:
    """Return daily activity within an inclusive date range."""

    try:
        return get_dashboard_activity(
            db,
            student_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
        )
    except (DashboardStudentNotFoundError, ValueError) as exc:
        _handle_dashboard_service_error(exc)


@router.get(
    "/study-plan",
    response_model=DashboardStudyPlanResponse,
    summary="Get the authenticated student's active study plan progress",
)
def get_dashboard_study_plan_endpoint(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        User,
        Depends(require_role("student")),
    ],
) -> DashboardStudyPlanResponse:
    """Return active plan progress and upcoming tasks."""

    try:
        return get_dashboard_study_plan(
            db,
            student_id=current_user.id,
        )
    except (DashboardStudentNotFoundError, ValueError) as exc:
        _handle_dashboard_service_error(exc)