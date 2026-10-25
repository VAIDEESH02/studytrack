"""Shared fixtures.

Tests never use DATABASE_URL from your shell, so they cannot touch a real database. They use
TEST_DATABASE_URL when it is set (CI's throwaway Postgres) and a fresh temporary SQLite file
otherwise. These environment variables must be set before ``backend`` is imported.
"""

import os
import tempfile
from pathlib import Path

_TEST_DB_DIR = Path(tempfile.mkdtemp(prefix="studytrack-tests-"))
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_TEST_DB_DIR / 'test.db'}"
os.environ["SECRET_KEY"] = "test-only-secret-key-" + "x" * 40
os.environ["ENVIRONMENT"] = "test"
os.environ["AI_MODE"] = "mock"
for _name in (
    "BOOTSTRAP_ADMIN_EMAIL",
    "BOOTSTRAP_ADMIN_PASSWORD",
    "COOKIE_SECURE",
    "ENABLE_DOCS",
    "GOOGLE_API_KEY",
    "PROXY_SIGNING_SECRET",
    "RENDER_GIT_COMMIT",
    "SEED_DEMO_DATA",
    "SESSION_HOURS",
):
    os.environ.pop(_name, None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from backend import auth  # noqa: E402
from backend.database import SessionLocal, engine, run_migrations  # noqa: E402
from backend.main import app  # noqa: E402
from backend.models import Course, Student, User  # noqa: E402
from backend.seed_data import seed_if_empty  # noqa: E402

ADMIN_EMAIL = "admin@studytrack.test"
ADMIN_PASSWORD = "admin-password-123"
MEMBER_EMAIL = "member@studytrack.test"
MEMBER_PASSWORD = "member-password-123"


@pytest.fixture(scope="session")
def password_hashes():
    """Migrate the test database once and hash the fixture passwords once (Argon2 is slow by design)."""
    run_migrations()
    yield {
        ADMIN_EMAIL: auth.hash_password(ADMIN_PASSWORD),
        MEMBER_EMAIL: auth.hash_password(MEMBER_PASSWORD),
    }
    engine.dispose()


@pytest.fixture
def db_state(password_hashes):
    """Reset to the demo roster plus one admin and one member before each test."""
    with SessionLocal() as db:
        db.execute(delete(Course))
        db.execute(delete(Student))
        db.execute(delete(User))
        db.commit()
        seed_if_empty(db)
        db.add_all(
            [
                User(
                    email=ADMIN_EMAIL, full_name="Ada Admin", role="admin", password_hash=password_hashes[ADMIN_EMAIL]
                ),
                User(
                    email=MEMBER_EMAIL,
                    full_name="Max Member",
                    role="member",
                    password_hash=password_hashes[MEMBER_EMAIL],
                ),
            ]
        )
        db.commit()
    auth.login_throttle.clear()
    yield


@pytest.fixture
def db(db_state):
    with SessionLocal() as session:
        yield session


def sign_in(client: TestClient, email: str, password: str) -> TestClient:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return client


@pytest.fixture
def anon_client(db_state):
    return TestClient(app)


@pytest.fixture
def admin_client(db_state):
    return sign_in(TestClient(app), ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture
def member_client(db_state):
    return sign_in(TestClient(app), MEMBER_EMAIL, MEMBER_PASSWORD)


@pytest.fixture
def client(member_client):
    """Any signed-in user. Roster and course routes do not need the admin role."""
    return member_client


def find_by_name(client: TestClient, name: str) -> dict:
    return next(student for student in client.get("/students/").json() if student["name"] == name)
