# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## What this is

StudyTrack is a FastAPI + SQLAlchemy dashboard for Myntra's Trainee Enablement team, with a plain-JavaScript frontend. Only approved users can sign in; there is no public sign-up. Locally the frontend calls this repo's backend at `http://<same host>:8000`. In production the frontend is on Netlify and calls `/api/*`, which Netlify proxies to the Render backend (never a third-party roster API). Production data lives in Postgres (Neon); local development defaults to SQLite.

## Commands

Run from the `studytrack` root (in `venv`):

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt          # backend deps + test/lint tools
cp .env.example .env                         # then set BOOTSTRAP_ADMIN_EMAIL / _PASSWORD
uvicorn backend.main:app --reload --port 8000 --env-file .env
```

Second terminal: `python3 -m http.server 5500 --directory frontend`, then open `http://127.0.0.1:5500` (or `localhost:5500`; use 127.0.0.1 if another service such as ChromaDB holds `localhost:8000` on IPv6). API docs: `http://localhost:8000/docs` (disabled in production).

- Tests: `pytest` (unit + API, 140+ tests, temp SQLite). `TEST_DATABASE_URL=postgresql://... pytest` runs the same suite on Postgres. Tests never read `DATABASE_URL`.
- Browser tests: `pytest -m e2e` (Playwright; starts its own servers on 8000/5500; first run `python -m playwright install chromium`). Set `E2E_BASE_URL` (+ `E2E_EMAIL`/`E2E_PASSWORD`) to run them against an already-running stack instead.
- Docker: `docker compose up --build` (Postgres 18 + API image + nginx on `127.0.0.1:5500`; sign in as `admin@studytrack.local` / `change-me-locally`). `docker compose --profile test run --rm --build tests` runs the suite inside the test image on a throwaway Postgres 18, exactly as CI does.
- Lint/format: `ruff check . && ruff format --check .`
- Accounts: `python -m backend.manage create-user --email you@x.com --name "You" --role admin`; `... set-password --email ...`.
- Demo data: `python -m backend.seed_data --reset` (replaces trainees/courses, never users).
- Migrations: `alembic revision --autogenerate -m "..."` then review the file. The app runs `upgrade head` on startup.

## Architecture

- `backend/main.py` — all routes, grouped into three `APIRouter`s in this file: `public` (`/health`, `/auth/login`, `/auth/logout`), `protected` (router-level `Depends(auth.current_user)`; everything else), and `admin` (`/users/*`, requires the admin role). Startup uses a `lifespan` handler: Alembic migrations, bootstrap admin from env, demo seed. CORS origins come from `ALLOWED_ORIGINS` and are never wildcarded.
- `backend/auth.py` — Argon2 password hashing (`pwdlib`), HS256 JWT session tokens (`PyJWT`) in an HttpOnly `SameSite=Lax` cookie (`Secure` in production), `current_user` / `require_admin` dependencies, in-memory per-email login throttle, startup settings check, bootstrap admin. Each token carries `users.token_version`; bumping it revokes every session for that user (password, role, or status change).
- `backend/models.py` — `Student` 1—many `Course` (`cascade="all, delete-orphan"`, DB `CheckConstraint` on credits 1–6) and `User` (role check constraint, `is_active`, `token_version`).
- `backend/schemas.py` — Pydantic contracts, separate from the ORM. Input strings are whitespace-stripped; ids and ages are bounded so Postgres INTEGER never overflows.
- `backend/crud.py` — the only place that talks to the DB session; routes never build SQLAlchemy statements. PATCH helpers ignore explicit nulls. `course_count_for_student` uses `select(func.count(...))` so the aggregate runs in SQL.
- `backend/database.py` — engine/session, `postgres://` URL normalization to psycopg 3, SQLite `PRAGMA foreign_keys=ON`, and `run_migrations()` (stamps pre-Alembic SQLite files at the baseline before upgrading).
- `backend/migrations/` — Alembic. `env.py` reuses the app engine, so `DATABASE_URL` is the only DB setting. `tests/test_migrations.py` fails if models and migrations drift.
- `backend/algorithms.py` — hand-written Insertion Sort, iterative Binary Search, and reporting helpers applied to the live roster via `main.student_records()`. They exist to demonstrate the algorithms, not for performance; keep them hand-written.
- `backend/ai_service.py` — mock mode by default (offline, deterministic). `AI_MODE=real` + `GOOGLE_API_KEY` makes `summarize_notes` call Gemini (SDK imported lazily, structured output). `search_notes` is always mock. `notes` is a static dataset unrelated to the DB.
- `backend/manage.py` — account CLI. `backend/seed_data.py` — idempotent demo seeding.
- `frontend/` — vanilla ES modules, no build step. `js/config.js` picks the API base (local port 8000 vs `/api`), `js/api.js` is the only fetch wrapper (cookies, 401 redirect, 422 field errors, cold-start retries), `js/ui.js` holds DOM helpers, `js/router.js` hash routes, `js/views/*` one module per page. `login.html` is the sign-in page. `_headers` holds the site's CSP and other security headers.
- `backend/edge.py` — ASGI middlewares that run before any route: security headers, the Netlify origin lock (when `PROXY_SIGNING_SECRET` is set, every request except `GET /health` must carry a valid Netlify `x-nf-sign` JWS with `deploy_context=production`), and a 256 KB body cap. `edge.trusted_client_ip()` gives the Netlify-reported visitor IP on signed requests.
- `Dockerfile` — multi-stage: `base` (Python + production deps, non-root uid 10001), `test` (adds dev deps and `tests/`; what CI runs pytest in), `runtime` (default; same uvicorn command as Render, `HEALTHCHECK` on `/health`). `compose.yaml` — `db` (Postgres 18.6, persistent volume), `api`, `web` (nginx serving `frontend/`), plus `db-test` (tmpfs) and `tests` under the `test` profile. Render still uses its native Python runtime; the image is for local parity and CI.
- Deployment: `render.yaml` (API), `netlify.toml` (signed `/api` proxy rules with per-IP rate limits; signed proxies only work in this file, so don't add a `_redirects` file), `.github/workflows/ci.yml` (lint incl. hadolint + compose config, SQLite tests natively, Postgres tests inside the Docker test image, Playwright against the full compose stack, pip-audit), `deploy.yml` (CI, then Render deploy hook for the exact commit, wait for `/health` version, Netlify CLI deploy, live smoke test).

## Conventions specific to this repo

- New routes go on the `protected` (or `admin`) router. `tests/test_auth.py::test_every_non_public_route_requires_sign_in` walks `app.routes` and fails if a non-public route answers without a session.
- Error mapping is centralized in `integrity_error_to_http_error` in `main.py`: Postgres SQLSTATE (`23505`/`23503`/`23514`) with SQLite message fallback; it returns the `HTTPException` and callers `raise ... from error`. Add new constraint-driven errors there and a case to `tests/test_error_mapping.py`.
- Every mutating route logs one INFO line via the module-level `logger` after success (students, courses, users, sign-in, password changes). Never log passwords, tokens, or failed-login emails.
- Secrets (`SECRET_KEY`, `DATABASE_URL`, `PROXY_SIGNING_SECRET`, `BOOTSTRAP_ADMIN_PASSWORD`, `GOOGLE_API_KEY`) come from the environment only; `.env` is gitignored and `.env.example` documents every variable. This repository is public.
- Frontend: never use `innerHTML` with data; build DOM with `el()` / `textContent`. No inline `<script>` or `style=""` (the production CSP forbids them); set CSS custom properties through `element.style.setProperty`. Colors come from `css/tokens.css`.
- Schema changes need an Alembic migration; `create_all` is not used by the app.
- Password hashing goes through `auth.hash_password` / `auth.verify_password`, which share a 2-slot semaphore (503 when saturated) so Argon2 can't exhaust the 512 MB Render instance. Don't call `_password_hash` directly.
- Docker: base images are pinned to exact versions (bump by hand; Dependabot is security-only and doesn't cover images). Keep `AI_MODE: mock` fixed in `compose.yaml`, because Compose reads `./.env` and must never pick up a real Gemini key in tests. CI job names (`Lint`, `Tests (sqlite)`, `Tests (postgres)`, `Browser tests`, `Dependency audit`) are required by branch protection; don't rename them.
