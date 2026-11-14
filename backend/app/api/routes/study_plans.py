
"""Study plan API endpoints.

Routes:
- POST /study-plans
- GET /study-plans
- GET /study-plans/{plan_id}
"""

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.app.api.authorization import require_role
from backend.app.api.deps import get_db
from backend.app.db.models import StudyPlan, StudyPlanTask, User
from backend.app.schemas.study_plans import (
    StudyPlanCreateRequest,
    StudyPlanDetailResponse,
    StudyPlanListResponse,
    StudyPlanPublic,
    StudyPlanTaskPublic,
)
from backend.app.services.study_plan_service import (
    ActiveStudyPlanExistsError,
    StudyPlanNotActiveError,
    StudyPlanNotFoundError,
    StudyPlanNotPausedError,
    StudyPlanUserNotEligibleError,
    StudyPlanUserNotFoundError,
    StudyPlanValidationError,
    complete_study_plan,
    create_study_plan,
    pause_study_plan,
    resume_study_plan,
)


router = APIRouter(
    prefix="/study-plans",
    tags=["Study Plans"],
)


@router.post(
    "",
    response_model=StudyPlanPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create a personalized study plan",
)
def create_study_plan_endpoint(
    payload: StudyPlanCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        User,
        Depends(require_role("student")),
    ],
) -> StudyPlanPublic:
    """Create a study plan for the authenticated student."""

    try:
        plan = create_study_plan(
            db,
            student_id=current_user.id,
            title=payload.title,
            target_score=payload.target_score,
            start_date=payload.start_date,
            end_date=payload.end_date,
            daily_minutes=payload.daily_minutes,
        )

        return StudyPlanPublic.model_validate(plan)

    except ActiveStudyPlanExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active study plan already exists.",
        ) from None

    except StudyPlanValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from None

    except StudyPlanUserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student account not found.",
        ) from None

    except StudyPlanUserNotEligibleError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account cannot create a study plan.",
        ) from None


@router.get(
    "",
    response_model=StudyPlanListResponse,
    summary="List the authenticated student's study plans",
)
def list_study_plans(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        User,
        Depends(require_role("student")),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> StudyPlanListResponse:
    """Return a paginated list of the current student's plans."""

    owner_filter = StudyPlan.user_id == current_user.id

    total = db.scalar(
        select(func.count(StudyPlan.id)).where(owner_filter)
    ) or 0

    plans = db.scalars(
        select(StudyPlan)
        .where(owner_filter)
        .order_by(
            StudyPlan.created_at.desc(),
            StudyPlan.id.desc(),
        )
        .offset(offset)
        .limit(limit)
    ).all()

    return StudyPlanListResponse(
        items=[
            StudyPlanPublic.model_validate(plan)
            for plan in plans
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{plan_id}",
    response_model=StudyPlanDetailResponse,
    summary="Get study plan details",
)
def get_study_plan_detail(
    plan_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        User,
        Depends(require_role("student")),
    ],
) -> StudyPlanDetailResponse:
    """Return a study plan and its tasks for the owning student."""

    plan = db.scalar(
        select(StudyPlan)
        .where(
            StudyPlan.id == plan_id,
            StudyPlan.user_id == current_user.id,
        )
        .options(
            selectinload(StudyPlan.tasks).selectinload(
                StudyPlanTask.skill
            )
        )
    )

    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Study plan not found.",
        )

    # Sort tasks deterministically for the API response.
    ordered_tasks = sorted(
        plan.tasks,
        key=lambda task: (
            task.scheduled_date,
            task.id,
        ),
    )

    plan_summary = StudyPlanPublic.model_validate(plan)

    return StudyPlanDetailResponse(
        **plan_summary.model_dump(),
        tasks=[
            StudyPlanTaskPublic.model_validate(task)
            for task in ordered_tasks
        ],
    )


@router.post(
    "/{plan_id}/pause",
    response_model=StudyPlanPublic,
    summary="Pause an active study plan",
)
def pause_study_plan_endpoint(
    plan_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        User,
        Depends(require_role("student")),
    ],
) -> StudyPlanPublic:
    """Pause the authenticated student's active study plan."""

    try:
        plan = pause_study_plan(
            db,
            student_id=current_user.id,
            plan_id=plan_id,
        )

        return StudyPlanPublic.model_validate(plan)

    except StudyPlanNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Study plan not found.",
        ) from None

    except StudyPlanNotActiveError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only an active study plan can be paused.",
        ) from None


@router.post(
    "/{plan_id}/resume",
    response_model=StudyPlanPublic,
    summary="Resume a paused study plan",
)
def resume_study_plan_endpoint(
    plan_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        User,
        Depends(require_role("student")),
    ],
) -> StudyPlanPublic:
    """Resume the authenticated student's paused study plan."""

    try:
        plan = resume_study_plan(
            db,
            student_id=current_user.id,
            plan_id=plan_id,
        )

        return StudyPlanPublic.model_validate(plan)

    except StudyPlanNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Study plan not found.",
        ) from None

    except StudyPlanNotPausedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a paused study plan can be resumed.",
        ) from None

    except ActiveStudyPlanExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active study plan already exists.",
        ) from None


@router.post(
    "/{plan_id}/complete",
    response_model=StudyPlanPublic,
    summary="Complete an active study plan",
)
def complete_study_plan_endpoint(
    plan_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        User,
        Depends(require_role("student")),
    ],
) -> StudyPlanPublic:
    """Complete the authenticated student's active study plan."""

    try:
        plan = complete_study_plan(
            db,
            student_id=current_user.id,
            plan_id=plan_id,
        )

        return StudyPlanPublic.model_validate(plan)

    except StudyPlanNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Study plan not found.",
        ) from None

    except StudyPlanNotActiveError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only an active study plan can be completed.",
        ) from None
