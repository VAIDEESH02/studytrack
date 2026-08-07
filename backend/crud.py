"""Database operations used by the API routes."""

from __future__ import annotations

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


def update_student(
    db: Session, student: models.Student, payload: schemas.StudentUpdate
) -> models.Student:
    for field, value in payload.model_dump(exclude_unset=True).items():
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


def update_course(
    db: Session, course: models.Course, payload: schemas.CourseUpdate
) -> models.Course:
    for field, value in payload.model_dump(exclude_unset=True).items():
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
