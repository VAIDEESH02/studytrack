"""FastAPI routes for the StudyTrack trainee roster.

Routes are grouped into three routers in this file:

* ``public``: health check, sign in, sign out. The only routes reachable without a session.
* ``protected``: everything else. The router-level ``current_user`` dependency answers 401
  before any route code runs, so new routes are protected by default.
* ``admin``: user management, which additionally requires the admin role.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import ai_service, algorithms, auth, crud, edge, models, schemas
from .database import SessionLocal, get_db, run_migrations
from .seed_data import seed_if_empty

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("studytrack")
logging.getLogger("alembic.runtime.plugins").setLevel(logging.WARNING)  # keep "Running upgrade" lines only

IdPath = Annotated[int, Path(gt=0, le=schemas.MAX_INT)]
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[models.User, Depends(auth.current_user)]
CurrentAdmin = Annotated[models.User, Depends(auth.require_admin)]


def docs_enabled() -> bool:
    """Interactive API docs are on locally and off in production unless ENABLE_DOCS=true."""
    return not auth.is_production() or os.getenv("ENABLE_DOCS", "").strip().lower() == "true"


def seed_demo_data_enabled() -> bool:
    return os.getenv("SEED_DEMO_DATA", "true").strip().lower() in {"1", "true", "yes", "on"}


def prepare_database() -> None:
    """Migrate the schema, create the first admin if needed, and seed the demo roster."""
    run_migrations()
    with SessionLocal() as db:
        auth.bootstrap_admin_from_env(db)
        if seed_demo_data_enabled():
            seed_if_empty(db)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    auth.check_settings()
    prepare_database()
    logger.info("StudyTrack backend started and the database is ready")
    yield


app = FastAPI(
    title="StudyTrack API",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if docs_enabled() else None,
    redoc_url="/redoc" if docs_enabled() else None,
    openapi_url="/openapi.json" if docs_enabled() else None,
)

# Local development calls the API cross-origin (port 5500 to 8000). In production the browser
# goes through the Netlify /api proxy, so it is same-origin; the deployed Netlify origin is
# still listed in ALLOWED_ORIGINS. Origins are always named, never "*".
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in allowed_origins if origin.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)
# Starlette runs the last-added middleware first, so a request passes through security headers,
# then the Netlify origin lock, then the body-size cap, then CORS, before reaching any route.
app.add_middleware(edge.BodySizeLimitMiddleware)
app.add_middleware(edge.ProxySignatureMiddleware)
app.add_middleware(edge.SecurityHeadersMiddleware)

# Annotated with FastAPI's own `responses` type: dict keys are invariant, so an inferred
# dict[int, ...] would not type-check against dict[int | str, ...].
OpenAPIResponses = dict[int | str, dict[str, Any]]
UNAUTHORIZED_RESPONSE: OpenAPIResponses = {401: {"model": schemas.MessageRead, "description": "Not signed in"}}
FORBIDDEN_RESPONSE: OpenAPIResponses = {
    403: {"model": schemas.MessageRead, "description": "Administrator access is required"}
}

public = APIRouter()
protected = APIRouter(dependencies=[Depends(auth.current_user)], responses=UNAUTHORIZED_RESPONSE)
admin = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(auth.require_admin)],
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE},
)


def not_found(resource: str, resource_id: int) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{resource} {resource_id} was not found")


def integrity_error_to_http_error(db: Session, error: IntegrityError) -> HTTPException:
    """Translate a database constraint failure into the matching HTTP error.

    Postgres (psycopg) exposes a SQLSTATE code; SQLite only has message text, so both are checked.
    Callers ``raise integrity_error_to_http_error(db, error) from error``.
    """
    db.rollback()
    sqlstate = getattr(error.orig, "sqlstate", None)
    message = str(error.orig).lower()
    if sqlstate == "23505" or "unique" in message:
        if "users" in message:
            return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A user with that email already exists")
        if "email" in message:
            return HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="A student with that email already exists"
            )
    if sqlstate == "23503" or "foreign key" in message:
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="student_id must reference an existing student"
        )
    if sqlstate == "23514" or "check constraint" in message:
        if "role" in message:
            return HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="role must be admin or member"
            )
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="credits must be between 1 and 6"
        )
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The database rejected this request")


# --- Public: health and session -------------------------------------------------------------


@public.get("/health", response_model=schemas.HealthRead, tags=["health"])
def health():
    """Liveness check for Render and the frontend's wake-up ping. Reports the deployed commit."""
    return {"status": "ok", "version": os.getenv("RENDER_GIT_COMMIT", "dev")}


@public.post(
    "/auth/login",
    response_model=schemas.UserRead,
    tags=["session"],
    responses={401: {"model": schemas.MessageRead}, 429: {"model": schemas.MessageRead}},
)
def login(payload: schemas.LoginRequest, request: Request, response: Response, db: DbSession):
    """Check credentials and set the HttpOnly session cookie."""
    # Logged so repeated attempts are visible in Render's logs. Emails are never logged.
    client_ip = edge.trusted_client_ip(request) or "an unverified address"
    wait_seconds = auth.login_throttle.retry_after(payload.email)
    if wait_seconds:
        minutes = max(1, round(wait_seconds / 60))
        logger.warning("Rejected sign-in for a locked-out email from %s", client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed sign-in attempts. Try again in about {minutes} minute(s).",
            headers={"Retry-After": str(wait_seconds)},
        )
    user = auth.authenticate(db, payload.email, payload.password)
    if user is None:
        auth.login_throttle.record_failure(payload.email)
        logger.info("Failed sign-in attempt from %s", client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    auth.login_throttle.reset(payload.email)
    crud.record_login(db, user)
    auth.set_session_cookie(response, user)
    logger.info("Signed in user id=%s", user.id)
    return user


@public.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, tags=["session"])
def logout():
    """Clear the session cookie. Safe to call when already signed out."""
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    auth.clear_session_cookie(response)
    logger.info("Signed out a session")
    return response


# --- Signed-in users ------------------------------------------------------------------------


@protected.get("/auth/me", response_model=schemas.UserRead, tags=["session"])
def read_current_user(user: CurrentUser):
    return user


@protected.post(
    "/auth/change-password", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, tags=["session"]
)
def change_password(payload: schemas.PasswordChange, user: CurrentUser, db: DbSession):
    """Change your own password. Other sessions are signed out; this one gets a fresh cookie."""
    if not auth.verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    if payload.new_password == payload.current_password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="New password must differ from the current one"
        )
    crud.set_password_hash(db, user, auth.hash_password(payload.new_password), revoke_sessions=True)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    auth.set_session_cookie(response, user)
    logger.info("Changed password for user id=%s", user.id)
    return response


@protected.post("/assistant/summarize", response_model=schemas.SummaryRead, tags=["assistant"])
def summarize_study_notes(payload: schemas.SummarizeRequest):
    """Summarize notes with mock mode or the explicitly configured Gemini mode."""
    try:
        return ai_service.summarize_notes(payload.text)
    except ai_service.AIServiceError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error


@protected.get("/assistant/search", response_model=list[schemas.NoteSearchResult], tags=["assistant"])
def search_study_notes(query: str = ""):
    """Search the sample notes with mock embeddings and cosine similarity."""
    return ai_service.search_notes(query)


@protected.post(
    "/students/", response_model=schemas.StudentRead, status_code=status.HTTP_201_CREATED, tags=["students"]
)
def create_student(payload: schemas.StudentCreate, db: DbSession):
    try:
        student = crud.create_student(db, payload)
    except IntegrityError as error:
        raise integrity_error_to_http_error(db, error) from error
    logger.info("Created student id=%s", student.id)
    return student


@protected.get("/students/", response_model=list[schemas.StudentRead], tags=["students"])
def read_students(db: DbSession, min_age: int | None = None):
    return crud.list_students(db, min_age=min_age)


def student_records(db: Session) -> list[dict[str, Any]]:
    """Load live ORM rows and turn them into plain dictionaries for algorithms."""
    return [schemas.StudentRead.model_validate(student).model_dump() for student in crud.list_students(db)]


@protected.get("/students/sorted", response_model=list[schemas.StudentRead], tags=["students"])
def read_sorted_students(db: DbSession, by: str = "age"):
    if by not in {"age", "name"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="by must be age or name")
    students = student_records(db)
    algorithms.insertion_sort_by_field(students, by)
    return students


@protected.get("/students/search", response_model=schemas.StudentRead, tags=["students"])
def search_students(name: str, db: DbSession):
    students = student_records(db)
    sorted_by_name = sorted(students, key=lambda student: student["name"])
    found = algorithms.binary_search_by_name(sorted_by_name, name)
    if found == -1:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Student named {name} was not found")
    return found


@protected.get("/students/report", response_model=schemas.RosterReportRead, tags=["students"])
def read_roster_report(db: DbSession, min_age: int = 21):
    students = student_records(db)
    return {
        "report": algorithms.format_roster_report(students),
        "count_meeting_min_age": algorithms.count_students_meeting_min_age(students, min_age),
    }


@protected.get("/students/{student_id}/course-count", response_model=schemas.CourseCountRead, tags=["students"])
def read_course_count(student_id: IdPath, db: DbSession):
    if crud.get_student(db, student_id) is None:
        raise not_found("Student", student_id)
    return {"student_id": student_id, "course_count": crud.course_count_for_student(db, student_id)}


@protected.get("/students/{student_id}", response_model=schemas.StudentRead, tags=["students"])
def read_student(student_id: IdPath, db: DbSession):
    student = crud.get_student(db, student_id)
    if student is None:
        raise not_found("Student", student_id)
    return student


@protected.patch("/students/{student_id}", response_model=schemas.StudentRead, tags=["students"])
def patch_student(student_id: IdPath, payload: schemas.StudentUpdate, db: DbSession):
    student = crud.get_student(db, student_id)
    if student is None:
        raise not_found("Student", student_id)
    try:
        updated = crud.update_student(db, student, payload)
    except IntegrityError as error:
        raise integrity_error_to_http_error(db, error) from error
    logger.info("Updated student id=%s", student_id)
    return updated


@protected.delete(
    "/students/{student_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, tags=["students"]
)
def remove_student(student_id: IdPath, db: DbSession):
    student = crud.get_student(db, student_id)
    if student is None:
        raise not_found("Student", student_id)
    crud.delete_student(db, student)
    logger.info("Deleted student id=%s", student_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@protected.post("/courses/", response_model=schemas.CourseRead, status_code=status.HTTP_201_CREATED, tags=["courses"])
def create_course(payload: schemas.CourseCreate, db: DbSession):
    try:
        course = crud.create_course(db, payload)
    except IntegrityError as error:
        raise integrity_error_to_http_error(db, error) from error
    logger.info("Created course id=%s", course.id)
    return course


@protected.get("/courses/", response_model=list[schemas.CourseRead], tags=["courses"])
def read_courses(db: DbSession):
    return crud.list_courses(db)


@protected.get("/courses/{course_id}", response_model=schemas.CourseRead, tags=["courses"])
def read_course(course_id: IdPath, db: DbSession):
    course = crud.get_course(db, course_id)
    if course is None:
        raise not_found("Course", course_id)
    return course


@protected.patch("/courses/{course_id}", response_model=schemas.CourseRead, tags=["courses"])
def patch_course(course_id: IdPath, payload: schemas.CourseUpdate, db: DbSession):
    course = crud.get_course(db, course_id)
    if course is None:
        raise not_found("Course", course_id)
    try:
        updated = crud.update_course(db, course, payload)
    except IntegrityError as error:
        raise integrity_error_to_http_error(db, error) from error
    logger.info("Updated course id=%s", course_id)
    return updated


@protected.delete(
    "/courses/{course_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, tags=["courses"]
)
def remove_course(course_id: IdPath, db: DbSession):
    course = crud.get_course(db, course_id)
    if course is None:
        raise not_found("Course", course_id)
    crud.delete_course(db, course)
    logger.info("Deleted course id=%s", course_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Administrators: user management --------------------------------------------------------


@admin.get("/", response_model=list[schemas.UserRead])
def read_users(db: DbSession):
    return crud.list_users(db)


@admin.post("/", response_model=schemas.UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: schemas.UserCreate, db: DbSession, current_admin: CurrentAdmin):
    try:
        user = crud.create_user(db, payload, auth.hash_password(payload.password))
    except IntegrityError as error:
        raise integrity_error_to_http_error(db, error) from error
    logger.info("Created user id=%s role=%s by admin id=%s", user.id, user.role, current_admin.id)
    return user


@admin.patch("/{user_id}", response_model=schemas.UserRead)
def patch_user(
    user_id: IdPath, payload: schemas.UserUpdate, response: Response, db: DbSession, current_admin: CurrentAdmin
):
    """Edit a user's name, role, or status, or set a new password for them.

    Admins cannot deactivate or demote themselves. Since the caller is always an active admin,
    this also guarantees at least one active admin remains.
    """
    user = crud.get_user(db, user_id)
    if user is None:
        raise not_found("User", user_id)
    is_self = user.id == current_admin.id
    if is_self and payload.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="You can't deactivate your own account"
        )
    if is_self and payload.role == "member":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="You can't remove your own administrator role"
        )
    password_hash = auth.hash_password(payload.password) if payload.password else None
    updated = crud.update_user(db, user, payload, password_hash)
    if is_self and password_hash is not None:
        auth.set_session_cookie(response, updated)  # keep the admin signed in after resetting their own password
    logger.info("Updated user id=%s by admin id=%s", user_id, current_admin.id)
    return updated


app.include_router(public)
app.include_router(protected)
app.include_router(admin)
