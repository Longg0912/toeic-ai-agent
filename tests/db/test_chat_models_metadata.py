"""Metadata tests for AI Tutor chat ORM models."""

from sqlalchemy import CheckConstraint
from sqlalchemy.orm import configure_mappers

from backend.app.db.base import Base
from backend.app.db.models import ChatMessage, ChatSession


def test_chat_tables_registered() -> None:
    """Both chat tables must be registered."""

    expected = {
        "chat_sessions",
        "chat_messages",
    }

    actual = set(Base.metadata.tables.keys())

    assert expected.issubset(actual)


def test_chat_relationships_configured() -> None:
    """SQLAlchemy must configure chat relationships."""

    configure_mappers()

    assert ChatSession.__tablename__ == "chat_sessions"
    assert ChatMessage.__tablename__ == "chat_messages"

    assert ChatSession.messages.property.back_populates == (
        "chat_session"
    )

    assert ChatMessage.chat_session.property.back_populates == (
        "messages"
    )


def test_chat_foreign_keys() -> None:
    """Chat tables must reference their parent tables."""

    expected = {
        "chat_sessions.user_id": "users.id",
        "chat_messages.chat_session_id": "chat_sessions.id",
    }

    for source, destination in expected.items():
        table_name, column_name = source.split(".")

        column = Base.metadata.tables[table_name].c[column_name]

        targets = {
            foreign_key.target_fullname
            for foreign_key in column.foreign_keys
        }

        assert destination in targets


def test_chat_message_check_constraints() -> None:
    """Chat messages must reject invalid roles and empty content."""

    table = Base.metadata.tables["chat_messages"]

    constraint_names = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "ck_chat_messages_role" in constraint_names
    assert "ck_chat_messages_content_not_empty" in constraint_names


def test_chat_indexes_registered() -> None:
    """Chat tables must have indexes for common queries."""

    session_indexes = {
        index.name
        for index in ChatSession.__table__.indexes
    }

    message_indexes = {
        index.name
        for index in ChatMessage.__table__.indexes
    }

    assert "ix_chat_sessions_user_updated_at" in session_indexes
    assert "ix_chat_messages_session_id" in message_indexes