
"""Resource ownership dependencies for TOEIC Tutor.

The authenticated student may access only quiz sessions
belonging to their own account.

Authentication and role checks are delegated to
existing FastAPI dependencies.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.authorization import require_role
from backend.app.api.deps import get_db
from backend.app.db.models import User, QuizSession


def get_owned_quiz_session(
    quiz_session_id: Annotated[
        int,
        Path(
            gt=0,
            description="ID of the requested quiz session",
        ),
    ],
    current_user: Annotated[
        User,
        Depends(require_role("student")),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> QuizSession:
    """Return a quiz session owned by the current student.

    Authentication:
        Requires a valid JWT and an active user.

    Authorization:
        Requires the student role.

    Ownership:
        The quiz session's user_id must equal
        current_user.id.

    Returns:
        An authorized QuizSession ORM instance.

    Raises:
        HTTP 401: Missing or invalid authentication.
        HTTP 403: Authenticated user has wrong role.
        HTTP 404: Quiz missing or owned by another user.
        HTTP 422: Invalid quiz_session_id.

    Security:
        Do not query by quiz_session_id alone.
        Do not trust a user_id supplied by the client.
    """

    stmt = (
        select(QuizSession)
        .where(
            QuizSession.id == quiz_session_id,
            QuizSession.user_id == current_user.id,
        )
    )

    quiz_session = db.scalar(stmt)

    if quiz_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz session not found.",
        )

    return quiz_session
