"""FastAPI routes for the StudyTrack trainee roster."""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import ai_service, algorithms, crud, schemas
from .database import Base, engine, get_db
from .seed_data import seed_database


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("studytrack")

app = FastAPI(title="StudyTrack API", version="1.0.0")

# The local frontend server is deliberately named. Add the deployed Netlify
# origin to ALLOWED_ORIGINS (comma-separated) when deploying the frontend.
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5500").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in allowed_origins if origin.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    seed_database()
    logger.info("StudyTrack backend started and demo data is ready")


def not_found(resource: str, resource_id: int) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{resource} {resource_id} was not found")


def integrity_error_to_http_error(db: Session, error: IntegrityError) -> None:
    db.rollback()
    message = str(error.orig).lower()
    if "unique" in message and "email" in message:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A student with that email already exists")
    if "foreign key" in message:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="student_id must reference an existing student")
    if "credits" in message or "check constraint" in message:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="credits must be between 1 and 6")
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The database rejected this request")


@app.post("/assistant/summarize", response_model=schemas.SummaryRead)
def summarize_study_notes(payload: schemas.SummarizeRequest):
    """Summarize notes with mock mode or the explicitly configured Gemini mode."""
    try:
        return ai_service.summarize_notes(payload.text)
    except ai_service.AIServiceError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error


@app.get("/assistant/search", response_model=list[schemas.NoteSearchResult])
def search_study_notes(query: str = ""):
    """Search the sample notes with mock embeddings and cosine similarity."""
    return ai_service.search_notes(query)


@app.post("/students/", response_model=schemas.StudentRead, status_code=status.HTTP_201_CREATED)
def create_student(payload: schemas.StudentCreate, db: Session = Depends(get_db)):
    try:
        student = crud.create_student(db, payload)
    except IntegrityError as error:
        integrity_error_to_http_error(db, error)
    logger.info("Created student id=%s", student.id)
    return student


@app.get("/students/", response_model=list[schemas.StudentRead])
def read_students(min_age: int | None = None, db: Session = Depends(get_db)):
    return crud.list_students(db, min_age=min_age)


def student_records(db: Session) -> list[dict[str, Any]]:
    """Load live ORM rows and turn them into plain dictionaries for algorithms."""
    return [schemas.StudentRead.model_validate(student).model_dump() for student in crud.list_students(db)]


@app.get("/students/sorted", response_model=list[schemas.StudentRead])
def read_sorted_students(by: str = "age", db: Session = Depends(get_db)):
    if by not in {"age", "name"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="by must be age or name")
    students = student_records(db)
    algorithms.insertion_sort_by_field(students, by)
    return students


@app.get("/students/search", response_model=schemas.StudentRead)
def search_students(name: str, db: Session = Depends(get_db)):
    students = student_records(db)
    sorted_by_name = sorted(students, key=lambda student: student["name"])
    found = algorithms.binary_search_by_name(sorted_by_name, name)
    if found == -1:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Student named {name} was not found")
    return found


@app.get("/students/report")
def read_roster_report(min_age: int = 21, db: Session = Depends(get_db)):
    students = student_records(db)
    return {
        "report": algorithms.format_roster_report(students),
        "count_meeting_min_age": algorithms.count_students_meeting_min_age(students, min_age),
    }


@app.get("/students/{student_id}/course-count", response_model=schemas.CourseCountRead)
def read_course_count(student_id: int, db: Session = Depends(get_db)):
    if crud.get_student(db, student_id) is None:
        raise not_found("Student", student_id)
    return {"student_id": student_id, "course_count": crud.course_count_for_student(db, student_id)}


@app.get("/students/{student_id}", response_model=schemas.StudentRead)
def read_student(student_id: int, db: Session = Depends(get_db)):
    student = crud.get_student(db, student_id)
    if student is None:
        raise not_found("Student", student_id)
    return student


@app.patch("/students/{student_id}", response_model=schemas.StudentRead)
def patch_student(student_id: int, payload: schemas.StudentUpdate, db: Session = Depends(get_db)):
    student = crud.get_student(db, student_id)
    if student is None:
        raise not_found("Student", student_id)
    try:
        updated = crud.update_student(db, student, payload)
    except IntegrityError as error:
        integrity_error_to_http_error(db, error)
    logger.info("Updated student id=%s", student_id)
    return updated


@app.delete("/students/{student_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def remove_student(student_id: int, db: Session = Depends(get_db)):
    student = crud.get_student(db, student_id)
    if student is None:
        raise not_found("Student", student_id)
    crud.delete_student(db, student)
    logger.info("Deleted student id=%s", student_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/courses/", response_model=schemas.CourseRead, status_code=status.HTTP_201_CREATED)
def create_course(payload: schemas.CourseCreate, db: Session = Depends(get_db)):
    try:
        course = crud.create_course(db, payload)
    except IntegrityError as error:
        integrity_error_to_http_error(db, error)
    logger.info("Created course id=%s", course.id)
    return course


@app.get("/courses/", response_model=list[schemas.CourseRead])
def read_courses(db: Session = Depends(get_db)):
    return crud.list_courses(db)


@app.get("/courses/{course_id}", response_model=schemas.CourseRead)
def read_course(course_id: int, db: Session = Depends(get_db)):
    course = crud.get_course(db, course_id)
    if course is None:
        raise not_found("Course", course_id)
    return course


@app.patch("/courses/{course_id}", response_model=schemas.CourseRead)
def patch_course(course_id: int, payload: schemas.CourseUpdate, db: Session = Depends(get_db)):
    course = crud.get_course(db, course_id)
    if course is None:
        raise not_found("Course", course_id)
    try:
        updated = crud.update_course(db, course, payload)
    except IntegrityError as error:
        integrity_error_to_http_error(db, error)
    logger.info("Updated course id=%s", course_id)
    return updated


@app.delete("/courses/{course_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def remove_course(course_id: int, db: Session = Depends(get_db)):
    course = crud.get_course(db, course_id)
    if course is None:
        raise not_found("Course", course_id)
    crud.delete_course(db, course)
    logger.info("Deleted course id=%s", course_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
