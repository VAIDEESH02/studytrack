"""Baseline: the students and courses tables exactly as the original create_all hook made them.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "students",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("age", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_students_email", "students", ["email"], unique=True)
    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_name", sa.String(length=160), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.CheckConstraint("credits >= 1 AND credits <= 6", name="credits_between_1_and_6"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_courses_student_id", "courses", ["student_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_courses_student_id", table_name="courses")
    op.drop_table("courses")
    op.drop_index("ix_students_email", table_name="students")
    op.drop_table("students")
