"""Dates in a form and on a page (the interface module of `pangloss_dates`): the kind of date is chosen first, an exact
date is three boxes, EDTF is one, a period has a start and an end, and each is said back as a person would say it
("Reads"), in the form and on the item's page. (A range with an end not known is in test_dateable.py; a recurrence, the
rule of a feast, in test_calendar.py.)"""

import re

from helpers import hydrated
from playwright.sync_api import Page, expect


def new_event(page: Page, label: str, kind: str) -> None:
    page.goto("/Event/new")
    hydrated(page)
    page.get_by_label("Label", exact=True).fill(label)
    page.get_by_label("Text", exact=True).fill("It happened")
    page.get_by_role("button", name="Add When").click()
    # (the kinds of date there are, by name)
    chooser = page.get_by_role("group", name="Add When")
    expect(chooser.get_by_role("button").filter(has_not_text="✕")).to_have_text(
        ["Date range", "EDTF date", "Exact date", "Ongoing date", "Period", "Recurrence", "Unknown date"]
    )
    chooser.get_by_role("button", name=kind, exact=True).click()


def save(page: Page) -> dict:
    with page.expect_response(
        lambda response: response.request.method == "POST" and response.url.endswith("/api/Event")
    ) as answer:
        page.get_by_role("button", name="Save").click()
    assert answer.value.ok, answer.value.text()
    return answer.value.json()


def test_an_exact_date_is_a_year_a_month_and_a_day_and_reads_as_it_is_said(logged_in: Page, types):
    page = logged_in
    new_event(page, "The coronation", "Exact date")
    reads = page.get_by_test_id("date-reads")
    # (nothing to read until there is a year)
    expect(reads).to_have_count(0)
    page.get_by_role("spinbutton", name="When Year").fill("1500")
    expect(reads).to_contain_text("1500")
    # (a day cannot be given before its month)
    page.get_by_label("When Month").select_option(label="March")
    expect(reads).to_contain_text("March 1500")
    page.get_by_role("spinbutton", name="When Day").fill("2")
    expect(reads).to_contain_text("2 March 1500")

    made = save(page)
    saved = types.admin().ok("GET", f"/api/Event/{made['id']}")["when"]
    assert (saved["type"], saved["year"], saved["month"], saved["day"]) == ("ExactDate", 1500, 3, 2), saved
    # (on its page the date is said, not listed field by field)
    expect(page.get_by_role("heading", level=1, name="The coronation")).to_be_visible()
    main = page.locator("main")
    expect(main).to_contain_text("2 March 1500 (Julian)")
    expect(main.locator("dt", has_text=re.compile("^(year|month|day)$", re.I))).to_have_count(0)

    # (and the form of the saved event has it again)
    page.goto(f"/Event/{made['id']}/edit")
    hydrated(page)
    expect(page.get_by_role("spinbutton", name="When Year")).to_have_value("1500")
    expect(page.get_by_role("spinbutton", name="When Day")).to_have_value("2")
    expect(page.get_by_test_id("date-reads")).to_contain_text("2 March 1500")


def test_an_edtf_date_is_one_box_that_takes_only_what_edtf_has(logged_in: Page, types):
    page = logged_in
    new_event(page, "About then", "EDTF date")
    box = page.get_by_label("When EDTF")
    # (letters that are not EDTF's are not taken; a small x is made a capital, an unspecified digit)
    box.press_sequentially("15xx")
    expect(box).to_have_value("15XX")
    box.fill("")
    box.press_sequentially("1500-03~")
    expect(box).to_have_value("1500-03~")
    # (EDTF is said as it is written: it is the server that reads it)
    expect(page.get_by_test_id("date-reads")).to_contain_text("1500-03~")
    made = save(page)
    saved = types.admin().ok("GET", f"/api/Event/{made['id']}")["when"]
    assert (saved["type"], saved["edtf"]) == ("EDTFDate", "1500-03~"), saved
    expect(page.locator("main")).to_contain_text("1500-03~ (Julian)")


def test_a_date_that_is_required_and_left_out_is_said_at_its_field(logged_in: Page, types):
    page = logged_in
    page.goto("/Event/new")
    hydrated(page)
    page.get_by_label("Label", exact=True).fill("No date")
    page.get_by_label("Text", exact=True).fill("It happened")
    page.get_by_role("button", name="Save").click()
    # (nothing is sent: still the form, with the field marked)
    expect(page).to_have_url(re.compile(r"/Event/new$"))
    expect(page.get_by_role("status", name="Notifications")).to_be_visible()
    expect(page.get_by_role("button", name="Add When")).to_be_visible()
    expect(page.get_by_role("status", name="Notifications")).to_contain_text(
        "Not saved: a field has a problem, marked in red"
    )
    expect(page.locator("main dt", has_text="When")).to_contain_text("Required")
    # (given, the mark goes)
    page.get_by_role("button", name="Add When").click()
    page.get_by_role("group", name="Add When").get_by_role("button", name="Unknown date", exact=True).click()
    expect(page.locator("main dt", has_text="When").first).not_to_contain_text("Required")


def test_an_unknown_date_has_nothing_to_fill_in_and_the_calendar_is_chosen(logged_in: Page, types):
    page = logged_in
    new_event(page, "Sometime", "Unknown date")
    # (nothing to fill in, and it reads as that)
    expect(page.get_by_role("spinbutton", name="When Year")).to_have_count(0)
    expect(page.get_by_test_id("date-reads")).to_contain_text("unknown")
    made = save(page)
    assert types.admin().ok("GET", f"/api/Event/{made['id']}")["when"]["type"] == "UnknownDate"

    # (the calendar of a date is the project's, Julian here, unless another is chosen for it)
    new_event(page, "By the new style", "Exact date")
    page.get_by_role("spinbutton", name="When Year").fill("1499")
    calendar = page.get_by_role("radiogroup", name="Calendar")
    calendar.get_by_role("radio", name="Gregorian").check()
    made = save(page)
    saved = types.admin().ok("GET", f"/api/Event/{made['id']}")["when"]
    assert (saved["type"], saved["year"], saved["calendar"]) == ("ExactDate", 1499, "gregorian"), saved
    # (a calendar is named only when it is not the Gregorian, whatever the project's own is: `format.ts`)
    expect(page.locator("main dd").last).to_have_text("1499")
