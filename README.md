# StudyTrack

StudyTrack is the trainee roster dashboard for Myntra's Trainee Enablement team. A FastAPI backend stores trainees, their course enrollments, and user accounts. A plain-JavaScript frontend with no build step lets signed-in staff manage the roster, run reports, and use a small AI study helper.

Only approved accounts can sign in. There is no public sign-up: administrators create users from the **Users** page.

```
Browser ──HTTPS──> Netlify  (static frontend/, security headers)
                     └─ /api/* proxy ──HTTPS──> Render web service (FastAPI + uvicorn)
                                                  └─ Neon Postgres
GitHub Actions: pull request → lint, tests on SQLite and Postgres, browser tests, dependency audit
                push to main → the same CI → deploy API → deploy site → smoke-test the live site
```

The browser only ever talks to the Netlify site. Netlify forwards `/api/*` to Render on the server side. That keeps the session cookie first-party (Safari blocks third-party cookies between `netlify.app` and `onrender.com`) and keeps the Render URL out of the frontend code. Every API route except `/health`, `/auth/login`, and `/auth/logout` requires a valid session, and the interactive docs are turned off in production.

## Run locally

From the repository root:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

Edit `.env` and set `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` (12 or more characters). That account is created the first time the API starts with an empty users table. You can also create accounts at any time with the CLI:

```bash
python -m backend.manage create-user --email you@myntra.com --name "Your Name" --role admin
```

Start the API. It migrates the database and seeds the demo roster on startup.

```bash
uvicorn backend.main:app --reload --port 8000 --env-file .env
```

In a second terminal, serve the frontend:

```bash
python3 -m http.server 5500 --directory frontend
```

Open `http://127.0.0.1:5500` and sign in. `http://localhost:5500` works too, unless another program, such as ChromaDB, is listening on `localhost:8000`. The API docs are at `http://localhost:8000/docs`.

To reset the demo trainees and courses (user accounts are kept), run `python -m backend.seed_data --reset`.

If you have a `backend/studytrack.db` from before sign-in was added, it is upgraded in place on first start.

## Tests and linting

```bash
ruff check . && ruff format --check .      # lint and formatting
pytest                                     # unit and API tests on a temporary SQLite database
pytest --cov=backend                       # the same, with coverage
python -m playwright install chromium      # once, before the browser tests
pytest -m e2e                              # browser tests; they start their own servers on 8000 and 5500
```

To run the suite against Postgres, start one (for example `docker run --rm -e POSTGRES_PASSWORD=postgres -p 55432:5432 postgres:17`) and run `TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:55432/postgres pytest`. The tests never read `DATABASE_URL`, so they cannot touch a real database by accident.

## Deploy

### One-time setup

1. **Database (Neon, free).** Create a project in the AWS Singapore region and copy the **direct** (not pooled) connection string. Render's free Postgres is deleted after 30 days, and Render's free disk is wiped on every restart, so SQLite is not an option there.
2. **API (Render).** Go to New > Blueprint and pick this repository; `render.yaml` describes the service. When prompted, enter `DATABASE_URL`, `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD`, and `BOOTSTRAP_ADMIN_NAME`. Leave `GOOGLE_API_KEY` empty unless you want Gemini summaries. After the first deploy, copy the service URL and, under Settings, the **Deploy Hook** URL.
3. **Site (Netlify).** Create a site without connecting Git builds (for example with `npx netlify-cli sites:create`). Note its **Site ID** and create a personal access token under User settings > Applications. Set `ALLOWED_ORIGINS` on Render to the Netlify URL.
4. **GitHub.** Under Settings > Environments, create `production` and add:
   - secrets: `RENDER_DEPLOY_HOOK_URL`, `NETLIFY_AUTH_TOKEN`, `NETLIFY_SITE_ID`, `SMOKE_EMAIL`, `SMOKE_PASSWORD`
   - variables: `RENDER_API_URL` (for example `https://studytrack-api.onrender.com`) and `SITE_URL` (for example `https://studytrack.netlify.app`)

   Then protect `main` under Settings > Branches: require pull requests and the CI checks **Lint**, **Tests (sqlite)**, **Tests (postgres)**, **Browser tests**, and **Dependency audit**.
5. **First sign-in.** Open the Netlify URL, sign in as the bootstrap admin, and create real accounts plus a `member` account for the smoke test (its credentials are the `SMOKE_*` secrets). Then delete `BOOTSTRAP_ADMIN_PASSWORD` from Render.

### How a change goes live

Open a pull request: `.github/workflows/ci.yml` runs lint, the tests on SQLite and Postgres, the browser tests, and `pip-audit`. Merge to `main`: `.github/workflows/deploy.yml` runs CI again on the merged commit, then:

1. triggers Render's deploy hook for exactly that commit and waits until `/health` reports it,
2. publishes `frontend/` to Netlify with the CLI, after rewriting the proxy target in `frontend/_redirects` to `RENDER_API_URL`,
3. checks the live site: health through the proxy, 401 without a session, no public `/docs`, a CSP header, and a real sign-in with the smoke account.

Render's auto-deploy is off (`autoDeployTrigger: "off"`) and Netlify has no Git builds, so nothing reaches production without passing CI.

### Free-tier cold starts

A free Render instance sleeps after about 15 idle minutes and takes about a minute to wake. Netlify gives up on a proxied request after 26 seconds. The frontend handles this: the sign-in page wakes the API while you type, and read requests retry for up to 90 seconds behind a "Waking up the server" banner. To avoid cold starts entirely, set the repository variable `KEEP_WARM=true` to enable `.github/workflows/keep-warm.yml`, or move the service to a paid Render plan.

## Security model

- Passwords are hashed with Argon2. Sessions are signed JWTs in an `HttpOnly`, `SameSite=Lax`, `Secure` cookie that page scripts cannot read. They last `SESSION_HOURS` (default 8).
- Five failed sign-ins for one email lock it for 15 minutes. Error messages never reveal whether an email exists.
- Changing a password, role, or active status signs that user out everywhere.
- Administrators manage users. They cannot deactivate or demote themselves, so at least one active admin always remains.
- The production site sends a strict Content-Security-Policy plus `nosniff`, `DENY` framing, and a referrer policy (`frontend/_headers`).
- Secrets come only from environment variables. `.env` is gitignored, and this repository is public, so never commit one.

## API endpoints

All responses are JSON. Everything except the first three rows requires the session cookie set by `POST /auth/login`; without it the API answers 401.

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/health` | Public. `{"status":"ok","version":"<deployed commit>"}` |
| POST | `/auth/login` | Public. `{"email","password"}` → user, sets the cookie. 401 bad credentials, 429 locked out |
| POST | `/auth/logout` | Public. Clears the cookie. 204 |
| GET | `/auth/me` | The signed-in user |
| POST | `/auth/change-password` | `{"current_password","new_password"}` → 204 |
| GET | `/users/` | Admin only. All accounts |
| POST | `/users/` | Admin only. `{"email","full_name","password","role"}` → 201 |
| PATCH | `/users/{id}` | Admin only. Any of `full_name`, `role`, `is_active`, `password` |
| POST | `/students/` | `{"name","email","age"}` → 201. 409 duplicate email |
| GET | `/students/` | Optional `?min_age=20` |
| GET | `/students/sorted?by=age` | `by` is `age` or `name`; insertion-sorted |
| GET | `/students/search?name=Priya%20Iyer` | Exact, case-sensitive binary search. 404 when absent |
| GET | `/students/report?min_age=21` | `{"report":"…","count_meeting_min_age":5}` |
| GET | `/students/{id}` | 404 when absent |
| PATCH | `/students/{id}` | Any of `name`, `email`, `age` |
| DELETE | `/students/{id}` | Also deletes the trainee's courses. 204 |
| GET | `/students/{id}/course-count` | `{"student_id":1,"course_count":2}`, counted in SQL |
| POST | `/courses/` | `{"course_name","credits","student_id"}` → 201 |
| GET | `/courses/` | All enrollments |
| GET | `/courses/{id}` | 404 when absent |
| PATCH | `/courses/{id}` | Any of `course_name`, `credits`, `student_id` |
| DELETE | `/courses/{id}` | 204 |
| POST | `/assistant/summarize` | `{"text":"…"}` (up to 20,000 characters) → `{"topic","key_points","difficulty"}` |
| GET | `/assistant/search?query=binary%20search` | Notes ranked by similarity |

Validation errors return 422. Emails must contain `@`, ages must be 1–150, credits must be 1–6, and passwords need at least 12 characters. A course's `student_id` must reference an existing trainee (422 otherwise).

## Where each endpoint appears in the app

| Page | Endpoints it uses |
| --- | --- |
| Sign in | `/health` (wake-up check), `/auth/me`, `/auth/login` |
| Every page | `/auth/me`, `/auth/logout`, `/auth/change-password` (account menu) |
| Dashboard | `/students/`, `/courses/`, `/students/report`, plus add trainee and add course |
| Trainees | `/students/` with minimum age, `/students/sorted`, `/students/search`, create, edit, and delete; the detail panel uses `/students/{id}`, `/students/{id}/course-count`, and the course endpoints |
| Courses | `/courses/`, `/courses/{id}` (fresh copy before editing), create, edit, and delete |
| Reports | `/students/report` |
| AI Helper | `/assistant/summarize`, `/assistant/search` |
| Users (admins) | `/users/` list, create, and edit |

## Algorithms engine

`GET /students/sorted?by=age` loads the live roster and applies the project's in-place insertion sort. For the demo data it returns Farhan, Rohan, Meera, Priya, Aditi, Devansh, Sameer, then Kavya. Insertion sort is O(n²) in the worst case, because a reverse-ordered list shifts nearly every earlier item for each new one. Its best case is O(n) for an already sorted roster: each pass makes one comparison and no shifts.

`GET /students/search?name=Priya%20Iyer` builds a name-sorted copy and runs the hand-written iterative binary search. Binary search needs the list sorted by the search field, because discarding half the range is only safe when smaller and larger values sit on predictable sides.

`GET /students/report?min_age=21` returns one line per trainee and a visible-accumulator count, which is 5 for the demo data.

## AI Helper

By default the helper runs in **mock** mode: offline, deterministic, and with no LLM calls. The mock summarizer uses the first non-empty line as the topic and the first three sentences as key points. It rates difficulty as easy below 40 words, medium at 40–100, and hard above 100.

`GET /assistant/search` always runs offline. It builds 12-word count vectors and ranks the five sample notes by hand-written cosine similarity. For the query `binary`, note 1 scores 1/√5 ≈ 0.447, because that note says "search" twice and "binary" once. A query with no vocabulary words returns all five notes at score 0.0 in id order.

Set `AI_MODE=real` and `GOOGLE_API_KEY` to have summaries generated by Google Gemini through the `google-genai` SDK, using structured JSON output. `GEMINI_MODEL` defaults to `gemini-3.6-flash`. The prompt sent to the model:

```text
Task: Summarize the study notes below.
Context: The notes are supplied verbatim after NOTES.
Constraints: Return exactly three fields. Use a concise title-like topic, give at most three key points, and set difficulty to exactly easy, medium, or hard. Do not include commentary, markdown, or extra fields.
Format instructions: Return valid JSON only, matching this schema exactly:
{"topic":"string","key_points":["string"],"difficulty":"easy|medium|hard"}
NOTES:
{{raw_text}}
```

## Configuration

Every setting is an environment variable; `.env.example` documents each one. The ones that matter most:

| Variable | Local default | Production |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | `production` (requires a 32+ character `SECRET_KEY` and secure cookies, and hides `/docs`) |
| `SECRET_KEY` | temporary per-process key | generated by Render |
| `DATABASE_URL` | `backend/studytrack.db` (SQLite) | Neon connection string |
| `COOKIE_SECURE` | `false` | `true` |
| `BOOTSTRAP_ADMIN_EMAIL` / `_PASSWORD` | unset | first admin; remove the password after the first sign-in |
| `SEED_DEMO_DATA` | `true` | `true` or `false` |
| `AI_MODE` / `GOOGLE_API_KEY` | `mock` | `mock`, or `real` with a key |
