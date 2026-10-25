"""Pydantic request and response contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

# Postgres INTEGER columns stop at 2**31 - 1; larger ids or ages would raise a driver error.
MAX_INT = 2_147_483_647
MAX_NOTE_CHARACTERS = 20_000
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128

Role = Literal["admin", "member"]
Difficulty = Literal["easy", "medium", "hard"]
DbId = Annotated[int, Field(gt=0, le=MAX_INT)]


def _require_at_sign(value: str) -> str:
    if "@" not in value:
        raise ValueError("email must contain an @ character")
    return value


def _normalize_email(value: str) -> str:
    return _require_at_sign(value).lower()


StudentEmail = Annotated[str, Field(min_length=1, max_length=255), AfterValidator(_require_at_sign)]
UserEmail = Annotated[str, Field(min_length=3, max_length=255), AfterValidator(_normalize_email)]


class StudentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    email: StudentEmail
    age: int = Field(gt=0, le=150)


class StudentUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: StudentEmail | None = None
    age: int | None = Field(default=None, gt=0, le=150)


class StudentRead(BaseModel):
    id: int
    name: str
    email: str
    age: int

    model_config = ConfigDict(from_attributes=True)


class CourseCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    course_name: str = Field(min_length=1, max_length=160)
    credits: int = Field(ge=1, le=6)
    student_id: DbId


class CourseUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    course_name: str | None = Field(default=None, min_length=1, max_length=160)
    credits: int | None = Field(default=None, ge=1, le=6)
    student_id: DbId | None = None


class CourseRead(BaseModel):
    id: int
    course_name: str
    credits: int
    student_id: int

    model_config = ConfigDict(from_attributes=True)


class CourseCountRead(BaseModel):
    student_id: int
    course_count: int


class RosterReportRead(BaseModel):
    report: str
    count_meeting_min_age: int


class MessageRead(BaseModel):
    detail: str


class HealthRead(BaseModel):
    status: Literal["ok"]
    version: str


class SummarizeRequest(BaseModel):
    text: str = Field(max_length=MAX_NOTE_CHARACTERS)


class SummaryRead(BaseModel):
    topic: str
    key_points: list[str]
    difficulty: Difficulty


class NoteSearchResult(BaseModel):
    id: int
    text: str
    score: float


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class UserRead(BaseModel):
    id: int
    email: str
    full_name: str
    role: Role
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("created_at", "last_login_at")
    @classmethod
    def assume_utc(cls, value: datetime | None) -> datetime | None:
        # SQLite drops timezone info; every timestamp StudyTrack stores is UTC.
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class UserCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: UserEmail
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    role: Role = "member"


class UserUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
