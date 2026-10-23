
"""Reusable FastAPI dependencies."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Provide a database session for one API request.

    The session is automatically closed after use.
    Registration Service handles commit and rollback.
    """

    with SessionLocal() as session:
        yield session
