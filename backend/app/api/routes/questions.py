
"""Read-only API endpoints for TOEIC questions."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from backend.app.api.deps import get_db
from backend.app.db.models import Question, QuestionSkill, Skill
from backend.app.schemas.questions import (
    Part5OptionPublic,
    Part5QuestionListResponse,
    Part5QuestionPublic,
)


router = APIRouter(
    prefix="/questions",
    tags=["Questions"],
)


@router.get(
    "/part5",
    response_model=Part5QuestionListResponse,
    summary="List approved TOEIC Part 5 questions",
)
def list_part5_questions(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
    skill_code: Annotated[
        str | None,
        Query(min_length=1, max_length=64),
    ] = None,
) -> Part5QuestionListResponse:
    """List questions approved for public practice.

    Only questions with approved review status, granted usage
    permission, and public visibility are returned.

    The correct answer and explanation are not exposed here.
    """

    filters = [
        Question.part == 5,
        Question.review_status == "approved",
        Question.usage_permission_status == "granted",
        Question.visibility == "public",
    ]

    # Filter by a specific skill when requested.
    if skill_code is not None:
        matching_question_ids = (
            select(QuestionSkill.question_id)
            .join(
                Skill,
                Skill.id == QuestionSkill.skill_id,
            )
            .where(Skill.code == skill_code)
        )

        filters.append(
            Question.id.in_(matching_question_ids)
        )

    # Count all matching questions before pagination.
    total = db.scalar(
        select(func.count(Question.id)).where(*filters)
    ) or 0

    # Load options and skill relationships efficiently.
    statement = (
        select(Question)
        .where(*filters)
        .options(
            selectinload(Question.options),
            selectinload(
                Question.skill_links
            ).joinedload(QuestionSkill.skill),
        )
        .order_by(Question.id)
        .offset(offset)
        .limit(limit)
    )

    questions = db.scalars(statement).all()

    items = [
        Part5QuestionPublic(
            id=question.id,
            content=question.content,
            difficulty=question.difficulty,
            options=[
                Part5OptionPublic(
                    option_key=option.option_key,
                    content=option.content,
                )
                for option in sorted(
                    question.options,
                    key=lambda item: item.option_key,
                )
            ],
            skill_codes=sorted(
                {
                    link.skill.code
                    for link in question.skill_links
                }
            ),
        )
        for question in questions
    ]

    return Part5QuestionListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )
