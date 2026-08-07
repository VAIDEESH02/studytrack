"""Deterministic StudyTrack demonstration data and a small seeding CLI."""

from __future__ import annotations

import argparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine
from .models import Course, Student


SEED_STUDENTS = [
    {"name": "Aditi Rao", "email": "aditi.rao@example.com", "age": 22},
    {"name": "Rohan Mehta", "email": "rohan.mehta@example.com", "age": 19},
    {"name": "Kavya Nair", "email": "kavya.nair@example.com", "age": 25},
    {"name": "Farhan Sheikh", "email": "farhan.sheikh@example.com", "age": 18},
    {"name": "Priya Iyer", "email": "priya.iyer@example.com", "age": 21},
    {"name": "Devansh Gupta", "email": "devansh.gupta@example.com", "age": 23},
    {"name": "Meera Joshi", "email": "meera.joshi@example.com", "age": 20},
    {"name": "Sameer Khan", "email": "sameer.khan@example.com", "age": 24},
]

COURSES = [
    {"course_name": "Retail Foundations", "credits": 3, "email": "aditi.rao@example.com"},
    {"course_name": "Data Literacy", "credits": 2, "email": "aditi.rao@example.com"},
    {"course_name": "Fashion Commerce", "credits": 4, "email": "priya.iyer@example.com"},
    {"course_name": "Customer Experience", "credits": 3, "email": "kavya.nair@example.com"},
]


def seed_if_empty(db: Session) -> None:
    """Insert the required roster only when the Student table has no records."""
    if db.scalar(select(Student.id).limit(1)) is not None:
        return
    students = [Student(**student) for student in SEED_STUDENTS]
    db.add_all(students)
    db.flush()
    by_email = {student.email: student for student in students}
    db.add_all(
        [
            Course(
                course_name=course["course_name"],
                credits=course["credits"],
                student_id=by_email[course["email"]].id,
            )
            for course in COURSES
        ]
    )
    db.commit()


def seed_database(reset: bool = False) -> None:
    """Create tables and seed once; reset makes the documented demo repeatable."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if reset:
            db.query(Course).delete()
            db.query(Student).delete()
            db.commit()
        seed_if_empty(db)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the StudyTrack SQLite database.")
    parser.add_argument("--reset", action="store_true", help="replace existing local demo data")
    args = parser.parse_args()
    seed_database(reset=args.reset)
    print("StudyTrack database seeded.")
