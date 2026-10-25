import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from backend import auth, main
from backend.database import SessionLocal
from backend.main import app
from backend.models import Course, Student, User
from backend.seed_data import SEED_STUDENTS, seed_database


def clear(*models):
    with SessionLocal() as db:
        for model in models:
            db.execute(delete(model))
        db.commit()


def count(model) -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(model))


@pytest.fixture
def bootstrap_env(monkeypatch):
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "Owner@StudyTrack.test")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "owner-password-123")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_NAME", "Olive Owner")


def test_startup_migrates_bootstraps_admin_and_seeds(db_state, bootstrap_env):
    clear(Course, Student, User)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        response = client.post("/auth/login", json={"email": "owner@studytrack.test", "password": "owner-password-123"})
        assert response.status_code == 200
        assert response.json()["full_name"] == "Olive Owner"
        assert response.json()["role"] == "admin"
        assert len(client.get("/students/").json()) == len(SEED_STUDENTS)


def test_bootstrap_is_skipped_once_any_user_exists(db_state, bootstrap_env):
    with SessionLocal() as db:
        assert auth.bootstrap_admin_from_env(db) is None
    assert count(User) == 2


def test_bootstrap_without_settings_only_warns(db_state, caplog):
    clear(User)
    with caplog.at_level(logging.WARNING, logger="studytrack"), SessionLocal() as db:
        assert auth.bootstrap_admin_from_env(db) is None
    assert "BOOTSTRAP_ADMIN_EMAIL" in caplog.text


def test_bootstrap_rejects_a_weak_password(db_state, bootstrap_env, monkeypatch):
    clear(User)
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "short")
    with SessionLocal() as db, pytest.raises(RuntimeError, match="password"):
        auth.bootstrap_admin_from_env(db)


def test_demo_seeding_can_be_disabled(db_state, monkeypatch):
    clear(Course, Student)
    monkeypatch.setenv("SEED_DEMO_DATA", "false")
    main.prepare_database()
    assert count(Student) == 0


def test_seed_reset_restores_roster_and_keeps_users(db_state):
    clear(Course, Student)
    seed_database(reset=True)
    assert count(Student) == len(SEED_STUDENTS)
    assert count(Course) == 4
    assert count(User) == 2


def test_docs_are_hidden_in_production_unless_enabled(monkeypatch):
    assert main.docs_enabled()
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert not main.docs_enabled()
    monkeypatch.setenv("ENABLE_DOCS", "true")
    assert main.docs_enabled()
