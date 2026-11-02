"""Making an item and changing one, through the form"""

import re

from helpers import hydrated
from playwright.sync_api import Page, expect


def test_an_item_page_has_an_edit_button_only_when_logged_in(page: Page, data):
    page.goto(f"/Statement/{data.statement}")
    expect(page.get_by_role("heading", name="Court at Ghent")).to_be_visible()
    expect(page.get_by_role("link", name="Edit")).to_have_count(0)


def test_editing_an_item_saves_a_change(logged_in: Page, data):
    page = logged_in
    page.goto(f"/Statement/{data.statement}")
    hydrated(page)
    page.get_by_role("link", name="Edit").click()
    page.wait_for_url(f"**/Statement/{data.statement}/edit")
    label = page.get_by_label("Label", exact=True)
    expect(label).to_have_value("Court at Ghent")
    label.fill("Court at Bruges")
    page.get_by_label("Text", exact=True).fill("Marie held court at Bruges")
    page.get_by_role("button", name="Save").click()
    page.wait_for_url(f"**/Statement/{data.statement}")
    expect(page.get_by_text("Marie held court at Bruges")).to_be_visible()
    expect(page.get_by_text("Court at Bruges").first).to_be_visible()
    # (a toast says it was saved, on the page of the item)
    expect(page.get_by_role("status", name="Notifications")).to_contain_text("Statement “Court at Bruges” saved")


def test_a_new_item_is_made_with_an_entity_found_by_search(logged_in: Page, data):
    page = logged_in
    page.goto("/Statement")
    hydrated(page)
    page.get_by_role("link", name="New Statement").click()
    page.wait_for_url("**/Statement/new")
    page.get_by_label("Label", exact=True).fill("A new statement")
    page.get_by_label("Text", exact=True).fill("Something happened")
    page.get_by_label("Find Person…").fill("Marie")
    page.get_by_role("option", name="Marie of Burgundy").click()
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_role("heading", name="A new statement")).to_be_visible()
    expect(page.get_by_role("link", name="Marie of Burgundy")).to_be_visible()


def test_an_entity_field_offers_the_most_used_then_puts_those_picked_lately_first(
    logged_in: Page, data
):
    page = logged_in
    page.goto("/Statement/new")
    hydrated(page)
    options = page.get_by_role("option")
    page.get_by_label("Find Person…").focus()
    # (Marie has a role and a statement about her, Maximilian a role, Charles nothing)
    expect(options).to_have_text(
        [re.compile("Marie of Burgundy"), re.compile("Maximilian"), re.compile("Charles the Bold")]
    )
    page.get_by_label("Find Person…").fill("Charl")
    page.get_by_role("option", name="Charles the Bold").click()
    page.goto("/Statement/new")
    hydrated(page)
    page.get_by_label("Find Person…").focus()
    expect(options).to_have_text(
        [re.compile("Charles the Bold"), re.compile("Marie of Burgundy"), re.compile("Maximilian")]
    )
    expect(options.first.get_by_title("Used recently")).to_be_visible()
    # (typing leaves out what was picked lately, if it does not match)
    page.get_by_label("Find Person…").fill("Mari")
    expect(options).to_have_text([re.compile("Marie of Burgundy")])


def test_a_rejected_form_says_what_is_wrong_and_keeps_what_was_typed(logged_in: Page, data):
    page = logged_in
    page.goto("/Statement/new")
    hydrated(page)
    page.get_by_label("Label", exact=True).fill("Incomplete")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_role("alert")).to_contain_text("text")
    expect(page.get_by_label("Label", exact=True)).to_have_value("Incomplete")


def test_cancel_goes_back_without_saving(logged_in: Page, data):
    page = logged_in
    page.goto(f"/Statement/{data.statement}/edit")
    hydrated(page)
    page.get_by_label("Label", exact=True).fill("Changed")
    page.get_by_role("button", name="Cancel").click()
    page.wait_for_url(f"**/Statement/{data.statement}")
    expect(page.get_by_role("heading", name="Court at Ghent")).to_be_visible()


def test_an_entity_is_made_from_the_form_and_chosen(logged_in: Page, data):
    page = logged_in
    page.goto("/Statement/new")
    hydrated(page)
    page.get_by_label("Label", exact=True).fill("Statement about Bede")
    page.get_by_label("Text", exact=True).fill("Bede wrote")
    page.get_by_role("button", name="Make a new one").click()
    dialog = page.get_by_role("dialog", name="New Person")
    dialog.get_by_label("Label", exact=True).fill("Bede")
    dialog.get_by_role("button", name="Save").click()
    expect(dialog).to_have_count(0)
    expect(page.get_by_text("Bede", exact=True)).to_be_visible()
    expect(page.get_by_role("status", name="Notifications")).to_contain_text("Person “Bede” created")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_role("heading", name="Statement about Bede")).to_be_visible()
    expect(page.get_by_role("status", name="Notifications")).to_contain_text("Statement “Statement about Bede” created")
    expect(page.get_by_role("link", name="Bede")).to_be_visible()


def test_an_entity_cut_in_one_form_is_pasted_into_another(logged_in: Page, data):
    page = logged_in
    # (nothing is copied from a view: only a form has the buttons)
    page.goto(f"/Statement/{data.statement}")
    hydrated(page)
    expect(page.get_by_role("button", name="Copy Marie of Burgundy")).to_have_count(0)
    page.goto(f"/Statement/{data.statement}/edit")
    hydrated(page)
    page.get_by_role("button", name="Cut Marie of Burgundy").click()
    clipboard = page.get_by_role("complementary", name="Clipboard")
    expect(clipboard).to_contain_text("Marie of Burgundy")
    # (the clipboard is kept in the browser, so it is there on the next page)
    page.goto("/Statement/new")
    hydrated(page)
    expect(clipboard).to_contain_text("Marie of Burgundy")
    page.get_by_label("Label", exact=True).fill("Pasted")
    page.get_by_label("Text", exact=True).fill("Marie again")
    page.get_by_role("group", name="Paste here").get_by_role("button").click()
    # (something cut is pasted once: the clipboard is empty, and the bar slides away, hidden from a screen reader)
    expect(page.locator('aside[aria-label="Clipboard"]')).to_have_attribute("aria-hidden", "true")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_role("heading", name="Pasted")).to_be_visible()
    expect(page.get_by_role("link", name="Marie of Burgundy")).to_be_visible()
