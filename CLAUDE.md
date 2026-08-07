# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

StudyTrack is a two-process FastAPI + SQLite dashboard for Myntra's Trainee Enablement team: a plain-JavaScript frontend that always talks to this repo's own FastAPI backend at `http://localhost:8000` (never a third-party roster API).

## Commands

Run from the `studytrack` root, backend first (in `venv`):

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
python -m backend.seed_data --reset
uvicorn backend.main:app --reload --port 8000
```

Then, in a second terminal, serve the frontend on the CORS-approved local origin:

```bash
python3 -m http.server 5500 --directory frontend
```

Open `http://localhost:5500`. API docs are auto-generated at `http://localhost:8000/docs`.

There are no test files, linter, or formatter configured in this repo.

## Architecture

- `backend/main.py` — all FastAPI routes live here directly (no router modules). CORS origins come from `ALLOWED_ORIGINS` (comma-separated) and are never wildcarded. `Base.metadata.create_all` + `seed_database()` run on startup, so the schema and demo data are always ready without a separate migration step.
- `backend/models.py` — SQLAlchemy ORM: `Student` 1—many `Course`, with `cascade="all, delete-orphan"` and a DB-level `CheckConstraint` on `credits` (1–6).
- `backend/schemas.py` — Pydantic request/response contracts, kept deliberately separate from the ORM models (`StudentCreate`/`StudentUpdate`/`StudentRead`, etc.).
- `backend/crud.py` — the only place that talks to the DB session; routes never build SQLAlchemy statements themselves. `course_count_for_student` intentionally uses `select(func.count(...))` so the aggregate runs in SQL, not Python.
- `backend/database.py` — engine/session setup. SQLite foreign keys are off by default and are turned on explicitly via a `PRAGMA foreign_keys=ON` connect event.
- `backend/algorithms.py` — hand-written (not stdlib) Insertion Sort, iterative Binary Search, and reporting helpers, applied to the *live* DB roster after routes load it into plain dicts via `main.student_records()`. Binary search requires the list to already be sorted by the search field. These exist to demonstrate the algorithms explicitly, not for performance.
- `backend/ai_service.py` — the "AI Helper": fully offline, deterministic **mock mode** by default (no LLM/embedding calls). `AI_MODE=real` + `GOOGLE_API_KEY` switches `summarize_notes` to call Gemini via the `google-genai` SDK; `search_notes` always stays mock (fixed 12-word vocabulary vectors + hand-written cosine similarity) regardless of `AI_MODE`. The `notes` list here is a separate static in-memory dataset, unrelated to the `students`/`courses` DB tables.
- `backend/seed_data.py` — idempotent demo-data seeding, also invoked as `python -m backend.seed_data --reset`.
- `frontend/app.js` — vanilla JS, no framework/build step. `API_BASE_URL` must be updated by hand when pointing at a deployed backend (paired with updating `ALLOWED_ORIGINS` on that backend to the exact deployed frontend origin).

## Conventions specific to this repo

- Error mapping is centralized: `IntegrityError` from CRUD calls is translated to HTTP status codes by `integrity_error_to_http_error` in `main.py` by pattern-matching the DB driver's error message (unique+email → 409, foreign key → 422, credits/check constraint → 422, else 400). Add new constraint-driven errors there rather than inline in a route.
- Every mutating route (`create_student`, `patch_student`, `remove_student`, and the `courses/` equivalents) logs one INFO line via the module-level `logger` after success — keep new mutating routes consistent with that.
- `AI_MODE` and `GOOGLE_API_KEY` are read from the process environment only; no API key is ever committed, and `.env` is gitignored. `.env.example` documents the expected variables.
