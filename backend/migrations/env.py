"""Alembic environment. Reuses the app's engine so DATABASE_URL is the only database setting."""

from logging.config import fileConfig

from alembic import context

from backend import models  # noqa: F401  (imports register every table on Base.metadata)
from backend.database import Base, engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _configure_and_run(connection) -> None:
    # Batch mode lets future ALTERs work on SQLite, which cannot alter most constraints in place.
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=engine.url.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # backend.database.run_migrations() passes its own open connection; the CLI does not.
    connection = config.attributes.get("connection")
    if connection is not None:
        _configure_and_run(connection)
        return
    with engine.connect() as new_connection:
        _configure_and_run(new_connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
