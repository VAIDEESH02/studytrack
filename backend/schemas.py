"""Pydantic request and response contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StudentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=1, max_length=255)
    age: int = Field(gt=0)

    @field_validator("email")
    @classmethod
    def email_must_contain_at_sign(cls, value: str) -> str:
        if "@" not in value:
            raise ValueError("email must contain an @ character")
        return value


class StudentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = Field(default=None, min_length=1, max_length=255)
    age: int | None = Field(default=None, gt=0)

    @field_validator("email")
    @classmethod
    def email_must_contain_at_sign(cls, value: str | None) -> str | None:
        if value is not None and "@" not in value:
            raise ValueError("email must contain an @ character")
        return value


class StudentRead(BaseModel):
    id: int
    name: str
    email: str
    age: int

    model_config = ConfigDict(from_attributes=True)


class CourseCreate(BaseModel):
    course_name: str = Field(min_length=1, max_length=160)
    credits: int = Field(ge=1, le=6)
    student_id: int = Field(gt=0)


class CourseUpdate(BaseModel):
    course_name: str | None = Field(default=None, min_length=1, max_length=160)
    credits: int | None = Field(default=None, ge=1, le=6)
    student_id: int | None = Field(default=None, gt=0)


class CourseRead(BaseModel):
    id: int
    course_name: str
    credits: int
    student_id: int

    model_config = ConfigDict(from_attributes=True)


class CourseCountRead(BaseModel):
    student_id: int
    course_count: int


class MessageRead(BaseModel):
    detail: str


class SummarizeRequest(BaseModel):
    text: str


class SummaryRead(BaseModel):
    topic: str
    key_points: list[str]
    difficulty: str


class NoteSearchResult(BaseModel):
    id: int
    text: str
    score: float
