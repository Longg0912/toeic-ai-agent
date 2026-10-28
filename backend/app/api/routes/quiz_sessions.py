
"""API for creating and reviewing TOEIC Part 5 practice sessions."""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from backend.app.api.auth_deps import get_current_user
from backend.app.api.deps import get_db
from backend.app.db.models import (
    Attempt,
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
    QuizSessionDetailItemPublic,
    QuizSessionDetailResponse,
    QuizSessionHistoryItemPublic,
    QuizSessionHistoryListResponse,
    QuizSessionItemPublic,
    QuizSessionSubmitItemPublic,
    QuizSessionSubmitRequest,
    QuizSessionSubmitResponse,
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
                "explanation": question.explanation,
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

@router.post(
    "/quiz-sessions/{session_id}/submit",
    response_model=QuizSessionSubmitResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit and grade a TOEIC Part 5 quiz session",
)
def submit_quiz_session(
    session_id: int,
    payload: QuizSessionSubmitRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> QuizSessionSubmitResponse:
    """Grade a completed set of answers and save the attempts."""

    # 1. Only the owner can access the session.
    # Return 404 for both missing sessions and sessions owned by others.
    quiz_session = db.scalar(
        select(QuizSession)
        .where(
            QuizSession.id == session_id,
            QuizSession.user_id == current_user.id,
        )
        .options(selectinload(QuizSession.items))
    )

    if quiz_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz session not found.",
        )

    # 2. A session can only be submitted once.
    if quiz_session.status != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Quiz session has already been submitted or is not active.",
        )

    # 3. Check that every quiz item has exactly one answer.
    session_items = sorted(
        quiz_session.items,
        key=lambda item: item.position,
    )

    submitted_ids = [
        answer.quiz_item_id
        for answer in payload.answers
    ]

    if len(submitted_ids) != len(set(submitted_ids)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Each quiz item must have exactly one answer.",
        )

    expected_ids = {item.id for item in session_items}

    if set(submitted_ids) != expected_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Submit exactly one answer for every quiz item in this session.",
        )

    answers_by_item_id = {
        answer.quiz_item_id: answer
        for answer in payload.answers
    }

    # 4. Validate options and grade using the frozen answer-key snapshot.
    now = datetime.now(timezone.utc)
    attempts: list[Attempt] = []
    result_items: list[QuizSessionSubmitItemPublic] = []
    correct_count = 0

    for item in session_items:
        answer = answers_by_item_id[item.id]
        snapshot = item.question_snapshot

        snapshot_options = snapshot.get("options", [])
        available_option_keys = {
            option.get("option_key")
            for option in snapshot_options
            if isinstance(option, dict)
        }

        if answer.selected_option_key not in available_option_keys:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Option {answer.selected_option_key} is not available "
                    f"for quiz item {item.id}."
                ),
            )

        # The answer key comes from the server-side snapshot,
        # never from the submitted request or current question record.
        correct_option_key = item.answer_key_snapshot
        is_correct = (
            answer.selected_option_key == correct_option_key
        )

        if is_correct:
            correct_count += 1

        attempts.append(
            Attempt(
                user_id=current_user.id,
                quiz_item_id=item.id,
                attempt_number=1,
                selected_option_key=answer.selected_option_key,
                is_correct=is_correct,
                is_retry=False,
                time_spent_seconds=answer.time_spent_seconds,
                submitted_at=now,
            )
        )

        result_items.append(
            QuizSessionSubmitItemPublic(
                quiz_item_id=item.id,
                question_id=item.question_id,
                position=item.position,
                content=snapshot["content"],
                difficulty=snapshot.get("difficulty"),
                options=snapshot_options,
                skill_codes=snapshot.get("skill_codes", []),
                selected_option_key=answer.selected_option_key,
                correct_option_key=correct_option_key,
                is_correct=is_correct,
                explanation=snapshot.get("explanation"),
            )
        )

    # 5. Calculate the score and prepare the response.
    total_questions = len(session_items)

    response_data = QuizSessionSubmitResponse(
        session_id=quiz_session.id,
        status="submitted",
        finished_at=now,
        total_questions=total_questions,
        answered_count=len(payload.answers),
        correct_count=correct_count,
        accuracy_percent=round(
            correct_count / total_questions * 100,
            2,
        ),
        items=result_items,
    )

    # 6. Save all attempts and update the session in one transaction.
    quiz_session.status = "submitted"
    quiz_session.finished_at = now
    db.add_all(attempts)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Quiz session could not be submitted again.",
        ) from exc

    return response_data


def _build_quiz_session_history_item(
    quiz_session: QuizSession,
) -> QuizSessionHistoryItemPublic:
    """Build a summary without exposing answers before submission."""

    question_count = len(quiz_session.items)

    # The first attempt represents the original submitted answer.
    first_attempts = []
    for item in quiz_session.items:
        attempt = next(
            (
                candidate
                for candidate in item.attempts
                if candidate.attempt_number == 1
            ),
            None,
        )
        if attempt is not None:
            first_attempts.append(attempt)

    answered_count = len(first_attempts)

    if quiz_session.status == "submitted":
        correct_count = sum(
            1 for attempt in first_attempts if attempt.is_correct
        )
        accuracy_percent = (
            round(correct_count / question_count * 100, 2)
            if question_count > 0
            else 0.0
        )
    else:
        # Do not reveal scores for unfinished or abandoned sessions.
        correct_count = None
        accuracy_percent = None

    return QuizSessionHistoryItemPublic(
        id=quiz_session.id,
        status=quiz_session.status,
        started_at=quiz_session.started_at,
        finished_at=quiz_session.finished_at,
        question_count=question_count,
        answered_count=answered_count,
        correct_count=correct_count,
        accuracy_percent=accuracy_percent,
    )


@router.get(
    "/quiz-sessions",
    response_model=QuizSessionHistoryListResponse,
    summary="List the authenticated user's quiz history",
)
def list_quiz_sessions(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> QuizSessionHistoryListResponse:
    """Return a paginated list of the current user's sessions."""

    owner_filter = QuizSession.user_id == current_user.id

    total = db.scalar(
        select(func.count(QuizSession.id)).where(owner_filter)
    ) or 0

    sessions = db.scalars(
        select(QuizSession)
        .where(owner_filter)
        .options(
            selectinload(QuizSession.items).selectinload(
                QuizItem.attempts
            )
        )
        .order_by(
            QuizSession.started_at.desc(),
            QuizSession.id.desc(),
        )
        .offset(offset)
        .limit(limit)
    ).all()

    history_items = [
        _build_quiz_session_history_item(quiz_session)
        for quiz_session in sessions
    ]

    return QuizSessionHistoryListResponse(
        items=history_items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/quiz-sessions/{session_id}",
    response_model=QuizSessionDetailResponse,
    summary="Review one quiz session",
)
def get_quiz_session_detail(
    session_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> QuizSessionDetailResponse:
    """Return session details while protecting unfinished answers."""

    quiz_session = db.scalar(
        select(QuizSession)
        .where(
            QuizSession.id == session_id,
            QuizSession.user_id == current_user.id,
        )
        .options(
            selectinload(QuizSession.items).selectinload(
                QuizItem.attempts
            )
        )
    )

    # Use the same response for a nonexistent session and another
    # user's session, so the endpoint does not disclose ownership.
    if quiz_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz session not found.",
        )

    is_submitted = quiz_session.status == "submitted"
    detail_items = []

    for item in sorted(
        quiz_session.items,
        key=lambda quiz_item: quiz_item.position,
    ):
        snapshot = item.question_snapshot
        options = [
            Part5OptionPublic(**option)
            for option in snapshot.get("options", [])
        ]

        first_attempt = next(
            (
                attempt
                for attempt in item.attempts
                if attempt.attempt_number == 1
            ),
            None,
        )

        if is_submitted:
            selected_option_key = (
                first_attempt.selected_option_key
                if first_attempt is not None
                else None
            )
            correct_option_key = item.answer_key_snapshot
            is_correct = (
                first_attempt.is_correct
                if first_attempt is not None
                else None
            )
            explanation = snapshot.get("explanation")
        else:
            # Never expose the answer key or explanation mid-quiz.
            selected_option_key = None
            correct_option_key = None
            is_correct = None
            explanation = None

        detail_items.append(
            QuizSessionDetailItemPublic(
                quiz_item_id=item.id,
                question_id=item.question_id,
                position=item.position,
                content=snapshot["content"],
                difficulty=snapshot.get("difficulty"),
                options=options,
                skill_codes=snapshot.get("skill_codes", []),
                selected_option_key=selected_option_key,
                correct_option_key=correct_option_key,
                is_correct=is_correct,
                explanation=explanation,
            )
        )

    summary = _build_quiz_session_history_item(quiz_session)

    return QuizSessionDetailResponse(
        **summary.model_dump(),
        items=detail_items,
    )
