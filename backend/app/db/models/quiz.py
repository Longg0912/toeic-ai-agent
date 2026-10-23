"""ORM models for TOEIC quiz sessions and attempts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base
from backend.app.db.models.core import Question, User


class QuizSession(Base):
    """A TOEIC practice session owned by one user."""

    __tablename__ = "quiz_sessions"

    __table_args__ = (
        CheckConstraint(
            "status IN ('in_progress', 'submitted', 'abandoned')",
            name="ck_quiz_sessions_status",
        ),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ck_quiz_sessions_finished_at",
        ),
        Index(
            "ix_quiz_sessions_user_started",
            "user_id",
            "started_at",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'in_progress'"),
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )

    user: Mapped[User] = relationship("User")

    items: Mapped[list[QuizItem]] = relationship(
        back_populates="session",
        passive_deletes=True,
    )


class QuizItem(Base):
    """Frozen question assigned to a specific quiz session."""

    __tablename__ = "quiz_items"

    __table_args__ = (
        UniqueConstraint(
            "quiz_session_id",
            "position",
            name="uq_quiz_items_session_position",
        ),
        UniqueConstraint(
            "quiz_session_id",
            "question_id",
            name="uq_quiz_items_session_question",
        ),
        CheckConstraint(
            "position >= 1",
            name="ck_quiz_items_position",
        ),
        CheckConstraint(
            "answer_key_snapshot IN ('A', 'B', 'C', 'D')",
            name="ck_quiz_items_answer_key",
        ),
        Index(
            "ix_quiz_items_question_id",
            "question_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    quiz_session_id: Mapped[int] = mapped_column(
        ForeignKey(
            "quiz_sessions.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    question_id: Mapped[int] = mapped_column(
        ForeignKey(
            "questions.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    question_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )

    answer_key_snapshot: Mapped[str] = mapped_column(
        String(1),
        nullable=False,
    )

    session: Mapped[QuizSession] = relationship(
        back_populates="items",
    )

    question: Mapped[Question] = relationship("Question")

    attempts: Mapped[list[Attempt]] = relationship(
        back_populates="quiz_item",
        passive_deletes=True,
    )


class Attempt(Base):
    """One submitted answer for an assigned quiz item."""

    __tablename__ = "attempts"

    __table_args__ = (
        UniqueConstraint(
            "quiz_item_id",
            "attempt_number",
            name="uq_attempts_item_number",
        ),
        CheckConstraint(
            "attempt_number >= 1",
            name="ck_attempts_number",
        ),
        CheckConstraint(
            "selected_option_key IN ('A', 'B', 'C', 'D')",
            name="ck_attempts_selected_option",
        ),
        CheckConstraint(
            "time_spent_seconds IS NULL OR time_spent_seconds >= 0",
            name="ck_attempts_time_spent",
        ),
        Index(
            "ix_attempts_user_submitted",
            "user_id",
            "submitted_at",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    quiz_item_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_items.id", ondelete="RESTRICT"),
        nullable=False,
    )

    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    selected_option_key: Mapped[str] = mapped_column(
        String(1),
        nullable=False,
    )

    is_correct: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )

    is_retry: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("0"),
    )

    time_spent_seconds: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    user: Mapped[User] = relationship("User")

    quiz_item: Mapped[QuizItem] = relationship(
        back_populates="attempts",
    )