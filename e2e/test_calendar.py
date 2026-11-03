"""The calendar in the interface (the module of `pangloss_calendar`): the years of the project's span (`/calendar`, linked
from the navigation bar), a month as a calendar page, and a day; and, for someone logged in, attaching a feast to a day.
The e2e project's `Event` has a date (`when`), `Feast` is a `DateCharacterisation`; the span is 1499 to 1501, Julian."""

import re
import subprocess

from conftest import Stack, environment
from helpers import expand_nav, hydrated
from playwright.sync_api import Page, expect


def test_the_navigation_bar_links_to_the_years_of_the_calendar(page: Page, dated):
    page.goto("/")
    expand_nav(page)
    page.get_by_role("region", name="Links").get_by_role(
        "link", name="Calendar"
    ).click()
    page.wait_for_url("**/calendar")
    expect(page.get_by_role("heading", name=re.compile("^Years"))).to_be_visible()
    rows = page.get_by_test_id("calendar-year")
    expect(rows).to_have_count(3)
    expect(rows.nth(0)).to_contain_text("1499")
    # (the three events are in 1500, and nothing in the other years)
    expect(rows.nth(1).locator("td").first).to_have_text("3")
    expect(rows.nth(0).locator("td").first).to_have_text("0")
    # (each month is a link to its page)
    rows.nth(1).get_by_role("link", name="March 1500").click()
    page.wait_for_url("**/calendar/julian/1500/3")
    expect(page.get_by_role("heading", name=re.compile("^March 1500"))).to_be_visible()


def test_a_month_is_a_calendar_page_with_what_is_dated_on_its_days(page: Page, dated):
    page.goto("/calendar/julian/1500/3")
    hydrated(page)
    month = page.get_by_test_id("calendar-month")
    # 31 days, the 1st a Sunday (Julian), in six rows
    expect(
        month.get_by_role("link", name=re.compile(r"^\d+ March 1500$"))
    ).to_have_count(31)
    expect(month.get_by_test_id("calendar-week")).to_have_count(6)
    # the coronation on the 2nd; the fair, which was on the 4th or the 5th, on each of them as possible
    expect(month.get_by_role("link", name="Coronation")).to_have_count(1)
    fair = month.locator("a[data-mark='possible']", has_text="The fair")
    expect(fair).to_have_count(2)
    # the siege, over eight days, as a bar across two weeks
    bars = month.get_by_test_id("calendar-bar")
    expect(bars).to_have_count(2)
    expect(bars.first).to_have_text("Siege of the town")
    assert bars.first.evaluate("e => e.style.gridColumn") == "2 / span 6"
    assert bars.nth(1).evaluate("e => e.style.gridColumn") == "1 / span 2"
    # the feast by rule on the 21st
    expect(month.get_by_role("link", name="Benedict")).to_have_count(1)
    # a date leads to what it is in
    month.get_by_role("link", name="Coronation").click()
    page.wait_for_url(f"**/Event/{dated.coronation}")
    expect(page.get_by_role("heading", name="Coronation")).to_be_visible()
    page.go_back()
    # the next month, and the same month read in the Gregorian calendar
    page.get_by_role("link", name="Next month").click()
    page.wait_for_url("**/calendar/julian/1500/4")
    expect(page.get_by_role("heading", name=re.compile("^April 1500"))).to_be_visible()
    page.get_by_role("banner", name="Console").get_by_role(
        "link", name="Gregorian"
    ).click()
    page.wait_for_url("**/calendar/gregorian/1500/4")
    # (Gregorian 1500 is not a leap year, and its April starts on another weekday: still 30 days)
    expect(
        page.get_by_test_id("calendar-month").get_by_role(
            "link", name=re.compile(r"^\d+ April 1500$")
        )
    ).to_have_count(30)


def test_a_day_names_itself_in_both_calendars_and_lists_what_is_dated_on_it(
    page: Page, dated
):
    page.goto("/calendar/julian/1500/3/2")
    hydrated(page)
    expect(
        page.get_by_role("heading", name=re.compile("^Monday 2 March 1500"))
    ).to_be_visible()
    expect(page.get_by_test_id("calendar-other-name")).to_have_text(
        "12 March 1500 (Gregorian)"
    )
    on_day = page.get_by_role("region", name="On this day")
    expect(on_day.get_by_role("link", name="Coronation")).to_be_visible()
    expect(on_day).not_to_contain_text("Siege")
    # (nothing by rule or by hand on this day, and no way to attach without a login)
    expect(
        page.get_by_role("region", name="Feasts and characterisations")
    ).to_have_count(0)
    page.get_by_role("link", name="Next day").click()
    page.wait_for_url("**/calendar/julian/1500/3/3")
    expect(
        page.get_by_role("heading", name=re.compile("^Tuesday 3 March 1500"))
    ).to_be_visible()
    expect(
        page.get_by_role("region", name="On this day").get_by_role(
            "link", name="Siege of the town"
        )
    ).to_be_visible()
    # the fair (the 4th or the 5th) and the siege are both on the 4th: each states a range that holds it, so neither is
    # only "possible" (that is for a date whose allowance for doubt alone reaches the day)
    page.get_by_role("link", name="Next day").click()
    page.wait_for_url("**/calendar/julian/1500/3/4")
    rows = page.get_by_role("region", name="On this day").locator("li[data-mark]")
    expect(rows).to_have_count(2)
    expect(rows.filter(has_text="The fair")).to_have_attribute("data-mark", "stated")
    expect(rows.filter(has_text="Siege")).to_have_attribute("data-mark", "stated")
    # the same day under its Gregorian name
    page.get_by_test_id("calendar-other-name").click()
    page.wait_for_url("**/calendar/gregorian/1500/3/14")
    expect(
        page.get_by_role("heading", name=re.compile("^Wednesday 14 March 1500"))
    ).to_be_visible()
    expect(
        page.get_by_role("region", name="On this day").get_by_role(
            "link", name="The fair"
        )
    ).to_be_visible()
    # the feast by rule, on the 21st, says so
    page.goto("/calendar/julian/1500/3/21")
    feasts = page.get_by_role("region", name="Feasts and characterisations")
    expect(feasts.get_by_role("link", name="Benedict")).to_be_visible()
    expect(feasts).to_contain_text("by rule")


def test_someone_logged_in_attaches_a_feast_to_a_day_and_takes_it_away(
    logged_in: Page, dated
):
    page = logged_in
    page.goto("/calendar/julian/1500/3/5")
    hydrated(page)
    feasts = page.get_by_role("region", name="Feasts and characterisations")
    expect(feasts).to_contain_text("None on this day")
    expect(feasts.get_by_role("link", name="New Feast")).to_be_visible()
    page.get_by_label("Attach a characterisation").fill("mark")
    found = page.get_by_role("list", name="Characterisations found")
    expect(found.get_by_role("button")).to_have_count(1)
    found.get_by_role("button", name=re.compile("Market day")).click()
    expect(page.get_by_text("Market day attached")).to_be_visible()
    expect(feasts.get_by_role("link", name="Market day")).to_be_visible()
    expect(feasts).to_contain_text("attached to this day")
    # (the API has it too, as attached by hand)
    on_day = dated.api.ok("GET", "/api/calendar/day/J1500-03-05")
    assert [
        (c["characterisation"]["label"], c["origin"])
        for c in on_day["characterisations"]
    ] == [("Market day", "manual")]
    # it is in the month as well
    page.goto("/calendar/julian/1500/3")
    expect(
        page.get_by_test_id("calendar-month").get_by_role("link", name="Market day")
    ).to_have_count(1)
    page.goto("/calendar/julian/1500/3/5")
    feasts.get_by_role("button", name="Detach").click()
    expect(page.get_by_text("Market day detached")).to_be_visible()
    expect(feasts).to_contain_text("None on this day")
    assert (
        dated.api.ok("GET", "/api/calendar/day/J1500-03-05")["characterisations"] == []
    )


def test_an_address_that_is_not_a_day_is_explained(page: Page, dated):
    page.goto("/calendar/hebrew/1500/3/2")
    expect(page.get_by_role("alert")).to_contain_text("not a day of the calendar")
    page.goto("/calendar/julian/1500/13")
    expect(page.get_by_role("alert")).to_contain_text("not a day of the calendar")


def test_the_calendar_module_tests_pass_in_the_built_project(stack: Stack):
    """The calendar module's own vitest tests and type-check, run where a project builds it (a module has no
    node_modules of its own)"""
    interface = stack.project / ".pangloss" / "interface"
    for command in (
        ["npx", "vitest", "run", "--root", "modules/pangloss_calendar"],
        ["npx", "tsc", "--noEmit", "-p", "modules/pangloss_calendar/tsconfig.json"],
    ):
        done = subprocess.run(
            command,
            cwd=interface,
            env=environment(),
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert done.returncode == 0, (done.stdout + done.stderr)[-3000:]
