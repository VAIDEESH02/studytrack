import re
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from backend import auth
from backend.main import app
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, MEMBER_EMAIL, MEMBER_PASSWORD, sign_in

PUBLIC_ROUTES = {("GET", "/health"), ("POST", "/auth/login"), ("POST", "/auth/logout")}


def api_routes():
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in sorted(route.methods):
                yield method, route.path


def cookie_attributes(set_cookie: str) -> set[str]:
    return {part.strip().split("=")[0].lower() for part in set_cookie.split(";")[1:]}


def test_every_non_public_route_requires_sign_in(anon_client):
    """Fails if someone adds a route outside the protected routers."""
    checked = []
    for method, path in api_routes():
        if (method, path) in PUBLIC_ROUTES:
            continue
        url = re.sub(r"\{[^}]+\}", "1", path)
        response = anon_client.request(method, url)
        assert response.status_code == 401, f"{method} {path} answered {response.status_code} without a session"
        checked.append((method, path))
    assert len(checked) >= 21


def test_public_routes_exist():
    assert PUBLIC_ROUTES <= set(api_routes())


def test_health_is_public_and_reports_version(anon_client, monkeypatch):
    assert anon_client.get("/health").json() == {"status": "ok", "version": "dev"}
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc123")
    assert anon_client.get("/health").json()["version"] == "abc123"


def test_login_sets_httponly_lax_cookie_and_hides_password_hash(anon_client):
    response = anon_client.post("/auth/login", json={"email": ADMIN_EMAIL.upper(), "password": ADMIN_PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == ADMIN_EMAIL and body["role"] == "admin"
    assert "password_hash" not in body
    assert body["last_login_at"] is not None and body["last_login_at"].endswith(("Z", "+00:00"))
    set_cookie = response.headers["set-cookie"]
    assert set_cookie.startswith(f"{auth.SESSION_COOKIE}=")
    assert {"httponly", "samesite", "path", "max-age"} <= cookie_attributes(set_cookie)
    assert "samesite=lax" in set_cookie.lower()
    assert "secure" not in cookie_attributes(set_cookie)  # local http development


def test_cookie_is_secure_in_production(anon_client, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    response = anon_client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert "secure" in cookie_attributes(response.headers["set-cookie"])


@pytest.mark.parametrize(
    ("email", "password"),
    [(ADMIN_EMAIL, "wrong-password"), ("nobody@studytrack.test", ADMIN_PASSWORD)],
)
def test_bad_credentials_get_one_generic_message(anon_client, email, password):
    response = anon_client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"
    assert "set-cookie" not in response.headers


def test_me_and_logout(member_client):
    assert member_client.get("/auth/me").json()["email"] == MEMBER_EMAIL
    response = member_client.post("/auth/logout")
    assert response.status_code == 204
    assert "max-age=0" in response.headers["set-cookie"].lower()
    assert member_client.get("/auth/me").status_code == 401


def test_logout_is_safe_when_signed_out(anon_client):
    assert anon_client.post("/auth/logout").status_code == 204


def test_repeated_failures_lock_the_email(anon_client):
    for _ in range(5):
        assert anon_client.post("/auth/login", json={"email": MEMBER_EMAIL, "password": "nope"}).status_code == 401
    locked = anon_client.post("/auth/login", json={"email": MEMBER_EMAIL, "password": MEMBER_PASSWORD})
    assert locked.status_code == 429
    assert int(locked.headers["retry-after"]) > 0
    assert "Too many failed sign-in attempts" in locked.json()["detail"]
    # Other accounts are unaffected.
    assert anon_client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}).status_code == 200


def test_successful_login_resets_failure_count(anon_client):
    for _ in range(4):
        anon_client.post("/auth/login", json={"email": MEMBER_EMAIL, "password": "nope"})
    assert anon_client.post("/auth/login", json={"email": MEMBER_EMAIL, "password": MEMBER_PASSWORD}).status_code == 200
    for _ in range(4):
        assert anon_client.post("/auth/login", json={"email": MEMBER_EMAIL, "password": "nope"}).status_code == 401


def test_throttle_window_expires(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: clock[0])
    throttle = auth.LoginThrottle(max_failures=2, window_seconds=60)
    throttle.record_failure("a")
    throttle.record_failure("a")
    assert throttle.retry_after("a") == 60
    clock[0] += 59.5
    assert throttle.retry_after("a") == 1
    clock[0] += 0.5
    assert throttle.retry_after("a") == 0


def forge(payload: dict, key: str | None = None) -> str:
    return jwt.encode(payload, key or auth.secret_key(), algorithm="HS256")


@pytest.mark.parametrize(
    "make_token",
    [
        lambda uid: "not-a-jwt",
        lambda uid: forge(
            {"sub": str(uid), "ver": 0, "iat": datetime.now(UTC), "exp": datetime.now(UTC) - timedelta(seconds=1)}
        ),
        lambda uid: forge(
            {"sub": str(uid), "ver": 0, "iat": datetime.now(UTC), "exp": datetime.now(UTC) + timedelta(hours=1)},
            "another-key-" + "y" * 40,
        ),
        lambda uid: forge({"sub": str(uid), "iat": datetime.now(UTC), "exp": datetime.now(UTC) + timedelta(hours=1)}),
        lambda uid: forge(
            {"sub": "abc", "ver": 0, "iat": datetime.now(UTC), "exp": datetime.now(UTC) + timedelta(hours=1)}
        ),
        lambda uid: forge(
            {"sub": "999999", "ver": 0, "iat": datetime.now(UTC), "exp": datetime.now(UTC) + timedelta(hours=1)}
        ),
    ],
    ids=["garbage", "expired", "wrong-key", "missing-ver", "non-numeric-sub", "unknown-user"],
)
def test_invalid_session_tokens_are_rejected(admin_client, anon_client, make_token):
    admin_id = admin_client.get("/auth/me").json()["id"]
    anon_client.cookies.set(auth.SESSION_COOKIE, make_token(admin_id))
    assert anon_client.get("/auth/me").status_code == 401


def test_deactivating_a_user_ends_their_existing_session(admin_client, member_client):
    member_id = member_client.get("/auth/me").json()["id"]
    assert admin_client.patch(f"/users/{member_id}", json={"is_active": False}).status_code == 200
    assert member_client.get("/students/").status_code == 401
    retry = TestClient(app).post("/auth/login", json={"email": MEMBER_EMAIL, "password": MEMBER_PASSWORD})
    assert retry.status_code == 401


def test_change_password_signs_out_other_sessions_but_keeps_this_one(db_state):
    this_device = sign_in(TestClient(app), MEMBER_EMAIL, MEMBER_PASSWORD)
    other_device = sign_in(TestClient(app), MEMBER_EMAIL, MEMBER_PASSWORD)
    response = this_device.post(
        "/auth/change-password", json={"current_password": MEMBER_PASSWORD, "new_password": "a-brand-new-password"}
    )
    assert response.status_code == 204
    assert this_device.get("/auth/me").status_code == 200
    assert other_device.get("/auth/me").status_code == 401
    old = TestClient(app).post("/auth/login", json={"email": MEMBER_EMAIL, "password": MEMBER_PASSWORD})
    assert old.status_code == 401
    sign_in(TestClient(app), MEMBER_EMAIL, "a-brand-new-password")


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        ({"current_password": "wrong-password", "new_password": "another-good-password"}, 400),
        ({"current_password": MEMBER_PASSWORD, "new_password": MEMBER_PASSWORD}, 422),
        ({"current_password": MEMBER_PASSWORD, "new_password": "short"}, 422),
    ],
)
def test_change_password_validation(member_client, payload, status):
    assert member_client.post("/auth/change-password", json=payload).status_code == status


def test_check_settings(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "k" * 32)
    auth.check_settings()

    monkeypatch.setenv("SECRET_KEY", "too-short")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        auth.check_settings()

    monkeypatch.setenv("SECRET_KEY", "k" * 32)
    monkeypatch.setenv("COOKIE_SECURE", "false")
    with pytest.raises(RuntimeError, match="COOKIE_SECURE"):
        auth.check_settings()


def test_secret_key_is_required_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("SECRET_KEY")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        auth.secret_key()


def test_development_without_secret_key_uses_temporary_key(monkeypatch, caplog):
    monkeypatch.delenv("SECRET_KEY")
    auth.check_settings()
    assert "temporary key" in caplog.text
    assert len(auth.secret_key()) >= auth.MIN_SECRET_KEY_LENGTH
