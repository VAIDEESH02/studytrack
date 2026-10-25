"""integrity_error_to_http_error must give the same answers on SQLite and Postgres."""

import pytest
from sqlalchemy.exc import IntegrityError

from backend.main import integrity_error_to_http_error


class FakeDriverError(Exception):
    def __init__(self, message: str, sqlstate: str | None = None):
        super().__init__(message)
        self.sqlstate = sqlstate


class FakeSession:
    rolled_back = False

    def rollback(self):
        self.rolled_back = True


@pytest.mark.parametrize(
    ("message", "sqlstate", "status", "detail"),
    [
        ("UNIQUE constraint failed: students.email", None, 409, "A student with that email already exists"),
        ("UNIQUE constraint failed: users.email", None, 409, "A user with that email already exists"),
        (
            'duplicate key value violates unique constraint "ix_students_email"',
            "23505",
            409,
            "A student with that email already exists",
        ),
        (
            'duplicate key value violates unique constraint "ix_users_email"',
            "23505",
            409,
            "A user with that email already exists",
        ),
        ("FOREIGN KEY constraint failed", None, 422, "student_id must reference an existing student"),
        (
            'insert or update on table "courses" violates foreign key constraint "courses_student_id_fkey"',
            "23503",
            422,
            "student_id must reference an existing student",
        ),
        ("CHECK constraint failed: credits_between_1_and_6", None, 422, "credits must be between 1 and 6"),
        (
            'new row for relation "courses" violates check constraint "credits_between_1_and_6"',
            "23514",
            422,
            "credits must be between 1 and 6",
        ),
        (
            'new row for relation "users" violates check constraint "users_role_valid"',
            "23514",
            422,
            "role must be admin or member",
        ),
        ("NOT NULL constraint failed: students.name", None, 400, "The database rejected this request"),
    ],
)
def test_maps_driver_errors(message, sqlstate, status, detail):
    session = FakeSession()
    error = integrity_error_to_http_error(session, IntegrityError("statement", {}, FakeDriverError(message, sqlstate)))
    assert session.rolled_back
    assert (error.status_code, error.detail) == (status, detail)
