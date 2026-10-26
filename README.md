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

The browser only ever talks to the Netlify site. Netlify forwards `/api/*` to Render on the server side. That keeps the session cookie first-party (Safari blocks third-party cookies between `netlify.app` and `onrender.com`) and keeps the Render URL out of the frontend code. Netlify signs every request it forwards, and the API refuses anything unsigned, so the Render URL is useless on its own. Every API route except `/health`, `/auth/login`, and `/auth/logout` also requires a valid session, and the interactive docs are turned off in production.

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

## Run with Docker

Docker runs the same stack as production without installing Python or Postgres: Postgres 18 (Neon's version), the API image built from the `Dockerfile`, and nginx serving `frontend/` in place of Netlify.

```bash
docker compose up --build
```

Open `http://127.0.0.1:5500` and sign in as `admin@studytrack.local` with password `change-me-locally`. To use your own account, set `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` in your shell before the first start. The admin is only created while the database has no users. `docker compose down` stops everything and keeps the data; add `--volumes` to start over with an empty database.

Notes:

- Ports bind to `127.0.0.1` only: the site on 5500, the API on 8000, and Postgres on 55432 for tools such as `psql`.
- The API container runs as an unprivileged user and checks its own `/health`.
- Compose reads `./.env` to fill in `${...}` values, but the AI Helper is fixed to offline mock mode so the stack never calls Gemini by accident. To try Gemini in Docker, create a gitignored `compose.override.yaml` that sets `AI_MODE` and `GOOGLE_API_KEY` under `services.api.environment`.
- Render still deploys with its native Python runtime from `render.yaml`. The `runtime` stage of the `Dockerfile` runs the same start command, so switching Render to Docker later only means setting `runtime: docker` and removing the build and start commands from `render.yaml`.

## Tests and linting

```bash
ruff check . && ruff format --check .      # lint and formatting
pytest                                     # unit and API tests on a temporary SQLite database
pytest --cov=backend                       # the same, with coverage
python -m playwright install chromium      # once, before the browser tests
pytest -m e2e                              # browser tests; they start their own servers on 8000 and 5500
```

With Docker you can run the suite the way CI does:

```bash
docker compose --profile test run --rm --build tests    # every test inside the image, on a throwaway Postgres 18
docker compose --profile test down                      # stop the throwaway database afterwards
```

To point the browser tests at the Docker stack instead of their own servers, start it with `docker compose up --build -d --wait`, then run `E2E_BASE_URL=http://127.0.0.1:5500 E2E_EMAIL=admin@studytrack.local E2E_PASSWORD=change-me-locally pytest -m e2e`. That run adds and deletes a trainee and creates a user, so use a fresh database.

The tests never read `DATABASE_URL`, so they cannot touch a real database by accident. They use `TEST_DATABASE_URL` when it is set and a temporary SQLite file otherwise.

## Deploy

GitHub Actions is the only thing that publishes code. Render's auto-deploy is off (`autoDeployTrigger: "off"` in `render.yaml`) and the Netlify site has no Git builds, so nothing reaches production without passing CI.

### One-time setup

Do these in order. Generate each secret with `python -c "import secrets; print(secrets.token_urlsafe(48))"` and keep it in a password manager.

0. **Secure the accounts.** Turn on two-factor sign-in for GitHub, Render, Netlify, and Neon. In GitHub > Settings > Applications, limit the Render and Netlify GitHub apps to only this repository. In this repository's Settings > Code security, enable secret scanning, push protection, and Dependabot alerts.
1. **Open a pull request** from your feature branch. Wait for the five CI checks to pass, then merge. The Deploy workflow will run and stop at "Check configuration" because no secrets exist yet. That is expected and deploys nothing.
2. **Database (Neon, free).** Create a project in AWS Singapore and copy the **direct** (not pooled) connection string. Render's free Postgres is deleted after 30 days, and Render's free disk is wiped on every restart, so SQLite is not an option there.
3. **API (Render).** Go to New > Blueprint and pick this repository; `render.yaml` describes the service. When prompted, enter `DATABASE_URL`, `PROXY_SIGNING_SECRET`, `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD`, and `BOOTSTRAP_ADMIN_NAME`. Leave `GOOGLE_API_KEY` empty unless you want Gemini summaries. In the first deploy's logs, look for "Running upgrade" and "Created bootstrap admin". Copy the service URL (it gets a suffix if `studytrack-api` was taken) and, under Settings, the **Deploy Hook** URL.
4. **Site (Netlify).** Create the site with Add new site > Deploy manually, so it has no Git builds. If you already made a Git-linked site, open Site configuration > Build & deploy > Continuous deployment and choose **Stop builds** instead. Under Site configuration > Environment variables, add `PROXY_SIGNING_SECRET` with the same value as on Render; its scopes must include **Runtime**. Note the site URL and **Site ID**, and create a personal access token under User settings > Applications.
5. **Back on Render,** set `ALLOWED_ORIGINS` to the Netlify URL.
6. **GitHub.** Under Settings > Environments, create `production` and add:
   - secrets: `RENDER_DEPLOY_HOOK_URL`, `NETLIFY_AUTH_TOKEN`, `NETLIFY_SITE_ID`
   - variables: `RENDER_API_URL` (for example `https://studytrack-api.onrender.com`) and `SITE_URL` (for example `https://studytrack.netlify.app`)

   Then protect `main` under Settings > Branches: require pull requests and the checks **Lint**, **Tests (sqlite)**, **Tests (postgres)**, **Browser tests**, and **Dependency audit**.
7. **Deploy.** Open Actions > Deploy > Run workflow. The backend, frontend, and smoke jobs should all pass; the sign-in smoke check is skipped until the next step.
8. **First sign-in.** Open the Netlify URL, sign in as the bootstrap admin, and create real accounts plus a `member` account used only by the smoke test. Add its credentials as `SMOKE_EMAIL` and `SMOKE_PASSWORD` secrets on the `production` environment. Delete `BOOTSTRAP_ADMIN_PASSWORD` from Render, then run the Deploy workflow once more.
9. **Monitoring.** Add a free uptime check (UptimeRobot or similar) on `https://<site>/api/health` every 5 minutes with email alerts; it also keeps the free instance warm. Turn on Render's notifications for failed deploys.

### How a change goes live

Open a pull request: `.github/workflows/ci.yml` runs lint (including the Dockerfile and `compose.yaml`), the tests on SQLite, the tests inside the Docker image on Postgres 18, the browser tests against the full Docker stack, and `pip-audit`. Merge to `main`: `.github/workflows/deploy.yml` runs CI again on the merged commit, then:

1. triggers Render's deploy hook for exactly that commit and waits until `/health` reports it,
2. publishes `frontend/` to Netlify with the CLI, after pointing the proxy rules in `netlify.toml` at `RENDER_API_URL`,
3. checks the live site: health through the proxy, 401 without a session, 403 when calling Render directly, a CSP header, and a real sign-in with the smoke account.

### Free-tier cold starts

A free Render instance sleeps after about 15 idle minutes and takes about a minute to wake. Netlify gives up on a proxied request after 26 seconds. The frontend handles this: the sign-in page wakes the API while you type, and read requests retry for up to 90 seconds behind a "Waking up the server" banner. To avoid cold starts entirely, use the uptime check above, set the repository variable `KEEP_WARM=true` to enable `.github/workflows/keep-warm.yml`, or move the service to a paid Render plan.

### Check the protections on the live site

```bash
curl -i https://<render>/students/        # 403: direct calls to Render are refused
curl -i https://<render>/health           # 200 with the deployed commit
curl -i https://<site>/api/students/      # 401: signed by Netlify, but no session
for i in $(seq 25); do curl -s -o /dev/null -w "%{http_code} " -H 'Content-Type: application/json' \
  -d '{"email":"x@y.z","password":"wrong"}' https://<site>/api/auth/login; done   # 401s, then 429
```

## Security model

Protection is layered, so each request has to pass every layer before it reaches the data.

| Layer | What it does | Where it lives |
| --- | --- | --- |
| Network | Cloudflare absorbs network-level DDoS floods, on every Render plan | Render, automatic |
| Edge | Netlify limits each visitor IP to 20 sign-in attempts and 300 API requests a minute | `netlify.toml` |
| Origin lock | Netlify signs every request it forwards. The API refuses unsigned requests with a 403 before doing any work, so calling the Render URL directly gets nowhere. Only `GET /health` is exempt, for Render's health checks | `netlify.toml`, `backend/edge.py` |
| Application | A session is required on every route except health, sign-in, and sign-out. Five failed sign-ins lock an email for 15 minutes. At most two password hashes run at once, and request bodies are capped at 256 KB | `backend/auth.py`, `backend/edge.py` |
| Data | Neon only accepts TLS connections. Every secret lives in environment variables | Neon, Render, Netlify |
| Accounts | Two-factor sign-in, GitHub apps limited to this repository, branch protection, secret scanning, Dependabot, and `pip-audit` in CI | GitHub, Render, Netlify, Neon |

More detail:

- Passwords are hashed with Argon2. Sessions are signed JWTs in an `HttpOnly`, `SameSite=Lax`, `Secure` cookie that page scripts cannot read. They last `SESSION_HOURS` (default 8).
- Sign-in errors never reveal whether an email exists. Failed attempts are logged with the visitor's IP as reported by Netlify, never with the email.
- Changing a password, role, or active status signs that user out everywhere.
- Administrators manage users. They cannot deactivate or demote themselves, so at least one active admin always remains.
- Netlify deploy previews carry a different signature context, so they can never reach production data.
- The site sends a strict Content-Security-Policy, `nosniff`, `DENY` framing, and a referrer policy (`frontend/_headers`). API responses add `Cache-Control: no-store` and, in production, HSTS.
- This repository is public. `.env` is gitignored; never commit one.

Known trade-off: anyone who knows an account's email can lock it for 15 minutes with five wrong passwords. That is accepted in exchange for stopping password guessing.

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
