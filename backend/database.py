"""Database configuration, schema migrations, and the FastAPI session dependency."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_DATABASE_PATH = BACKEND_DIR / "studytrack.db"
MIGRATIONS_DIR = BACKEND_DIR / "migrations"
BASELINE_REVISION = "0001_baseline"


def normalize_database_url(url: str) -> str:
    """Point plain Postgres URLs, as Neon and Render print them, at the psycopg 3 driver."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url.removeprefix(prefix)
    return url


DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL") or f"sqlite:///{DEFAULT_DATABASE_PATH}")
IS_SQLITE = DATABASE_URL.startswith("sqlite")


class Base(DeclarativeBase):
    """Base class for all ORM models."""


if IS_SQLITE:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # Hosted Postgres (Neon) closes idle connections, so test them before use and recycle them.
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)


@event.listens_for(engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
    """Make SQLite enforce the Course.student_id foreign key."""
    if IS_SQLITE:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session]:
    """Open a request-scoped session and always close it after the route returns."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations(bind: Engine = engine) -> None:
    """Upgrade the schema to the latest Alembic revision.

    Databases created by the old ``create_all`` startup hook already have the baseline tables
    but no ``alembic_version`` table, so they are stamped at the baseline instead of failing.
    """
    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    with bind.begin() as connection:
        config.attributes["connection"] = connection
        tables = set(inspect(connection).get_table_names())
        if "alembic_version" not in tables and "students" in tables:
            command.stamp(config, BASELINE_REVISION)
        command.upgrade(config, "head")
