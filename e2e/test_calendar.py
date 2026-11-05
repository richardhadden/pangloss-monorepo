"""The calendar in the interface (the module of `pangloss_calendar`): the years of the project's span (`/calendar`, linked
from the navigation bar), a month as a calendar page, and a day; and, for someone logged in, attaching a feast to a day.
The e2e project's `Event` has a date (`when`), `Feast` is a `DateCharacterisation`; the span is 1499 to 1501, Julian."""

import re
import subprocess

from conftest import USERNAME, Stack, environment
from helpers import expand_nav, hydrated
from playwright.sync_api import Page, expect
from test_login import log_in_through_the_dialog


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
    # (the four events are in 1500, and nothing in the other years)
    # (at the end of each row: the number in a circle, then "events")
    expect(rows.nth(1).get_by_test_id("calendar-year-count")).to_have_text("4events")
    expect(rows.nth(0).get_by_test_id("calendar-year-count")).to_have_text("0events")
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
    # the coronation on the 2nd, a chip of its type and label; the fair, one day on the 4th or the 5th, as a hollow bar between
    # them, not on either
    expect(month.get_by_role("link", name="Event Coronation")).to_have_count(1)
    expect(month.locator("a[data-mark]", has_text="The fair")).to_have_count(0)
    fair = month.locator("[data-testid='calendar-bar'][data-between='true']")
    expect(fair).to_have_count(1)
    expect(fair).to_have_text(re.compile(r"^Event\s*The fair$"))
    assert fair.evaluate("e => e.style.gridColumn") == "3 / span 2"
    expect(fair).to_have_attribute(
        "title", re.compile("between 4 March 1500 and 5 March 1500")
    )
    # the siege, a period of eight days, as a filled bar across two weeks
    bars = month.locator("[data-testid='calendar-bar']:not([data-between])")
    expect(bars).to_have_count(2)
    expect(bars.first).to_have_text(re.compile(r"^Event\s*Siege of the town$"))
    assert bars.first.evaluate("e => e.style.gridColumn") == "2 / span 6"
    assert bars.nth(1).evaluate("e => e.style.gridColumn") == "1 / span 2"
    # the birth, sometime in 1500, is not drawn on the days but listed under the grid
    expect(month.get_by_role("link", name=re.compile("Birth of Alcuin"))).to_have_count(
        0
    )
    roughly = page.get_by_test_id("calendar-roughly")
    expect(roughly).to_have_count(1)
    # (the field, then a chip of what it is in: its type and its label)
    expect(roughly).to_contain_text("When")
    expect(roughly.get_by_role("link", name="Event Birth of Alcuin")).to_be_visible()
    expect(roughly).to_contain_text("between 1 January 1500 and 31 December 1500")
    # the feast by rule on the 21st
    expect(month.get_by_role("link", name="Benedict")).to_have_count(1)
    # a date leads to what it is in
    month.get_by_role("link", name="Event Coronation").click()
    page.wait_for_url(f"**/Event/{dated.coronation}")
    expect(page.get_by_role("heading", name="Coronation")).to_be_visible()
    page.go_back()
    # the next month, and the same month read in the Gregorian calendar
    page.get_by_role("link", name="Next month").click()
    page.wait_for_url("**/calendar/julian/1500/4")
    expect(page.get_by_role("heading", name=re.compile("^April 1500"))).to_be_visible()
    # (one button: it names the calendar the page is read in, and goes to the other)
    page.get_by_role("banner", name="Console").get_by_role(
        "link", name="Julian"
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
    # (the birth, sometime in 1500, is possible on any day of it, and says so)
    birth = on_day.locator("li[data-mark]", has_text="Birth of Alcuin")
    expect(birth).to_have_attribute("data-mark", "possible")
    expect(birth).to_contain_text("between 1 January 1500 and 31 December 1500")
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
    # on the 4th: the siege (a period) is stated; the fair, one day on the 4th or the 5th, is only possible; the birth too
    page.get_by_role("link", name="Next day").click()
    page.wait_for_url("**/calendar/julian/1500/3/4")
    rows = page.get_by_role("region", name="On this day").locator("li[data-mark]")
    expect(rows).to_have_count(3)
    expect(rows.filter(has_text="Siege")).to_have_attribute("data-mark", "stated")
    expect(rows.filter(has_text="The fair")).to_have_attribute("data-mark", "possible")
    expect(rows.filter(has_text="The fair")).to_contain_text(
        "between 4 March 1500 and 5 March 1500"
    )
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
    expect(feasts).to_contain_text("repeats")


def test_someone_logged_in_attaches_a_feast_to_a_day_and_takes_it_away(
    logged_in: Page, dated
):
    page = logged_in
    page.goto("/calendar/julian/1500/3/5")
    hydrated(page)
    feasts = page.get_by_role("region", name="Feasts and characterisations")
    expect(feasts).to_contain_text("None on this day")
    # (no New buttons in the console any more: a + of a day, or of the search, makes one)
    expect(
        page.get_by_role("banner", name="Console").get_by_role("link", name="New Feast")
    ).to_have_count(0)
    # the search of the characterisations, as in a form: one found is attached to the day
    feasts.get_by_placeholder("Find one to attach to this day, or + to make one").fill(
        "mark"
    )
    feasts.get_by_role("option", name=re.compile("Market day")).click()
    expect(page.get_by_text("Market day attached")).to_be_visible()
    expect(feasts.get_by_role("link", name="Market day")).to_be_visible()
    expect(feasts).to_contain_text("attached to this day")
    expect(feasts).not_to_contain_text("repeats")
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
    # taken away by the remove button of its chip
    feasts.get_by_role("button", name="Detach Market day").click()
    expect(page.get_by_text("Market day detached")).to_be_visible()
    expect(feasts).to_contain_text("None on this day")
    assert (
        dated.api.ok("GET", "/api/calendar/day/J1500-03-05")["characterisations"] == []
    )
    # the + of the search makes a new one, on this day to start with
    feasts.get_by_role("button", name="Make a new one").click()
    dialog = page.get_by_role("dialog")
    # (a feast, or a document that can have a date, a dateable appointment too; the search finds only feasts)
    expect(dialog.locator("button[data-choice]")).to_have_text(
        ["Appointment", "Feast", "Event"]
    )
    dialog.get_by_role("button", name="Feast", exact=True).click()
    expect(dialog.get_by_label("When Year", exact=True)).to_have_value("1500")
    expect(dialog.get_by_label("When Day", exact=True)).to_have_value("5")
    dialog.get_by_label("Label", exact=True).fill("Fair day")
    dialog.get_by_role("button", name="Save").click()
    expect(dialog).to_have_count(0)
    expect(feasts.get_by_role("link", name="Fair day")).to_be_visible()
    # and a document, in the same dialog, its date the day; saved, it is on the day, and not attached
    feasts.get_by_role("button", name="Make a new one").click()
    dialog.get_by_role("button", name="Event", exact=True).click()
    expect(dialog.get_by_role("heading", name="New Event")).to_be_visible()
    expect(dialog.get_by_label("When Day", exact=True)).to_have_value("5")
    dialog.get_by_label("Label", exact=True).fill("The bridge falls")
    dialog.get_by_label("Text", exact=True).fill("The bridge falls")
    dialog.get_by_role("button", name="Save").click()
    expect(dialog).to_have_count(0)
    expect(page).to_have_url(re.compile(r"/calendar/julian/1500/3/5$"))
    expect(
        page.get_by_role("region", name="On this day").get_by_role(
            "link", name=re.compile("The bridge falls")
        )
    ).to_be_visible()
    expect(feasts.get_by_role("link", name=re.compile("The bridge falls"))).to_have_count(0)


def test_a_feast_is_made_from_the_plus_of_a_day_in_the_month(logged_in: Page, dated):
    """Each day of the month has a + (for someone logged in): it opens the types that can be made on a day (the
    characterisations, and the documents that can have a date), and the form of the one chosen starts on that day;
    saved, it is on the day"""
    page = logged_in
    page.goto("/calendar/julian/1500/3")
    hydrated(page)
    month = page.get_by_test_id("calendar-month")
    month.get_by_role("button", name="Add to 7 March 1500").click()
    dialog = page.get_by_role("dialog")
    # (a feast, and an event and an appointment, which have a date; not a report, which has none)
    expect(dialog.locator("button[data-choice]")).to_have_text(
        ["Appointment", "Feast", "Event"]
    )
    dialog.get_by_role("button", name="Feast", exact=True).click()
    expect(dialog.get_by_role("heading", name="New Feast")).to_be_visible()
    expect(dialog.get_by_label("When Month", exact=True)).to_have_value("3")
    expect(dialog.get_by_label("When Day", exact=True)).to_have_value("7")
    dialog.get_by_label("Label", exact=True).fill("Thomas Aquinas")
    dialog.get_by_role("button", name="Save").click()
    expect(dialog).to_have_count(0)
    expect(month.get_by_role("link", name="Thomas Aquinas")).to_have_count(1)
    # (a reader not logged in has no +)
    page.context.clear_cookies()
    page.reload()
    expect(
        page.get_by_test_id("calendar-month").get_by_role(
            "button", name=re.compile("^Add to")
        )
    ).to_have_count(0)


def test_a_document_with_a_date_is_made_from_the_plus_of_a_day_in_the_month(
    logged_in: Page, dated
):
    """A document that can have a date is made from a day's + in a dialog, the date that day (in the calendar of the
    page), without leaving the month; saved, it is on the day"""
    page = logged_in
    page.goto("/calendar/gregorian/1500/3")
    hydrated(page)
    month = page.get_by_test_id("calendar-month")
    month.get_by_role("button", name="Add to 20 March 1500").click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_role("button", name="Event", exact=True).click()
    expect(dialog.get_by_role("heading", name="New Event")).to_be_visible()
    expect(dialog.get_by_label("When Year", exact=True)).to_have_value("1500")
    expect(dialog.get_by_label("When Month", exact=True)).to_have_value("3")
    expect(dialog.get_by_label("When Day", exact=True)).to_have_value("20")
    expect(dialog.get_by_role("radio", name="Gregorian")).to_have_attribute(
        "aria-checked", "true"
    )
    dialog.get_by_label("Label", exact=True).fill("The siege is lifted")
    dialog.get_by_label("Text", exact=True).fill("The siege is lifted")
    dialog.get_by_role("button", name="Save").click()
    expect(dialog).to_have_count(0)
    expect(page).to_have_url(re.compile(r"/calendar/gregorian/1500/3$"))
    expect(
        month.get_by_role("link", name=re.compile("The siege is lifted"))
    ).to_have_count(1)
    # (in the Julian calendar it is the 10th)
    page.goto("/calendar/julian/1500/3/10")
    expect(page.get_by_role("link", name=re.compile("The siege is lifted"))).to_be_visible()


def test_the_month_is_asked_for_again_after_logging_in_and_out(page: Page, dated):
    # (what is dated on it may be more for someone logged in: a document not yet published. The calendar reads it outside
    # the router's queries, which are asked for again anyway; that it is asked for again is what is seen)
    def month(request):
        return "/api/calendar/month/" in request.url

    page.goto("/calendar/julian/1500/3")
    hydrated(page)
    expect(page.get_by_test_id("calendar-month")).to_be_visible()
    with page.expect_request(month):
        log_in_through_the_dialog(page)
    expect(page.get_by_role("button", name="Add to 7 March 1500")).to_be_visible()
    expand_nav(page)
    with page.expect_request(month):
        page.get_by_role("button", name=f"Log out {USERNAME}").click()
    expect(page.get_by_role("button", name="Add to 7 March 1500")).to_have_count(0)


def test_the_day_and_the_month_lead_to_their_year(page: Page, dated):
    page.goto("/calendar/julian/1500/3/2")
    hydrated(page)
    where = page.get_by_role("navigation", name="Where in the calendar")
    expect(where.get_by_role("link", name="March 1500")).to_have_attribute(
        "href", "/calendar/julian/1500/3"
    )
    where.get_by_role("link", name="1500", exact=True).click()
    page.wait_for_url("**/calendar?calendar=julian#year-1500")
    # (the year's row is the one gone to)
    row = page.locator("#year-1500")
    expect(row).to_be_visible()
    expect(row).to_have_attribute("aria-current", "true")
    expect(page.locator("[aria-current='true'][data-testid='calendar-year']")).to_have_count(1)
    page.goto("/calendar/julian/1500/3")
    expect(
        page.get_by_role("navigation", name="Where in the calendar").get_by_role(
            "link", name="1500"
        )
    ).to_have_attribute("href", "/calendar?calendar=julian#year-1500")


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


def test_a_feast_by_rule_is_made_in_the_form_as_a_person_says_it(
    logged_in: Page, dated
):
    """The form of a Feast: a Recurrence is said as every year on a day of a month, from a year until a year (none of
    the rule's raw fields), and it is saved and found on its day"""
    page = logged_in
    page.goto("/Feast/new")
    hydrated(page)
    page.get_by_label("Label", exact=True).fill("Gregory")
    page.get_by_role("button", name="Add when").click()
    page.get_by_role("button", name="Recurrence", exact=True).click()
    editor = page.get_by_test_id("recurrence-editor")
    expect(editor).to_be_visible()
    for raw in ("Nth", "Month day", "Excluded days", "Easter offset", "Interval"):
        expect(page.locator("main")).not_to_contain_text(raw)
    page.get_by_role("radio", name="Every year").click()
    page.get_by_role("radio", name="A day of a month").click()
    page.get_by_label("When Day", exact=True).fill("12")
    page.get_by_label("When Month", exact=True).select_option("3")
    page.get_by_label("When From Year", exact=True).fill("1450")
    page.get_by_label("When Until Year", exact=True).fill("1530")
    expect(page.get_by_test_id("date-reads")).to_contain_text(
        "every year on 12 March, 1450 – 1530"
    )
    page.get_by_role("button", name="Save").click()
    page.wait_for_url(re.compile(r"/Feast/[^/]+$"))
    expect(page.get_by_role("heading", name="Gregory")).to_be_visible()
    # (it falls on 12 March 1500, by rule, and repeats)
    page.goto("/calendar/julian/1500/3/12")
    feasts = page.get_by_role("region", name="Feasts and characterisations")
    expect(feasts.get_by_role("link", name="Gregory")).to_be_visible()
    expect(feasts).to_contain_text("repeats")
