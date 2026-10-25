import pytest
from fastapi.testclient import TestClient

from backend.main import app
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, MEMBER_EMAIL, sign_in


def user_id(client: TestClient, email: str) -> int:
    return next(u["id"] for u in client.get("/users/").json() if u["email"] == email)


def test_members_cannot_manage_users(member_client):
    assert member_client.get("/users/").status_code == 403
    assert (
        member_client.post("/users/", json={"email": "x@y.z", "full_name": "X", "password": "x" * 12}).status_code
        == 403
    )
    assert member_client.patch("/users/1", json={"full_name": "X"}).status_code == 403


def test_admin_lists_users_without_password_hashes(admin_client):
    users = admin_client.get("/users/").json()
    assert {u["email"] for u in users} == {ADMIN_EMAIL, MEMBER_EMAIL}
    assert all("password_hash" not in u for u in users)


def test_admin_creates_user_who_can_sign_in(admin_client):
    response = admin_client.post(
        "/users/",
        json={"email": "  New.Person@Myntra.com ", "full_name": "New Person", "password": "temporary-pass-1"},
    )
    assert response.status_code == 201
    created = response.json()
    assert created["email"] == "new.person@myntra.com"
    assert created["role"] == "member" and created["is_active"] is True and created["last_login_at"] is None
    sign_in(TestClient(app), "new.person@myntra.com", "temporary-pass-1")


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        ({"email": MEMBER_EMAIL.upper(), "full_name": "Dup", "password": "x" * 12}, 409),
        ({"email": "a@b.c", "full_name": "Short", "password": "x" * 11}, 422),
        ({"email": "a@b.c", "full_name": "Role", "password": "x" * 12, "role": "owner"}, 422),
        ({"email": "no-at-sign", "full_name": "Email", "password": "x" * 12}, 422),
    ],
)
def test_create_user_validation(admin_client, payload, status):
    assert admin_client.post("/users/", json=payload).status_code == status


def test_admin_edits_name_and_role(admin_client):
    member = user_id(admin_client, MEMBER_EMAIL)
    response = admin_client.patch(f"/users/{member}", json={"full_name": "Max Promoted", "role": "admin"})
    assert response.status_code == 200
    assert (response.json()["full_name"], response.json()["role"]) == ("Max Promoted", "admin")


def test_role_change_signs_the_user_out(admin_client, member_client):
    member = user_id(admin_client, MEMBER_EMAIL)
    admin_client.patch(f"/users/{member}", json={"role": "admin"})
    assert member_client.get("/auth/me").status_code == 401


def test_name_change_keeps_the_user_signed_in(admin_client, member_client):
    member = user_id(admin_client, MEMBER_EMAIL)
    admin_client.patch(f"/users/{member}", json={"full_name": "Renamed"})
    assert member_client.get("/auth/me").json()["full_name"] == "Renamed"


def test_admin_resets_a_password(admin_client, member_client):
    member = user_id(admin_client, MEMBER_EMAIL)
    assert admin_client.patch(f"/users/{member}", json={"password": "reset-by-admin-1"}).status_code == 200
    assert member_client.get("/auth/me").status_code == 401
    sign_in(TestClient(app), MEMBER_EMAIL, "reset-by-admin-1")


def test_admin_resetting_own_password_stays_signed_in(admin_client):
    me = user_id(admin_client, ADMIN_EMAIL)
    assert admin_client.patch(f"/users/{me}", json={"password": "my-new-admin-pass"}).status_code == 200
    assert admin_client.get("/auth/me").status_code == 200
    assert (
        TestClient(app).post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}).status_code == 401
    )


@pytest.mark.parametrize(
    ("payload", "message"),
    [({"is_active": False}, "deactivate your own account"), ({"role": "member"}, "remove your own administrator role")],
)
def test_admin_cannot_lock_themselves_out(admin_client, payload, message):
    me = user_id(admin_client, ADMIN_EMAIL)
    response = admin_client.patch(f"/users/{me}", json=payload)
    assert response.status_code == 422
    assert message in response.json()["detail"]


def test_reactivating_a_user(admin_client):
    member = user_id(admin_client, MEMBER_EMAIL)
    admin_client.patch(f"/users/{member}", json={"is_active": False})
    assert admin_client.patch(f"/users/{member}", json={"is_active": True}).json()["is_active"] is True


def test_patch_unknown_user(admin_client):
    assert admin_client.patch("/users/999999", json={"full_name": "X"}).status_code == 404
