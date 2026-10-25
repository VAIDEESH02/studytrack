import pytest
from sqlalchemy.exc import IntegrityError

from backend import crud, schemas
from backend.main import integrity_error_to_http_error
from tests.conftest import find_by_name


def test_list_returns_seeded_courses(client):
    courses = client.get("/courses/").json()
    assert [c["course_name"] for c in courses] == [
        "Retail Foundations",
        "Data Literacy",
        "Fashion Commerce",
        "Customer Experience",
    ]


def test_create_get_patch_delete_course(client):
    rohan = find_by_name(client, "Rohan Mehta")
    created = client.post("/courses/", json={"course_name": "Supply Chain", "credits": 4, "student_id": rohan["id"]})
    assert created.status_code == 201
    course = created.json()
    assert client.get(f"/courses/{course['id']}").json() == course

    meera = find_by_name(client, "Meera Joshi")
    patched = client.patch(f"/courses/{course['id']}", json={"credits": 5, "student_id": meera["id"]})
    assert patched.status_code == 200
    assert patched.json() == {**course, "credits": 5, "student_id": meera["id"]}

    assert client.delete(f"/courses/{course['id']}").status_code == 204
    assert client.get(f"/courses/{course['id']}").status_code == 404


def test_create_rejects_unknown_student_with_422(client):
    response = client.post("/courses/", json={"course_name": "X", "credits": 2, "student_id": 999999})
    assert response.status_code == 422
    assert response.json()["detail"] == "student_id must reference an existing student"


def test_patch_rejects_unknown_student(client):
    course = client.get("/courses/").json()[0]
    response = client.patch(f"/courses/{course['id']}", json={"student_id": 999999})
    assert response.status_code == 422


@pytest.mark.parametrize("credits", [0, 7])
def test_credits_must_be_between_1_and_6(client, credits):
    rohan = find_by_name(client, "Rohan Mehta")
    response = client.post("/courses/", json={"course_name": "X", "credits": credits, "student_id": rohan["id"]})
    assert response.status_code == 422


def test_database_check_constraint_also_guards_credits(db):
    student_id = crud.list_students(db)[0].id
    bad = schemas.CourseCreate.model_construct(course_name="Bypass", credits=9, student_id=student_id)
    with pytest.raises(IntegrityError) as caught:
        crud.create_course(db, bad)
    error = integrity_error_to_http_error(db, caught.value)
    assert (error.status_code, error.detail) == (422, "credits must be between 1 and 6")


def test_unknown_course_ids(client):
    assert client.get("/courses/999999").status_code == 404
    assert client.patch("/courses/999999", json={"credits": 2}).status_code == 404
    assert client.delete("/courses/999999").status_code == 404
