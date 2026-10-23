"""Database engine and session configuration."""

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


# D:/toeic-ai-agent
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Load local configuration when it exists.
# Existing environment variables have priority.
load_dotenv(PROJECT_ROOT / ".env", override=False)

# Default SQLite location.
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "toeic.sqlite3"

DEFAULT_DATABASE_URL = (
    f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"
)

DATABASE_URL = (
    os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL
)


def make_engine(database_url: str) -> Engine:
    """Create an SQLite engine with foreign-key enforcement."""

    parsed_url = make_url(database_url)

    if parsed_url.get_backend_name() != "sqlite":
        raise ValueError(
            "This project currently supports SQLite only."
        )

    engine_options: dict[str, Any] = {
        "connect_args": {
            "check_same_thread": False,
        },
        "pool_pre_ping": True,
    }

    if parsed_url.database == ":memory:":
        engine_options["poolclass"] = StaticPool

    db_engine = create_engine(
        database_url,
        **engine_options,
    )

    @event.listens_for(db_engine, "connect")
    def enable_foreign_keys(
        dbapi_connection: Any,
        _connection_record: Any,
    ) -> None:
        """Enable SQLite foreign-key checks per connection."""

        cursor = dbapi_connection.cursor()

        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    return db_engine


# Creating an Engine does not create database tables.
engine = make_engine(DATABASE_URL)


# Factory for SQLAlchemy sessions.
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Iterator[Session]:
    """Yield a database session and close it afterward."""

    with SessionLocal() as db:
        yield db