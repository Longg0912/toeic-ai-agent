"""API endpoints for multi-turn TOEIC Tutor conversations."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.auth_deps import get_current_user
from backend.app.api.deps import get_db
from backend.app.db.models import ChatMessage, ChatSession, User
from backend.app.schemas.tutor import (
    TutorChatMessagePublic,
    TutorChatRequest,
    TutorChatResponse,
    TutorChatSessionDetailResponse,
    TutorChatSessionListResponse,
    TutorChatSessionSummary,
)
from backend.app.services.gemini_tutor import (
    GeminiConfigurationError,
    GeminiServiceError,
    chat_with_tutor,
)


router = APIRouter(
    prefix="/tutor",
    tags=["AI Tutor"],
)

# Tối đa 20 tin nhắn được gửi cho Gemini trong một lượt gọi.
MAX_CONTEXT_MESSAGES = 20

# Số tin nhắn cũ tối đa cần lấy, dành một vị trí cho tin nhắn mới.
MAX_HISTORY_MESSAGES = MAX_CONTEXT_MESSAGES - 1


def _make_session_title(message: str) -> str:
    """Create a short title from the first user message."""

    normalized = " ".join(message.split())

    if len(normalized) <= 150:
        return normalized

    return normalized[:147].rstrip() + "..."


def _public_message(
    message: ChatMessage,
) -> TutorChatMessagePublic:
    """Convert a database message into a public response schema."""

    return TutorChatMessagePublic(
        id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
    )


@router.post(
    "/chat",
    response_model=TutorChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Send a message to the TOEIC AI Tutor",
)
def send_chat_message(
    request_data: TutorChatRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TutorChatResponse:
    """Send a message and save the user/assistant message pair.

    A new chat session is created when chat_session_id is omitted.
    Existing sessions can only be accessed by their owner.
    """

    chat_session: ChatSession | None = None
    history: list[ChatMessage] = []

    # 1. Load an existing session, if the client provided its ID.
    if request_data.chat_session_id is not None:
        chat_session = db.scalar(
            select(ChatSession).where(
                ChatSession.id == request_data.chat_session_id,
                ChatSession.user_id == current_user.id,
            )
        )

        # Do not reveal whether a session belongs to another user.
        if chat_session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session not found.",
            )

        # 2. Retrieve the latest messages in chronological order.
        history = list(
            db.scalars(
                select(ChatMessage)
                .where(
                    ChatMessage.chat_session_id == chat_session.id
                )
                .order_by(ChatMessage.id.desc())
                .limit(MAX_HISTORY_MESSAGES)
            ).all()
        )

        history.reverse()

    # 3. Build the conversation context for Gemini.
    conversation = [
        {
            "role": message.role,
            "content": message.content,
        }
        for message in history
    ]

    conversation.append(
        {
            "role": "user",
            "content": request_data.message,
        }
    )

    # 4. Call Gemini before writing messages to the database.
    # If Gemini fails, no incomplete message pair is saved.
    try:
        assistant_content = chat_with_tutor(
            conversation,
            db=db,
            student_id=current_user.id,
        )

    except GeminiConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI Tutor service is not configured.",
        ) from None

    except GeminiServiceError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI Tutor could not generate a response.",
        ) from None

    # 5. Create a new session only after Gemini responds successfully.
    if chat_session is None:
        chat_session = ChatSession(
            user_id=current_user.id,
            title=_make_session_title(request_data.message),
        )
        db.add(chat_session)
        db.flush()

    # 6. Save both messages as one transaction.
    user_message = ChatMessage(
        chat_session_id=chat_session.id,
        role="user",
        content=request_data.message,
    )

    assistant_message = ChatMessage(
        chat_session_id=chat_session.id,
        role="assistant",
        content=assistant_content,
    )

    chat_session.updated_at = func.current_timestamp()

    db.add_all(
        [
            user_message,
            assistant_message,
        ]
    )

    db.commit()

    # 7. Reload database-generated IDs and timestamps.
    db.refresh(chat_session)
    db.refresh(user_message)
    db.refresh(assistant_message)

    return TutorChatResponse(
        chat_session_id=chat_session.id,
        title=chat_session.title,
        user_message=_public_message(user_message),
        assistant_message=_public_message(assistant_message),
    )


@router.get(
    "/sessions",
    response_model=TutorChatSessionListResponse,
    summary="List the current user's Tutor chat sessions",
)
def list_chat_sessions(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TutorChatSessionListResponse:
    """Return a paginated list of sessions owned by the current user."""

    owner_filter = ChatSession.user_id == current_user.id

    total = db.scalar(
        select(func.count(ChatSession.id)).where(owner_filter)
    ) or 0

    message_count = (
        select(func.count(ChatMessage.id))
        .where(
            ChatMessage.chat_session_id == ChatSession.id
        )
        .correlate(ChatSession)
        .scalar_subquery()
    )

    statement = (
        select(
            ChatSession,
            message_count.label("message_count"),
        )
        .where(owner_filter)
        .order_by(
            ChatSession.updated_at.desc(),
            ChatSession.id.desc(),
        )
        .offset(offset)
        .limit(limit)
    )

    rows = db.execute(statement).all()

    items = [
        TutorChatSessionSummary(
            id=session.id,
            title=session.title,
            created_at=session.created_at,
            updated_at=session.updated_at,
            message_count=count,
        )
        for session, count in rows
    ]

    return TutorChatSessionListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/sessions/{session_id}",
    response_model=TutorChatSessionDetailResponse,
    summary="Get one Tutor chat session and its messages",
)
def get_chat_session(
    session_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TutorChatSessionDetailResponse:
    """Return a session and its messages if the current user owns it."""

    chat_session = db.scalar(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )

    if chat_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found.",
        )

    messages = db.scalars(
        select(ChatMessage)
        .where(
            ChatMessage.chat_session_id == chat_session.id
        )
        .order_by(ChatMessage.id)
    ).all()

    return TutorChatSessionDetailResponse(
        id=chat_session.id,
        title=chat_session.title,
        created_at=chat_session.created_at,
        updated_at=chat_session.updated_at,
        messages=[
            _public_message(message)
            for message in messages
        ],
    )