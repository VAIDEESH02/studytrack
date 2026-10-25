"""Browser tests (Playwright).

By default they start their own backend on port 8000 (fresh SQLite database, demo roster, a
bootstrap admin) and serve frontend/ on port 5500, exactly like local development.
Set E2E_BASE_URL (plus E2E_EMAIL and E2E_PASSWORD) to run them against a running deployment.
"""

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
E2E_EMAIL = os.environ.get("E2E_EMAIL", "e2e-admin@studytrack.test")
E2E_PASSWORD = os.environ.get("E2E_PASSWORD", "e2e-admin-password")


def _port_in_use(port: int) -> bool:
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _wait_for(url: str, process: subprocess.Popen, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Server for {url} exited early with code {process.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError):
            pass
        time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for {url}")


@pytest.fixture(scope="session")
def app_url(tmp_path_factory):
    external = os.environ.get("E2E_BASE_URL")
    if external:
        yield external.rstrip("/")
        return

    for port in (8000, 5500):
        if _port_in_use(port):
            pytest.fail(f"Port {port} is busy. Stop your local StudyTrack servers before running the e2e tests.")

    workdir = tmp_path_factory.mktemp("e2e")
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{workdir / 'e2e.db'}",
        "SECRET_KEY": "e2e-only-secret-key-" + "x" * 40,
        "ENVIRONMENT": "development",
        "COOKIE_SECURE": "false",
        "ALLOWED_ORIGINS": "http://localhost:5500,http://127.0.0.1:5500",
        "BOOTSTRAP_ADMIN_EMAIL": E2E_EMAIL,
        "BOOTSTRAP_ADMIN_PASSWORD": E2E_PASSWORD,
        "BOOTSTRAP_ADMIN_NAME": "Eve Tester",
        "SEED_DEMO_DATA": "true",
        "AI_MODE": "mock",
    }
    backend_log = open(workdir / "backend.log", "w")  # noqa: SIM115 (closed in finally)
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--port", "8000"],
        cwd=ROOT,
        env=env,
        stdout=backend_log,
        stderr=subprocess.STDOUT,
    )
    frontend = subprocess.Popen(
        [sys.executable, "-m", "http.server", "5500", "--bind", "127.0.0.1", "--directory", "frontend"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for("http://127.0.0.1:8000/health", backend)
        _wait_for("http://127.0.0.1:5500/login.html", frontend)
        # 127.0.0.1 rather than localhost: another service on [::1]:8000 would otherwise answer first.
        yield "http://127.0.0.1:5500"
    finally:
        for process in (frontend, backend):
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        backend_log.close()
        print(f"\nBackend log: {workdir / 'backend.log'}")
