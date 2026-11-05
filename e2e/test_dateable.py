"""What refers to an entity, by date (`pangloss_dates.dateable`): the e2e project's `Appointment` is `Dateable`, its
`Statement` is not. On a person's page the appointments can be shown in order of date, each with its date and the field
it is in, narrowed by a slider of years; those whose date is not known and the statements follow. And a range with an
end that is not known, in the form. (The fixture `appointed` is in conftest.py.)"""

import re

from helpers import hydrated
from playwright.sync_api import Page, expect


def test_what_refers_to_a_person_is_shown_by_date(page: Page, appointed):
    page.goto(f"/Person/{appointed.ada}")
    hydrated(page)
    # (by field, as before, until asked; each a chip: the copy of its date is not shown as its fields)
    expect(page.locator("main [data-block]")).to_have_count(0)
    by_date = page.get_by_role("button", name="By date")
    expect(by_date).to_have_attribute("aria-pressed", "false")
    by_date.click()
    rows = page.get_by_test_id("dated-item")
    expect(rows).to_have_count(2)
    # (in order of date, the date and the field on the left)
    expect(rows.nth(0)).to_contain_text("≥ 1490")
    expect(rows.nth(0).get_by_role("link")).to_have_text(re.compile("Notary"))
    expect(rows.nth(1)).to_contain_text("1510")
    expect(rows.nth(1).get_by_role("link")).to_have_text(re.compile("Bishop"))
    expect(page.get_by_test_id("incoming-date-unknown")).to_contain_text("Abbot")
    expect(page.get_by_text("Not dated")).to_be_visible()
    expect(page.get_by_role("link", name=re.compile("She was there"))).to_be_visible()

    # (the slider of years narrows them)
    page.get_by_role("slider", name="From").fill("1500")
    expect(rows).to_have_count(1)
    expect(page.get_by_test_id("incoming-shown")).to_have_text("1 of 2")

    # (the choice is kept on the next page)
    page.reload()
    hydrated(page)
    expect(page.get_by_role("button", name="By date")).to_have_attribute(
        "aria-pressed", "true"
    )
    page.get_by_role("button", name="By field").click()
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
