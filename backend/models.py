"""SQLAlchemy ORM models for trainees, their course enrollments, and app users."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, func, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    age: Mapped[int] = mapped_column(Integer, nullable=False)

    courses: Mapped[list[Course]] = relationship(back_populates="student", cascade="all, delete-orphan")


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (CheckConstraint("credits >= 1 AND credits <= 6", name="credits_between_1_and_6"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_name: Mapped[str] = mapped_column(String(160), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False, index=True)

    student: Mapped[Student] = relationship(back_populates="courses")


class User(Base):
    """Someone allowed to sign in to StudyTrack. There is no self sign-up; admins create users."""

    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('admin', 'member')", name="users_role_valid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="member", server_default="member")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    # Bumped whenever existing sessions must stop working (password, role, or status change).
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
