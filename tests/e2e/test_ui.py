import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import E2E_EMAIL, E2E_PASSWORD

pytestmark = pytest.mark.e2e


def sign_in(page: Page, app_url: str, password: str = E2E_PASSWORD) -> None:
    page.get_by_label("Email").fill(E2E_EMAIL)
    page.get_by_label("Password", exact=True).fill(password)
    page.get_by_role("button", name="Sign in").click()


def go_to(page: Page, section: str) -> None:
    page.get_by_role("navigation", name="Main").get_by_role("link", name=section).click()
    expect(page.locator("#page-title")).to_have_text(section)


def test_sign_in_is_required_and_returns_to_the_requested_page(page: Page, app_url: str):
    page.goto(f"{app_url}/#/courses")
    expect(page).to_have_url(re.compile(r"/login\.html\?next=%23%2Fcourses$"))
    expect(page.locator("#auth-notice")).to_be_hidden()

    sign_in(page, app_url, password="definitely-wrong")
    expect(page.locator("#login-error")).to_have_text("Invalid email or password")

    sign_in(page, app_url)
    expect(page).to_have_url(re.compile(r"/index\.html#/courses$"))
    expect(page.get_by_role("heading", name="Course enrollments")).to_be_visible()


def test_full_workflow(page: Page, app_url: str):
    page.goto(f"{app_url}/")
    sign_in(page, app_url)
    # Any admin name: the self-started servers use "Eve Tester", the Docker stack its own.
    expect(page.get_by_role("heading", name=re.compile(r"^Welcome back, \S+"))).to_be_visible()
    expect(page.locator(".stat", has=page.get_by_text("Trainees", exact=True))).to_contain_text("8")

    # Add a trainee, then try a duplicate email.
    go_to(page, "Trainees")
    page.get_by_role("button", name="Add trainee").click()
    dialog = page.get_by_role("dialog", name="Add a trainee")
    dialog.get_by_label("Full name").fill("Nila Raman")
    dialog.get_by_label("Email").fill("nila.raman@myntra.com")
    dialog.get_by_label("Age").fill("21")
    dialog.get_by_role("button", name="Add trainee").click()
    expect(page.locator(".toast").filter(has_text="Added Nila Raman")).to_be_visible()
    row = page.get_by_role("row").filter(has_text="Nila Raman")
    expect(row).to_be_visible()

    page.get_by_role("button", name="Add trainee").click()
    dialog = page.get_by_role("dialog", name="Add a trainee")
    dialog.get_by_label("Full name").fill("Someone Else")
    dialog.get_by_label("Email").fill("nila.raman@myntra.com")
    dialog.get_by_label("Age").fill("30")
    dialog.get_by_role("button", name="Add trainee").click()
    expect(dialog.get_by_text("A student with that email already exists")).to_be_visible()
    dialog.get_by_role("button", name="Cancel").click()

    # Edit the age.
    page.get_by_role("button", name="Edit Nila Raman").click()
    dialog = page.get_by_role("dialog", name="Edit Nila Raman")
    dialog.get_by_label("Age").fill("22")
    dialog.get_by_role("button", name="Save changes").click()
    expect(row.get_by_role("cell", name="22", exact=True)).to_be_visible()

    # Server-side insertion sort.
    page.get_by_label("Sort by").select_option("age")
    expect(page.get_by_text("Sorted by the server with insertion sort.")).to_be_visible()
    expect(page.locator("tbody tr").first).to_contain_text("Farhan Sheikh")

    # Binary-search lookup opens the detail panel; add a course there.
    page.get_by_label("Exact name lookup").fill("Nila Raman")
    page.get_by_role("button", name="Find").click()
    drawer = page.get_by_role("dialog", name="Nila Raman")
    expect(drawer.get_by_text("0 courses")).to_be_visible()
    drawer.get_by_role("button", name="Add course").click()
    course_dialog = page.get_by_role("dialog", name="Add a course enrollment")
    course_dialog.get_by_label("Course name").fill("Supply Chain Basics")
    course_dialog.get_by_label("Credits").fill("4")
    course_dialog.get_by_role("button", name="Add course").click()
    expect(drawer.get_by_text("Supply Chain Basics")).to_be_visible()
    expect(drawer.get_by_text("1 course", exact=True)).to_be_visible()
    drawer.get_by_role("button", name="Close panel").click()

    go_to(page, "Courses")
    expect(page.get_by_role("row").filter(has_text="Supply Chain Basics")).to_contain_text("Nila Raman")

    # Deleting the trainee warns about the enrollment and removes both.
    go_to(page, "Trainees")
    page.get_by_role("button", name="Delete Nila Raman").click()
    confirm = page.get_by_role("dialog", name="Delete Nila Raman?")
    expect(confirm).to_contain_text("also removes 1 course enrollment")
    confirm.get_by_role("button", name="Delete trainee").click()
    expect(page.get_by_role("row").filter(has_text="Nila Raman")).to_have_count(0)

    go_to(page, "Reports")
    expect(page.locator(".stat").filter(has_text="Trainees aged 21 or older")).to_contain_text("5")
    expect(page.get_by_label("Roster report")).to_contain_text("[Age 22] Aditi Rao <aditi.rao@example.com>")

    go_to(page, "AI Helper")
    page.get_by_role("button", name="Use sample notes").click()
    page.get_by_role("button", name="Summarize").click()
    expect(page.get_by_role("heading", name="Binary Search")).to_be_visible()
    expect(page.get_by_text(re.compile(r"Difficulty: (easy|medium|hard)"))).to_be_visible()
    page.get_by_role("button", name="binary search").click()
    expect(page.locator(".result").first).to_contain_text("Note 1")

    # Administrators manage who can sign in.
    go_to(page, "Users")
    page.get_by_role("button", name="Add user").click()
    dialog = page.get_by_role("dialog", name="Add a user")
    dialog.get_by_label("Full name").fill("Max Member")
    dialog.get_by_label("Email").fill("max.member@myntra.com")
    dialog.get_by_role("button", name="Add user").click()
    credentials = page.get_by_role("dialog", name="Share these sign-in details")
    expect(credentials).to_contain_text("max.member@myntra.com")
    credentials.get_by_role("button", name="Done").click()
    expect(page.get_by_role("row").filter(has_text="Max Member")).to_contain_text("Active")

    # Sign out ends the session.
    page.get_by_role("button", name="Account menu").click()
    page.get_by_role("button", name="Sign out").click()
    expect(page.locator("#auth-notice")).to_have_text("You've been signed out.")
    page.goto(f"{app_url}/#/dashboard")
    expect(page).to_have_url(re.compile(r"/login\.html"))


def test_phone_layout_has_bottom_tabs_and_no_horizontal_scroll(page: Page, app_url: str):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{app_url}/#/trainees")
    sign_in(page, app_url)
    expect(page.get_by_role("row").filter(has_text="Aditi Rao")).to_be_visible()
    nav_box = page.get_by_role("navigation", name="Main").bounding_box()
    assert nav_box and nav_box["y"] > 844 - 120, "navigation should sit at the bottom on phones"
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
