"""Database operations used by the API routes."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models, schemas


def create_student(db: Session, payload: schemas.StudentCreate) -> models.Student:
    student = models.Student(**payload.model_dump())
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


def list_students(db: Session, min_age: int | None = None) -> list[models.Student]:
    statement = select(models.Student).order_by(models.Student.id)
    if min_age is not None:
        statement = statement.where(models.Student.age >= min_age)
    return list(db.scalars(statement))


def get_student(db: Session, student_id: int) -> models.Student | None:
    return db.get(models.Student, student_id)


def update_student(db: Session, student: models.Student, payload: schemas.StudentUpdate) -> models.Student:
    # exclude_none: an explicit null for a required column is ignored rather than hitting NOT NULL.
    for field, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(student, field, value)
    db.commit()
    db.refresh(student)
    return student


def delete_student(db: Session, student: models.Student) -> None:
    db.delete(student)
    db.commit()


def create_course(db: Session, payload: schemas.CourseCreate) -> models.Course:
    course = models.Course(**payload.model_dump())
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def list_courses(db: Session) -> list[models.Course]:
    return list(db.scalars(select(models.Course).order_by(models.Course.id)))


def get_course(db: Session, course_id: int) -> models.Course | None:
    return db.get(models.Course, course_id)


def update_course(db: Session, course: models.Course, payload: schemas.CourseUpdate) -> models.Course:
    for field, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(course, field, value)
    db.commit()
    db.refresh(course)
    return course


def delete_course(db: Session, course: models.Course) -> None:
    db.delete(course)
    db.commit()


def course_count_for_student(db: Session, student_id: int) -> int:
    """Use SQL COUNT(*) in the database rather than loading course rows into Python."""
    statement = select(func.count(models.Course.id)).where(models.Course.student_id == student_id)
    return int(db.scalar(statement) or 0)


def get_user(db: Session, user_id: int) -> models.User | None:
    return db.get(models.User, user_id)


def get_user_by_email(db: Session, email: str) -> models.User | None:
    return db.scalar(select(models.User).where(models.User.email == email.strip().lower()))


def list_users(db: Session) -> list[models.User]:
    return list(db.scalars(select(models.User).order_by(models.User.id)))


def count_users(db: Session) -> int:
    return int(db.scalar(select(func.count(models.User.id))) or 0)


def create_user(db: Session, payload: schemas.UserCreate, password_hash: str) -> models.User:
    user = models.User(
        email=payload.email,
        full_name=payload.full_name,
        role=payload.role,
        password_hash=password_hash,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(
    db: Session, user: models.User, payload: schemas.UserUpdate, password_hash: str | None = None
) -> models.User:
    """Apply admin edits. Role, status, and password changes sign the user out everywhere."""
    revoke_sessions = password_hash is not None
    for field, value in payload.model_dump(exclude_unset=True, exclude_none=True, exclude={"password"}).items():
        if field in {"role", "is_active"} and getattr(user, field) != value:
            revoke_sessions = True
        setattr(user, field, value)
    if password_hash is not None:
        user.password_hash = password_hash
    if revoke_sessions:
        user.token_version += 1
    db.commit()
    db.refresh(user)
    return user


def set_password_hash(db: Session, user: models.User, password_hash: str, *, revoke_sessions: bool) -> models.User:
    user.password_hash = password_hash
    if revoke_sessions:
        user.token_version += 1
    db.commit()
    db.refresh(user)
    return user


def record_login(db: Session, user: models.User) -> models.User:
    user.last_login_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    return user
