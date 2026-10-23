"""Alembic migration environment for TOEIC Tutor Agent."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from backend.app.db.base import Base
from backend.app.db.session import DATABASE_URL, make_engine

# Import ORM models so they register with Base.metadata.
import backend.app.db.models  # noqa: F401


# Alembic configuration object
config = context.config


# Configure logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# Metadata containing all registered ORM tables
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate SQL migration commands without DB connection."""

    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Execute migrations using an existing connection."""

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Execute migrations using the configured SQLite database."""

    # Allow tests to inject their own database connection.
    existing_connection = config.attributes.get("connection")

    if existing_connection is not None:
        do_run_migrations(existing_connection)
        return

    # Use the same database configuration as SQLAlchemy.
    migration_engine = make_engine(DATABASE_URL)

    try:
        with migration_engine.connect() as connection:
            do_run_migrations(connection)
    finally:
        migration_engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()