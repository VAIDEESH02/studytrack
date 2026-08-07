"""Hand-written sorting, searching, and reporting helpers for the live roster."""

from __future__ import annotations

from typing import Any


StudentRecord = dict[str, Any]


def insertion_sort_by_field(students: list[StudentRecord], field: str) -> None:
    """Sort ``students`` in place, ascending, with a hand-written Insertion Sort."""
    for index in range(1, len(students)):
        key = students[index]
        position = index - 1

        # Shift every larger item right until the key belongs at position + 1.
        while position >= 0 and students[position][field] > key[field]:
            students[position + 1] = students[position]
            position -= 1

        students[position + 1] = key


def binary_search_by_name(sorted_by_name_list: list[StudentRecord], name: str) -> StudentRecord | int:
    """Iteratively find an exact name in an alphabetically sorted student list."""
    low = 0
    high = len(sorted_by_name_list) - 1

    while low <= high:
        mid = low + (high - low) // 2
        candidate = sorted_by_name_list[mid]

        if candidate["name"] == name:
            return candidate
        if candidate["name"] < name:
            low = mid + 1
        else:
            high = mid - 1

    return -1


def format_roster_report(students: list[StudentRecord]) -> str:
    """Format one readable roster line per student."""
    lines: list[str] = []
    for student in students:
        lines.append(f"[Age {student['age']}] {student['name']} <{student['email']}>")
    return "\n".join(lines)


def count_students_meeting_min_age(students: list[StudentRecord], min_age: int) -> int:
    """Count students meeting the stated minimum age with a visible accumulator."""
    count = 0
    for student in students:
        if student["age"] >= min_age:
            count += 1
    return count
