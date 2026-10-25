"""Origin lock, body-size cap, security headers, and the password-hashing cap."""

import logging
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from backend import auth, edge
from backend.main import app
from tests.conftest import MEMBER_EMAIL, MEMBER_PASSWORD

SECRET = "proxy-test-secret-" + "z" * 40


def netlify_signature(
    secret: str = SECRET, *, issuer: str = "netlify", context: str = "production", expires_in: int = 60, **overrides
) -> str:
    """A token shaped like the x-nf-sign header Netlify adds to proxied requests."""
    claims = {
        "deploy_context": context,
        "exp": datetime.now(UTC) + timedelta(seconds=expires_in),
        "iss": issuer,
        "netlify_id": "00000000-0000-0000-0000-000000000000",
        "site_url": "https://studytrack.netlify.app",
        **overrides,
    }
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, secret, algorithm="HS256")


@pytest.fixture
def locked(monkeypatch):
    monkeypatch.setenv("PROXY_SIGNING_SECRET", SECRET)


@pytest.fixture
def signed_client(db_state, locked):
    client = TestClient(app)
    client.headers["x-nf-sign"] = netlify_signature()
    return client


# --- Origin lock ------------------------------------------------------------------------------


def test_lock_is_off_when_no_secret_is_configured(anon_client):
    assert anon_client.get("/students/").status_code == 401


@pytest.mark.parametrize(
    ("method", "path"), [("GET", "/students/"), ("POST", "/auth/login"), ("GET", "/docs"), ("POST", "/health")]
)
def test_unsigned_requests_are_refused_before_any_route(anon_client, locked, method, path):
    response = anon_client.request(method, path)
    assert response.status_code == 403
    assert response.json() == {"detail": edge.NOT_FROM_PROXY}


def test_health_stays_reachable_for_render_checks(anon_client, locked):
    assert anon_client.get("/health").status_code == 200


def test_signed_requests_pass_but_still_need_a_session(signed_client):
    assert signed_client.get("/students/").status_code == 401
    login = signed_client.post("/auth/login", json={"email": MEMBER_EMAIL, "password": MEMBER_PASSWORD})
    assert login.status_code == 200
    assert signed_client.get("/students/").status_code == 200


@pytest.mark.parametrize(
    "token",
    [
        "not-a-jws",
        netlify_signature("some-other-secret-" + "q" * 40),
        netlify_signature(expires_in=-120),
        netlify_signature(issuer="someone-else"),
        netlify_signature(context="deploy-preview"),
        netlify_signature(context="branch-deploy"),
        netlify_signature(exp=None),
    ],
    ids=["garbage", "wrong-secret", "expired", "wrong-issuer", "deploy-preview", "branch-deploy", "no-expiry"],
)
def test_bad_signatures_are_refused(anon_client, locked, token):
    assert anon_client.get("/students/", headers={"x-nf-sign": token}).status_code == 403


def test_small_clock_skew_is_tolerated(anon_client, locked):
    response = anon_client.get("/students/", headers={"x-nf-sign": netlify_signature(expires_in=-10)})
    assert response.status_code == 401  # through the lock; only the session is missing


def test_failed_sign_ins_log_the_netlify_reported_ip(signed_client, caplog):
    with caplog.at_level(logging.INFO, logger="studytrack"):
        signed_client.post(
            "/auth/login",
            json={"email": MEMBER_EMAIL, "password": "wrong-password"},
            headers={"x-nf-client-connection-ip": "203.0.113.9"},
        )
    assert "Failed sign-in attempt from 203.0.113.9" in caplog.text
    assert MEMBER_EMAIL not in caplog.text


def test_unsigned_ip_headers_are_not_trusted(anon_client, caplog):
    with caplog.at_level(logging.INFO, logger="studytrack"):
        anon_client.post(
            "/auth/login",
            json={"email": MEMBER_EMAIL, "password": "wrong-password"},
            headers={"x-nf-client-connection-ip": "198.51.100.7"},
        )
    assert "198.51.100.7" not in caplog.text
    assert "Failed sign-in attempt from an unverified address" in caplog.text


# --- Request body cap -------------------------------------------------------------------------


def test_declared_oversized_body_is_refused(anon_client):
    response = anon_client.post(
        "/auth/login", content=b"x" * (edge.MAX_BODY_BYTES + 1), headers={"content-type": "application/json"}
    )
    assert response.status_code == 413
    assert response.json() == {"detail": edge.BODY_TOO_LARGE}


def test_streamed_oversized_body_is_refused(anon_client):
    chunks = (b"x" * 65_536 for _ in range(5))  # no Content-Length: sent chunked
    response = anon_client.post("/auth/login", content=chunks, headers={"content-type": "application/json"})
    assert response.status_code == 413


def test_invalid_content_length_is_refused(anon_client):
    response = anon_client.post(
        "/auth/login", content=b"{}", headers={"content-length": "lots", "content-type": "application/json"}
    )
    assert response.status_code == 400


# --- Security headers -------------------------------------------------------------------------


def test_security_headers_are_on_every_response(anon_client, locked):
    for response in (anon_client.get("/health"), anon_client.get("/students/")):
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["x-frame-options"] == "DENY"
        assert "strict-transport-security" not in response.headers


def test_hsts_is_sent_in_production(anon_client, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert anon_client.get("/health").headers["strict-transport-security"].startswith("max-age=31536000")


# --- Password-hashing cap ---------------------------------------------------------------------


class NoFreeSlots:
    def acquire(self, timeout=None):
        return False

    def release(self):
        raise AssertionError("release() must not be called when acquire() failed")


def test_saturated_hashing_answers_503(anon_client, monkeypatch):
    monkeypatch.setattr(auth, "_hashing_slots", NoFreeSlots())
    response = anon_client.post("/auth/login", json={"email": MEMBER_EMAIL, "password": MEMBER_PASSWORD})
    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"


def test_hashing_slots_are_released_after_use(anon_client):
    for password in ("wrong-password", MEMBER_PASSWORD):
        anon_client.post("/auth/login", json={"email": MEMBER_EMAIL, "password": password})
    anon_client.post("/auth/login", json={"email": "nobody@studytrack.test", "password": "whatever"})
    assert auth._hashing_slots._value == auth.MAX_CONCURRENT_HASHES


def test_production_warns_when_the_proxy_secret_is_missing(monkeypatch, caplog):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "k" * 32)
    with caplog.at_level(logging.WARNING, logger="studytrack"):
        auth.check_settings()
    assert "PROXY_SIGNING_SECRET is not set" in caplog.text

    caplog.clear()
    monkeypatch.setenv("PROXY_SIGNING_SECRET", SECRET)
    with caplog.at_level(logging.WARNING, logger="studytrack"):
        auth.check_settings()
    assert "PROXY_SIGNING_SECRET" not in caplog.text
