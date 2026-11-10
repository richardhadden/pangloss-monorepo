"""What the core's pages do that had only unit tests: the shortcuts of the list, the item and the form; who made and
changed an item, in the console; and a document inside another (its head is a link, its own page says what it is
contained in, and its Edit is the form of the document it is part of)."""

import re

from conftest import AUTHOR_PASSWORD, AUTHOR_USERNAME, USERNAME
from helpers import hydrated
from playwright.sync_api import Page, expect


def test_the_shortcuts_make_edit_and_save(logged_in: Page, data):
    page = logged_in
    page.goto("/Statement")
    hydrated(page)
    # (Cmd/Ctrl+Enter is the New button; the cursor starts in the label)
    page.keyboard.press("ControlOrMeta+Enter")
    page.wait_for_url("**/Statement/new")
    label = page.get_by_label("Label", exact=True)
    expect(label).to_be_focused()
    page.keyboard.type("Made with the keys")
    page.get_by_label("Text", exact=True).fill("Typed")
    page.get_by_label("Find Person…").fill("Marie")
    page.get_by_role("option", name="Marie of Burgundy").click()
    # (Cmd/Ctrl+S is the Save button)
    page.keyboard.press("ControlOrMeta+s")
    expect(page.get_by_role("heading", level=1, name="Made with the keys")).to_be_visible()
    made = page.url.rstrip("/").split("/")[-1]
    # (Cmd/Ctrl+E is the Edit button)
    hydrated(page)
    page.keyboard.press("ControlOrMeta+e")
    page.wait_for_url(f"**/Statement/{made}/edit")
    expect(page.get_by_label("Label", exact=True)).to_have_value("Made with the keys")
    # (with nothing changed there is nothing to save: the keys do no more than the button, which is off)
    expect(page.get_by_role("button", name="Save")).to_be_disabled()
    page.keyboard.press("ControlOrMeta+s")
    expect(page).to_have_url(re.compile(rf"/Statement/{made}/edit$"))


def test_the_console_says_who_made_and_who_changed_an_item(logged_in: Page, data, types):
    page = logged_in
    page.goto(f"/Statement/{data.statement}")
    hydrated(page)
    meta = page.get_by_test_id("console-meta")
    expect(meta).to_contain_text(re.compile(rf"Created\s*{USERNAME}"))
    expect(meta).not_to_contain_text("Modified")

    # (someone else changes it: both are said, each with their name and when)
    ann = types.client(AUTHOR_USERNAME, AUTHOR_PASSWORD)
    edit = ann.ok("GET", f"/api/Statement/{data.statement}/edit")
    status, result = ann.send(
        "PUT", f"/api/Statement/{data.statement}", {**edit, "text": "Changed by ann"}, headers={"If-Match": "*"}
    )
    assert status < 300, result
    page.reload()
    hydrated(page)
    expect(meta).to_contain_text(re.compile(rf"Created\s*{USERNAME}\s*·\s*\w+ \d+, \d{{4}}"))
    expect(meta).to_contain_text(re.compile(rf"Modified\s*{AUTHOR_USERNAME}\s*·\s*\w+ \d+, \d{{4}}"))
    expect(meta.get_by_role("link", name=AUTHOR_USERNAME)).to_have_attribute("href", f"/users/{AUTHOR_USERNAME}")


def test_a_document_inside_another_links_to_its_own_page_and_back(logged_in: Page, types):
    api = types.admin()
    report = api.ok(
        "POST",
        "/api/Report",
        {
            "label": "The report",
            "text": "What was found",
            "sections": [
                {"type": "ReportSection", "label": "First section", "body": "The first"},
                {"type": "ReportSection", "label": "Second section", "body": "The second"},
            ],
            "findings": [],
        },
    )["id"]
    section = api.ok("GET", f"/api/Report/{report}")["sections"][1]["id"]

    page = logged_in
    page.goto(f"/Report/{report}")
    hydrated(page)
    # (the head of a document inside the report is a link to that document)
    head = page.locator("main").get_by_role("link", name="Report section Second section")
    expect(head).to_have_attribute("href", f"/ReportSection/{section}")
    head.click()
    page.wait_for_url(f"**/ReportSection/{section}")
    hydrated(page)

    # (its own page: what it is contained in, as a chip to the report, showing where it is in it)
    main = page.locator("main")
    expect(main.get_by_role("heading", level=1, name="Second section")).to_be_visible()
    expect(main).to_contain_text("Contained in")
    expect(main).to_contain_text("The second")
    expect(main).not_to_contain_text("The first")
    contained = main.get_by_role("link", name="Report The report")
    expect(contained).to_have_attribute("href", f"/Report/{report}?show={section}")
    # (it is not deleted apart from its report, and its Edit is the report's form, at its block)
    expect(page.get_by_role("button", name="Delete")).to_have_count(0)
    edit = page.get_by_role("link", name="Edit")
    expect(edit).to_have_attribute("href", f"/Report/{report}/edit?show={section}")
    edit.click()
    page.wait_for_url(f"**/Report/{report}/edit?show={section}")
    expect(page.get_by_label("Label", exact=True).first).to_have_value("The report")
    expect(page.locator(f'[data-item-id="{section}"], [id="{section}"]').first).to_be_in_viewport()

    # (and back from the chip: the report, scrolled to the section)
    page.goto(f"/ReportSection/{section}")
    hydrated(page)
    page.locator("main").get_by_role("link", name="Report The report").click()
    page.wait_for_url(f"**/Report/{report}?show={section}")
    expect(page.locator("main").get_by_role("heading", level=1, name="The report")).to_be_visible()
