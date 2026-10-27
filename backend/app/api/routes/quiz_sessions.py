
"""API for creating TOEIC Part 5 practice sessions."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from backend.app.api.auth_deps import get_current_user
from backend.app.api.deps import get_db
from backend.app.db.models import (
    Question,
    QuestionOption,
    QuestionSkill,
    QuizItem,
    QuizSession,
    Skill,
    User,
)
from backend.app.schemas.questions import Part5OptionPublic
from backend.app.schemas.quiz_sessions import (
    QuizSessionCreateRequest,
    QuizSessionCreateResponse,
    QuizSessionItemPublic,
)


router = APIRouter(tags=["Quiz Sessions"])


@router.post(
    "/quiz-sessions",
    response_model=QuizSessionCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a TOEIC Part 5 practice session",
)
def create_quiz_session(
    payload: QuizSessionCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> QuizSessionCreateResponse:
    """Create a practice session for the authenticated user.

    Only approved, publicly visible questions with granted
    usage permission and exactly four options are eligible.

    Correct answers and explanations are never returned.
    """

    # A complete Part 5 question must contain exactly four
    # distinct option keys. The database already enforces
    # valid keys and uniqueness for each question.
    questions_with_four_options = (
        select(QuestionOption.question_id)
        .group_by(QuestionOption.question_id)
        .having(func.count(QuestionOption.id) == 4)
    )

    filters = [
        Question.part == 5,
        Question.review_status == "approved",
        Question.usage_permission_status == "granted",
        Question.visibility == "public",
        Question.id.in_(questions_with_four_options),
    ]

    # Apply an optional skill filter.
    if payload.skill_code is not None:
        matching_question_ids = (
            select(QuestionSkill.question_id)
            .join(
                Skill,
                Skill.id == QuestionSkill.skill_id,
            )
            .where(Skill.code == payload.skill_code)
        )

        filters.append(
            Question.id.in_(matching_question_ids)
        )

    # Check the available question count before writing anything.
    total_available = (
        db.scalar(
            select(func.count(Question.id)).where(*filters)
        )
        or 0
    )

    if total_available < payload.question_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": (
                    "Not enough eligible TOEIC Part 5 questions."
                ),
                "requested": payload.question_count,
                "available": total_available,
            },
        )

    # Randomly select distinct questions and load related data.
    statement = (
        select(Question)
        .where(*filters)
        .options(
            selectinload(Question.options),
            selectinload(
                Question.skill_links
            ).joinedload(QuestionSkill.skill),
        )
        .order_by(func.random())
        .limit(payload.question_count)
    )

    questions = db.scalars(statement).all()

    # Recheck the result in case the available data changed.
    if len(questions) < payload.question_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": (
                    "Not enough eligible TOEIC Part 5 questions."
                ),
                "requested": payload.question_count,
                "available": len(questions),
            },
        )

    try:
        # Create the session for the authenticated user.
        quiz_session = QuizSession(
            user_id=current_user.id,
            status="in_progress",
        )
        db.add(quiz_session)
        db.flush()
        db.refresh(quiz_session)

        # Keep response data separate from private answer data.
        prepared_items: list[
            tuple[
                QuizItem,
                Question,
                list[Part5OptionPublic],
                list[str],
            ]
        ] = []

        for position, question in enumerate(questions, start=1):
            sorted_options = sorted(
                question.options,
                key=lambda option: option.option_key,
            )

            options_data = [
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

            # Freeze the question text and choices so future
            # edits do not change this session's question.
            question_snapshot = {
                "content": question.content,
                "difficulty": question.difficulty,
                "options": options_data,
                "skill_codes": skill_codes,
            }

            quiz_item = QuizItem(
                quiz_session_id=quiz_session.id,
                question_id=question.id,
                position=position,
                question_snapshot=question_snapshot,

                # Store the answer key privately for later grading.
                # This field is never included in the API response.
                answer_key_snapshot=question.correct_option_key,
            )

            db.add(quiz_item)

            public_options = [
                Part5OptionPublic(**option)
                for option in options_data
            ]

            prepared_items.append(
                (
                    quiz_item,
                    question,
                    public_options,
                    skill_codes,
                )
            )

        # Assign database IDs to all quiz items.
        db.flush()

        response_items = [
            QuizSessionItemPublic(
                id=quiz_item.id,
                question_id=question.id,
                position=quiz_item.position,
                content=question.content,
                difficulty=question.difficulty,
                options=public_options,
                skill_codes=skill_codes,
            )
            for (
                quiz_item,
                question,
                public_options,
                skill_codes,
            ) in prepared_items
        ]

        response = QuizSessionCreateResponse(
            id=quiz_session.id,
            status=quiz_session.status,
            started_at=quiz_session.started_at,
            question_count=len(response_items),
            items=response_items,
        )

        # Save the session and all its items atomically.
        db.commit()

        return response

    except Exception:
        # Do not leave a partially created session behind.
        db.rollback()
        raise
