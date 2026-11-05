"""What refers to an entity, by date (`pangloss_dates.dateable`): the e2e project's `Appointment` is `Dateable`, its
`Statement` is not. On a person's page the appointments can be shown in order of date, each with its date and the field
it is in, under a "Timeline" bar, beside a timeline that goes to a year; the statements stay with the person's own facts,
and those whose date is not known come last. And a range with an end that is not known, in the form. (The fixture
`appointed` is in conftest.py.)"""

import re

from conftest import julian
from helpers import hydrated
from playwright.sync_api import Page, expect


def test_what_refers_to_a_person_is_shown_by_date(page: Page, appointed):
    page.goto(f"/Person/{appointed.ada}")
    hydrated(page)
    # (by relation, as before, until the console's toggle is pressed; each a chip: the copy of its date is not shown as its fields)
    expect(page.locator("main [data-block]")).to_have_count(0)
    by_date = page.get_by_role("button", name="Sort by date")
    expect(by_date).to_have_attribute("aria-pressed", "false")
    by_date.click()
    # (what has no date stays with the person's facts, with no heading; what has is a section of its own, under a bar)
    expect(page.locator("main h2")).to_have_text(["Timeline"])
    expect(
        page.locator("main dl").first.get_by_role(
            "link", name=re.compile("She was there")
        )
    ).to_be_visible()
    expect(page.locator("main section").get_by_test_id("dated-item")).to_have_count(3)
    rows = page.get_by_test_id("dated-item")
    # (the date in words and the field on the left; last the abbot, whose date is not known)
    expect(rows).to_have_count(3)
    expect(rows.nth(0)).to_contain_text("not before 1490")
    expect(rows.nth(0).get_by_role("link")).to_have_text(re.compile("Notary"))
    expect(rows.nth(1)).to_contain_text("1510")
    expect(rows.nth(1).get_by_role("link")).to_have_text(re.compile("Bishop"))
    expect(page.get_by_test_id("incoming-date-unknown")).to_contain_text("Abbot")

    # (the timeline beside them spans their years; there is no other filter of years)
    timeline = page.get_by_role("slider", name="Go to year")
    expect(timeline).to_have_attribute("aria-valuemin", "1490")
    expect(timeline).to_have_attribute("aria-valuemax", "1510")
    expect(page.get_by_role("slider", name="From")).to_have_count(0)

    # (the timeline takes the page to a year: the keys go from one year that has something to the next; a low window,
    # so that the page can scroll)
    page.set_viewport_size({"width": 1280, "height": 320})
    page.evaluate("window.scrollTo(0, 0)")
    heading = page.locator("main [data-year='1510']")
    expect(heading).not_to_be_in_viewport()
    timeline.press("End")
    expect(timeline).to_have_attribute("aria-valuenow", "1510")
    expect(heading).to_be_in_viewport()

    # (the choice is kept on the next page)
    page.reload()
    hydrated(page)
    expect(page.get_by_role("button", name="Sort by date")).to_have_attribute(
        "aria-pressed", "true"
    )
    page.get_by_role("button", name="Sort by date").click()
    expect(page.get_by_test_id("dated-item")).to_have_count(0)


def test_an_end_of_a_range_that_is_not_known_is_a_button(logged_in: Page, appointed):
    page = logged_in
    page.goto(f"/Appointment/{appointed.notary}/edit")
    hydrated(page)
    not_after = page.get_by_role("button", name="Date Not after Not known")
    # (the copy of the date is the server's: not in the form)
    expect(
        page.locator("main dt", has_text=re.compile("^date text$", re.I))
    ).to_have_count(0)
    expect(not_after).to_have_attribute("aria-pressed", "true")
    expect(page.get_by_test_id("date-reads")).to_contain_text("not before 1490")
    # (both ends cannot be unknown)
    expect(
        page.get_by_role("button", name="Date Not before Not known")
    ).to_be_disabled()
    not_after.click()
    expect(not_after).to_have_attribute("aria-pressed", "false")
    page.get_by_role("spinbutton", name="Date Not after Year").fill("1495")
    expect(page.get_by_test_id("date-reads")).to_contain_text("1490 to 1495")


def test_the_timeline_is_dragged_to_a_year_and_follows_the_page(
    page: Page, appointed, types
):
    # (enough appointments over 80 years for the page to scroll under the timeline, which sticks to the window)
    api = types.admin()
    for n, year in enumerate(range(1450, 1530, 4)):
        api.ok(
            "POST",
            "/api/Appointment",
            {
                "label": f"Office {n}",
                "appointed": {"type": "Person", "id": appointed.ada},
                "date": julian(year),
            },
        )
    page.goto(f"/Person/{appointed.ada}")
    hydrated(page)
    page.get_by_role("button", name="Sort by date").click()
    timeline = page.get_by_role("slider", name="Go to year")
    expect(timeline).to_have_attribute("aria-valuenow", "1450")
    # (a drag down a third of the track: the page scrolls as it goes, and the track with it, but the year follows the
    # pointer, and ends on a year that has something)
    box = timeline.bounding_box()
    track = timeline.locator("..").bounding_box()
    assert box and track
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(
        box["x"] + box["width"] / 2, box["y"] + track["height"] / 3, steps=10
    )
    page.mouse.up()
    year = int(timeline.get_attribute("aria-valuenow") or 0)
    assert 1470 <= year <= 1490 and year % 4 == 2, year
    expect(page.locator(f"main [data-year='{year}']")).to_be_in_viewport()
    # (scrolling the page moves the thumb)
    page.mouse.wheel(0, 2000)
    expect(timeline).not_to_have_attribute("aria-valuenow", str(year))
