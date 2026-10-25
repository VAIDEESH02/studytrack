from backend.seed_data import SEED_STUDENTS
from tests.conftest import find_by_name


def test_list_returns_seeded_roster_in_id_order(client):
    response = client.get("/students/")
    assert response.status_code == 200
    assert [s["name"] for s in response.json()] == [s["name"] for s in SEED_STUDENTS]


def test_list_filters_by_min_age(client):
    ages = [s["age"] for s in client.get("/students/", params={"min_age": 22}).json()]
    assert ages and all(age >= 22 for age in ages)
    assert len(ages) == 4


def test_create_student_trims_input_and_returns_201(client):
    response = client.post("/students/", json={"name": "  Nila  ", "email": "nila@myntra.com", "age": 21})
    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "Nila"
    assert client.get(f"/students/{created['id']}").json() == created


def test_create_rejects_duplicate_email_with_409(client):
    response = client.post("/students/", json={"name": "Copy", "email": "aditi.rao@example.com", "age": 30})
    assert response.status_code == 409
    assert response.json()["detail"] == "A student with that email already exists"


def test_create_validates_fields(client):
    cases = [
        {"name": "   ", "email": "a@b.c", "age": 20},
        {"name": "A", "email": "no-at-sign", "age": 20},
        {"name": "A", "email": "a@b.c", "age": 0},
        {"name": "A", "email": "a@b.c", "age": 151},
        {"name": "A" * 121, "email": "a@b.c", "age": 20},
    ]
    for payload in cases:
        assert client.post("/students/", json=payload).status_code == 422, payload


def test_get_unknown_or_out_of_range_student(client):
    assert client.get("/students/999999").status_code == 404
    assert client.get("/students/99999999999").status_code == 422
    assert client.get("/students/0").status_code == 422


def test_patch_updates_only_sent_fields(client):
    aditi = find_by_name(client, "Aditi Rao")
    response = client.patch(f"/students/{aditi['id']}", json={"age": 23})
    assert response.status_code == 200
    assert response.json() == {**aditi, "age": 23}


def test_patch_ignores_explicit_nulls(client):
    aditi = find_by_name(client, "Aditi Rao")
    response = client.patch(f"/students/{aditi['id']}", json={"name": None, "age": 24})
    assert response.status_code == 200
    assert response.json()["name"] == "Aditi Rao"


def test_patch_rejects_duplicate_email_and_unknown_id(client):
    aditi = find_by_name(client, "Aditi Rao")
    response = client.patch(f"/students/{aditi['id']}", json={"email": "priya.iyer@example.com"})
    assert response.status_code == 409
    assert client.patch("/students/999999", json={"age": 30}).status_code == 404


def test_delete_removes_student_and_cascades_courses(client):
    aditi = find_by_name(client, "Aditi Rao")
    assert client.get(f"/students/{aditi['id']}/course-count").json()["course_count"] == 2
    assert client.delete(f"/students/{aditi['id']}").status_code == 204
    assert client.get(f"/students/{aditi['id']}").status_code == 404
    assert all(course["student_id"] != aditi["id"] for course in client.get("/courses/").json())
    assert client.delete(f"/students/{aditi['id']}").status_code == 404


def test_sorted_by_age_and_name(client):
    by_age = client.get("/students/sorted", params={"by": "age"}).json()
    assert [s["age"] for s in by_age] == sorted(s["age"] for s in SEED_STUDENTS)
    by_name = client.get("/students/sorted", params={"by": "name"}).json()
    assert [s["name"] for s in by_name] == sorted(s["name"] for s in SEED_STUDENTS)
    assert client.get("/students/sorted").json() == by_age


def test_sorted_rejects_unknown_field(client):
    response = client.get("/students/sorted", params={"by": "email"})
    assert response.status_code == 422
    assert response.json()["detail"] == "by must be age or name"


def test_search_finds_exact_name_only(client):
    response = client.get("/students/search", params={"name": "Priya Iyer"})
    assert response.status_code == 200
    assert response.json()["email"] == "priya.iyer@example.com"
    assert client.get("/students/search", params={"name": "priya iyer"}).status_code == 404


def test_report_lists_every_student_and_counts_min_age(client):
    body = client.get("/students/report").json()
    assert body["count_meeting_min_age"] == 5
    assert len(body["report"].split("\n")) == len(SEED_STUDENTS)
    assert client.get("/students/report", params={"min_age": 25}).json()["count_meeting_min_age"] == 1


def test_course_count(client):
    aditi = find_by_name(client, "Aditi Rao")
    rohan = find_by_name(client, "Rohan Mehta")
    assert client.get(f"/students/{aditi['id']}/course-count").json() == {"student_id": aditi["id"], "course_count": 2}
    assert client.get(f"/students/{rohan['id']}/course-count").json()["course_count"] == 0
    assert client.get("/students/999999/course-count").status_code == 404
