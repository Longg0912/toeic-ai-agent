
"""Protected API endpoints for the TOEIC AI Tutor."""

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from backend.app.api.auth_deps import get_current_user
from backend.app.api.deps import get_db
from backend.app.db.models import (
    Question,
    QuestionSkill,
    User,
)
from backend.app.schemas.tutor import (
    TutorExplainRequest,
    TutorExplainResponse,
)
from backend.app.services.gemini_tutor import (
    GeminiConfigurationError,
    GeminiServiceError,
    explain_toeic_question,
)


router = APIRouter(
    prefix="/tutor",
    tags=["AI Tutor"],
)


@router.post(
    "/explain",
    response_model=TutorExplainResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate a Vietnamese explanation for a TOEIC question",
)
def explain_question(
    request_data: TutorExplainRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TutorExplainResponse:
    """Generate an explanation for an accessible TOEIC Part 5 question.

    Public questions must be approved and have granted usage permission.
    Private questions can only be accessed by their owner.

    The official answer key is always retrieved from the database.
    """

    # Public questions must be approved and permitted.
    public_question_filter = and_(
        Question.visibility == "public",
        Question.review_status == "approved",
        Question.usage_permission_status == "granted",
    )

    # Private questions are accessible only to their owner.
    private_question_filter = and_(
        Question.visibility == "private",
        Question.owner_user_id == current_user.id,
    )

    statement = (
        select(Question)
        .where(
            Question.id == request_data.question_id,
            Question.part == 5,
            or_(
                public_question_filter,
                private_question_filter,
            ),
        )
        .options(
            selectinload(Question.options),
            selectinload(
                Question.skill_links
            ).joinedload(QuestionSkill.skill),
        )
    )

    question = db.scalars(statement).first()

    # Return the same response for missing and inaccessible questions.
    if question is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found.",
        )

    # Sort options by their answer keys.
    sorted_options = sorted(
        question.options,
        key=lambda option: option.option_key,
    )

    # The Tutor currently supports complete Part 5 questions only.
    option_keys = {
        option.option_key
        for option in sorted_options
    }

    if option_keys != {"A", "B", "C", "D"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Question does not have four complete answer options.",
        )

    # Confirm that the database answer key matches an existing option.
    if question.correct_option_key not in option_keys:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Question answer key is invalid.",
        )

    # Prepare question data for Gemini.
    options_for_gemini = [
        {
            "option_key": option.option_key,
            "content": option.content,
        }
        for option in sorted_options
    ]

    skill_codes = sorted(
        {
            link.skill.code
            for link in question.skill_links
        }
    )

    try:
        explanation = explain_toeic_question(
            question_content=question.content,
            options=options_for_gemini,
            correct_option_key=question.correct_option_key,
            existing_explanation=question.explanation,
            skill_codes=skill_codes,
        )

    except GeminiConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI Tutor service is not configured.",
        ) from None

    except GeminiServiceError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI Tutor could not generate an explanation.",
        ) from None

    return TutorExplainResponse(
        question_id=question.id,
        correct_option_key=question.correct_option_key,
        explanation=explanation,
    )
