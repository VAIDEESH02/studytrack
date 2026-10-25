from backend import algorithms
from backend.seed_data import SEED_STUDENTS


def roster():
    return [{"id": index + 1, **student} for index, student in enumerate(SEED_STUDENTS)]


def test_insertion_sort_by_age_matches_documented_order():
    students = roster()
    algorithms.insertion_sort_by_field(students, "age")
    assert [s["name"] for s in students] == [
        "Farhan Sheikh",
        "Rohan Mehta",
        "Meera Joshi",
        "Priya Iyer",
        "Aditi Rao",
        "Devansh Gupta",
        "Sameer Khan",
        "Kavya Nair",
    ]


def test_insertion_sort_by_name_is_alphabetical_and_in_place():
    students = roster()
    result = algorithms.insertion_sort_by_field(students, "name")
    assert result is None
    assert [s["name"] for s in students] == sorted(s["name"] for s in SEED_STUDENTS)


def test_insertion_sort_is_stable_for_equal_keys():
    students = [{"name": "B", "age": 20}, {"name": "A", "age": 20}, {"name": "C", "age": 19}]
    algorithms.insertion_sort_by_field(students, "age")
    assert [s["name"] for s in students] == ["C", "B", "A"]


def test_insertion_sort_handles_empty_and_single_lists():
    empty: list[dict] = []
    algorithms.insertion_sort_by_field(empty, "age")
    single = [{"name": "A", "age": 1}]
    algorithms.insertion_sort_by_field(single, "age")
    assert empty == [] and single == [{"name": "A", "age": 1}]


def test_binary_search_finds_exact_name():
    by_name = sorted(roster(), key=lambda s: s["name"])
    assert algorithms.binary_search_by_name(by_name, "Priya Iyer")["email"] == "priya.iyer@example.com"
    assert algorithms.binary_search_by_name(by_name, "Aditi Rao")["name"] == "Aditi Rao"
    assert algorithms.binary_search_by_name(by_name, "Sameer Khan")["name"] == "Sameer Khan"


def test_binary_search_is_exact_and_case_sensitive():
    by_name = sorted(roster(), key=lambda s: s["name"])
    assert algorithms.binary_search_by_name(by_name, "priya iyer") == -1
    assert algorithms.binary_search_by_name(by_name, "Nobody") == -1
    assert algorithms.binary_search_by_name([], "Priya Iyer") == -1


def test_roster_report_has_one_line_per_student():
    report = algorithms.format_roster_report(roster())
    lines = report.split("\n")
    assert len(lines) == len(SEED_STUDENTS)
    assert lines[0] == "[Age 22] Aditi Rao <aditi.rao@example.com>"


def test_count_meeting_min_age_uses_inclusive_threshold():
    assert algorithms.count_students_meeting_min_age(roster(), 21) == 5
    assert algorithms.count_students_meeting_min_age(roster(), 0) == 8
    assert algorithms.count_students_meeting_min_age(roster(), 100) == 0
