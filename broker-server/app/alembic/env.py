import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from core.config import settings
from models.db import Base

# Alembic configuration object (loaded from alembic.ini)
config = context.config

# Set up Python logging based on the config file (if provided)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata: used by Alembic to compare current DB state vs. model definitions
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This mode generates SQL scripts instead of executing them directly.
    It uses a static URL and does not require a real database connection.
    Useful for generating migration SQL for review or execution in restricted environments.
    """
    url = (
        settings.database_url
    )  # Note: Uses synchronous-style URL (e.g., postgresql://...)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,  # Render actual values instead of bind parameters
        dialect_opts={"paramstyle": "named"},  # Use named parameters in generated SQL
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """
    Run migrations using a given synchronous-style SQLAlchemy connection.

    This function is called inside an async-to-sync bridge (via `run_sync`).
    It configures Alembic to use the provided connection and executes the migrations.
    """
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode using an asynchronous database engine.

    Establishes a real async connection to the database and applies migrations.
    Uses NullPool to avoid connection reuse issues during migration runs.
    """
    connectable = create_async_engine(
        settings.async_database_url,  # e.g., postgresql+asyncpg://...
        poolclass=pool.NullPool,  # Avoid pooling since this is a short-lived script
    )

    async with connectable.connect() as connection:
        # Bridge async connection to Alembic's sync-based migration system
        await connection.run_sync(do_run_migrations)

    # Cleanly close all connections in the pool
    await connectable.dispose()


# Entry point: decide whether to run in offline or online mode
if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
