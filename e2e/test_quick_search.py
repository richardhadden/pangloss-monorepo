"""The quick search popup (`/`): what only a browser shows. An item opens in the popup, which grows; with
Cmd or Ctrl held it goes to the page."""

import re

from helpers import hydrated
from playwright.sync_api import Page, expect


def open_and_search(page: Page, text: str):
    page.keyboard.press("/")
    popup = page.get_by_test_id("quick-search")
    expect(popup).to_be_visible()
    popup.get_by_role("searchbox").fill(text)
    results = popup.get_by_test_id("quick-search-results")
    expect(results.get_by_role("link", name=re.compile(text)).first).to_be_visible()
    return popup, results


def test_an_item_opens_in_the_popup_and_the_popup_grows(page: Page, data):
    page.goto("/Statement")
    hydrated(page)
    popup, results = open_and_search(page, "Maximilian")
    before = popup.bounding_box()

    page.keyboard.press("Enter")
    item = popup.get_by_test_id("quick-search-item")
    expect(item.get_by_test_id("quick-search-back")).to_be_visible()
    expect(page).to_have_url(re.compile(r"/Statement$"))
    expect(item.get_by_role("link", name=re.compile("Maximilian")).first).to_be_visible()
    expect(results).to_have_attribute("inert", "")
    page.wait_for_timeout(400)
    after = popup.bounding_box()
    assert after["width"] > before["width"]
    assert after["height"] != before["height"]

    # (back to the list, and then away)
    page.keyboard.press("Escape")
    expect(results.get_by_role("link", name=re.compile("Maximilian")).first).to_be_in_viewport()
    page.keyboard.press("Escape")
    expect(popup).to_have_count(0)


def test_a_click_shows_the_item_and_with_command_goes_to_it(page: Page, data):
    page.goto("/Statement")
    hydrated(page)
    popup, results = open_and_search(page, "Maximilian")
    link = results.get_by_role("link", name="Person Maximilian")
    link.click()
    expect(popup.get_by_test_id("quick-search-back")).to_be_visible()
    popup.get_by_test_id("quick-search-back").click()

    link.click(modifiers=["ControlOrMeta"])
    expect(popup).to_have_count(0)
    expect(page).to_have_url(re.compile(r"/Person/"))


def test_ctrl_enter_goes_to_the_result_and_from_the_item(page: Page, data):
    page.goto("/Statement")
    hydrated(page)
    popup, _ = open_and_search(page, "Maximilian")
    page.keyboard.press("ControlOrMeta+Enter")
    expect(popup).to_have_count(0)
    expect(page).to_have_url(re.compile(r"/(Person|Role)/"))
    # (focus is not in the popup any more, and the search did not change the address)
    assert "q=" not in page.url

    popup, _ = open_and_search(page, "Maximilian")
    page.keyboard.press("Enter")
    expect(popup.get_by_test_id("quick-search-back")).to_be_visible()
    page.keyboard.press("ControlOrMeta+Enter")
    expect(popup).to_have_count(0)


def test_a_slash_in_a_field_is_only_a_slash(page: Page, data):
    page.goto("/Statement")
    hydrated(page)
    field = page.get_by_role("searchbox").first
    field.click()
    page.keyboard.press("/")
    expect(field).to_have_value("/")
    expect(page.get_by_test_id("quick-search")).to_have_count(0)
