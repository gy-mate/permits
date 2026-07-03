"""Alembic async migration environment."""

import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from permits.config import get_settings
from permits.models import Base

config = context.config
target_metadata = Base.metadata


def run_migrations(connection) -> None:
    # The alembic_version table stays in the default (public) schema so it does not
    # depend on the "permits" schema the first migration creates.
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async() -> None:
    engine = create_async_engine(get_settings().database_url)

    async with engine.connect() as connection:
        await connection.run_sync(run_migrations)

    await engine.dispose()


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async())
