"""The search form of a list: the button beside Deep search opens it under the console, it pushes the list down, and
each change of it is a search, kept in the address"""

import json
import re
from urllib.parse import parse_qs, urlparse

from helpers import hydrated
from playwright.sync_api import Page, expect


def results(page: Page):
    return page.locator("main ul[style] > li")


def panel(page: Page):
    return page.get_by_role("region", name=re.compile("by fields"))


def open_form(page: Page, type: str = "Person") -> None:
    page.goto(f"/{type}")
    hydrated(page)
    page.get_by_role("button", name="Search by fields").click()
    expect(panel(page)).to_be_visible()


def box(locator) -> dict:
    """Where it is on the page (it is on show)"""
    found = locator.bounding_box()
    assert found is not None
    return found


def form_in_address(page: Page) -> dict:
    return json.loads(parse_qs(urlparse(page.url).query)["form"][0])


def test_the_form_opens_under_the_console_and_pushes_the_list_down(page: Page, data):
    page.goto("/Person")
    hydrated(page)
    expect(panel(page)).to_be_hidden()
    first = box(results(page).first)
    button = page.get_by_role("button", name="Search by fields")
    expect(button).to_have_attribute("aria-pressed", "false")
    button.click()
    expect(button).to_have_attribute("aria-pressed", "true")
    expect(panel(page)).to_be_visible()
    # (its top is the bottom of the console, and the list is below it)
    console = box(page.get_by_role("banner", name="Console"))
    top = box(panel(page))
    assert abs(top["y"] - (console["y"] + console["height"])) <= 1
    expect(results(page)).to_have_count(3)
    page.wait_for_timeout(400)
    moved = box(results(page).first)
    assert moved["y"] > first["y"] + 100
    assert moved["y"] >= top["y"] + box(panel(page))["height"]
    page.get_by_role("button", name="Close").click()
    expect(panel(page)).to_be_hidden()
    expect(button).to_have_attribute("aria-pressed", "false")


def test_a_condition_narrows_the_list_and_is_kept_in_the_address(page: Page, data):
    open_form(page)
    page.get_by_role(
        "combobox", name=re.compile("^Condition on has role", re.I)
    ).select_option("missing")
    expect(results(page)).to_have_count(1)
    expect(page.get_by_role("link", name="Charles the Bold")).to_be_visible()
    expect(page.get_by_title("Found")).to_have_text("1")
    page.wait_for_url(re.compile(r"form="))
    assert form_in_address(page)["fields"]["has_role"]["op"] == "missing"
    # (and the button says a search by fields is in use)
    expect(page.get_by_role("button", name="Search by fields (in use)")).to_be_visible()
    # not: those that have one
    page.get_by_role("button", name=re.compile("^Not: has role", re.I)).click()
    expect(results(page)).to_have_count(2)
    # (the address opens the form as it was, with what it found)
    page.reload()
    hydrated(page)
    expect(panel(page)).to_be_visible()
    expect(results(page)).to_have_count(2)
    expect(
        page.get_by_role("button", name=re.compile("^Not: has role", re.I))
    ).to_have_attribute("aria-pressed", "true")
    page.get_by_role("button", name="Clear").click()
    expect(results(page)).to_have_count(3)
    page.wait_for_url(lambda url: "form=" not in url)


def test_entities_are_picked_as_in_the_entry_form(page: Page, data):
    open_form(page)
    page.get_by_role("combobox", name=re.compile("^Find Role")).fill("advisor")
    page.get_by_role("option", name=re.compile("Marie's advisor")).click()
    expect(results(page)).to_have_count(1)
    expect(page.get_by_role("link", name="Marie of Burgundy")).to_be_visible()


def test_what_is_typed_narrows_the_form_and_deep_search_is_off(page: Page, data):
    open_form(page)
    page.get_by_role(
        "combobox", name=re.compile("^Condition on has role", re.I)
    ).select_option("exists")
    expect(results(page)).to_have_count(2)
    expect(page.get_by_role("button", name="Deep search", exact=True)).to_be_disabled()
    page.get_by_role("searchbox").fill("Max")
    expect(results(page)).to_have_count(1)
    expect(page.get_by_role("link", name="Maximilian")).to_be_visible()


def test_a_nested_form_describes_what_a_relation_points_at(page: Page, data):
    open_form(page)
    page.get_by_role(
        "combobox", name=re.compile("^Condition on has role", re.I)
    ).select_option("match")
    # (the field can point at a role or at a type of one: which is chosen first)
    page.get_by_role("button", name="Choose a type").click()
    page.get_by_role("menuitem", name="Role", exact=True).click()
    nested = page.locator('[data-search-node="Role"]')
    expect(nested).to_be_visible()
    nested.get_by_role("textbox", name="Label").fill("secretary")
    expect(results(page)).to_have_count(1)
    expect(page.get_by_role("link", name="Maximilian")).to_be_visible()


def test_an_entity_is_found_by_what_refers_to_it(page: Page, data):
    open_form(page)
    page.get_by_role("combobox", name="Add what refers to it").select_option(
        label="Statement · About"
    )
    expect(results(page)).to_have_count(1)
    expect(page.get_by_role("link", name="Marie of Burgundy")).to_be_visible()
    nested = page.locator('[data-search-node="Statement"]')
    nested.get_by_role("textbox", name="Text").fill("Bruges")
    expect(results(page)).to_have_count(0)
    nested.get_by_role("textbox", name="Text").fill("Ghent")
    expect(results(page)).to_have_count(1)


def test_a_document_is_found_by_what_it_mentions(page: Page, data):
    open_form(page, "Statement")
    page.get_by_role("combobox", name="Find an entity…").fill("Maxim")
    page.get_by_role("option", name="Person Maximilian").click()
    expect(results(page)).to_have_count(0)
    page.get_by_role("button", name="Remove Maximilian").click()
    page.get_by_role("combobox", name="Find an entity…").fill("Marie of")
    page.get_by_role("option", name="Person Marie of Burgundy").click()
    expect(results(page)).to_have_count(1)
    expect(page.get_by_role("link", name="Court at Ghent")).to_be_visible()
