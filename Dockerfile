# StudyTrack API image.
#
#   docker build -t studytrack-api .                  production image (the default, last stage)
#   docker build --target test -t studytrack-test .   adds the test tools and tests/
#
# The API needs DATABASE_URL (Postgres) and SECRET_KEY at runtime; compose.yaml sets local values.
# The frontend is static files served by Netlify (or nginx in compose.yaml), so it is not in here.
# Base images are pinned exactly; Dependabot raises no security alerts for them, so bump by hand.

ARG PYTHON_IMAGE=python:3.13.17-slim-trixie

# ---- base: Python plus the production dependencies, shared by both images -------------------
FROM ${PYTHON_IMAGE} AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# A fixed, unprivileged user. Nothing in /app is writable by it, so a compromised process
# cannot modify the application code.
RUN useradd --system --uid 10001 --user-group --no-create-home --shell /usr/sbin/nologin app

# Dependencies first, so code changes don't invalidate the cached install layer.
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# ---- test: what CI runs pytest in ----------------------------------------------------------
FROM base AS test

COPY requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY pyproject.toml alembic.ini ./
COPY backend ./backend
COPY tests ./tests

USER 10001:10001
# The test user can't write to /app, so keep pytest's cache and coverage data in /tmp.
ENV COVERAGE_FILE=/tmp/.coverage
CMD ["pytest", "-p", "no:cacheprovider"]

# ---- runtime: the production API -----------------------------------------------------------
FROM base AS runtime

COPY alembic.ini ./
COPY backend ./backend

# Numeric so platforms can verify the container isn't root without resolving the name.
USER 10001:10001
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=5 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/health', timeout=4)"]

# Same command Render runs. Startup migrates the database, creates the bootstrap admin if needed,
# and seeds demo data. exec makes uvicorn PID 1 so it receives stop signals directly.
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port \"$PORT\" --proxy-headers --forwarded-allow-ips='*'"]
