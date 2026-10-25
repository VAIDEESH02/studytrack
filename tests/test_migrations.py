import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from backend.database import Base, engine, normalize_database_url, run_migrations


def schema_drift(bind) -> list:
    with bind.connect() as connection:
        return compare_metadata(MigrationContext.configure(connection), Base.metadata)


def revision(bind) -> str:
    with bind.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


@pytest.fixture
def sqlite_engine(tmp_path):
    engines = []

    def make(name: str):
        engines.append(create_engine(f"sqlite:///{tmp_path / name}"))
        return engines[-1]

    yield make
    for created in engines:
        created.dispose()


def test_fresh_database_migrates_to_match_the_models(sqlite_engine):
    fresh = sqlite_engine("fresh.db")
    run_migrations(fresh)
    assert {"students", "courses", "users", "alembic_version"} <= set(inspect(fresh).get_table_names())
    assert schema_drift(fresh) == []
    assert revision(fresh) == "0002_users"
    run_migrations(fresh)  # running again is a no-op
    assert revision(fresh) == "0002_users"


def test_database_from_old_create_all_hook_is_adopted(sqlite_engine):
    legacy = sqlite_engine("legacy.db")
    Base.metadata.create_all(legacy, tables=[Base.metadata.tables["students"], Base.metadata.tables["courses"]])
    with legacy.begin() as connection:
        connection.execute(text("INSERT INTO students (name, email, age) VALUES ('Old', 'old@example.com', 30)"))
    run_migrations(legacy)
    assert "users" in inspect(legacy).get_table_names()
    assert revision(legacy) == "0002_users"
    with legacy.connect() as connection:
        assert connection.execute(text("SELECT name FROM students")).scalar_one() == "Old"


def test_test_database_matches_the_models(password_hashes):
    """In CI's Postgres job this checks the migrations against real Postgres."""
    assert schema_drift(engine) == []


def test_normalize_database_url():
    assert normalize_database_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert (
        normalize_database_url("postgresql://u:p@h/db?sslmode=require")
        == "postgresql+psycopg://u:p@h/db?sslmode=require"
    )
    assert normalize_database_url("postgresql+psycopg://u@h/db") == "postgresql+psycopg://u@h/db"
    assert normalize_database_url("sqlite:///x.db") == "sqlite:///x.db"
