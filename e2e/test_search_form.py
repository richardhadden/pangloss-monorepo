"""The search form of a list: the button beside Deep search opens it under the console, it pushes the list down, and
each change of it is a search, kept in the address"""

import json
import re
from urllib.parse import parse_qs, urlparse

from helpers import add_filter, hydrated, pick
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


def test_there_is_no_row_until_a_filter_is_added(page: Page, data):
    open_form(page)
    expect(panel(page).locator("dt:not(.sr-only)")).to_have_count(0)
    add_filter(page, "has role")
    expect(panel(page).locator("dt:not(.sr-only)")).to_have_text(
        [re.compile("has role", re.I)]
    )
    # (a row with nothing in it yet changes nothing; taken out, it is gone)
    expect(results(page)).to_have_count(3)
    page.get_by_role(
        "button", name=re.compile("^Remove the condition on has role", re.I)
    ).click()
    expect(panel(page).locator("dt:not(.sr-only)")).to_have_count(0)


def test_a_condition_narrows_the_list_and_is_kept_in_the_address(page: Page, data):
    open_form(page)
    add_filter(page, "has role")
    pick(
        page.get_by_role("combobox", name=re.compile("^Condition on has role", re.I)),
        "missing",
    )
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
    add_filter(page, "has role")
    page.get_by_role("combobox", name=re.compile("^Find Role")).fill("advisor")
    page.get_by_role("option", name=re.compile("Marie's advisor")).click()
    expect(results(page)).to_have_count(1)
    expect(page.get_by_role("link", name="Marie of Burgundy")).to_be_visible()


def test_what_is_typed_narrows_the_form_and_deep_search_is_off(page: Page, data):
    open_form(page)
    add_filter(page, "has role")
    pick(
        page.get_by_role("combobox", name=re.compile("^Condition on has role", re.I)),
        "exists",
    )
    expect(results(page)).to_have_count(2)
    expect(page.get_by_role("button", name="Deep search", exact=True)).to_be_disabled()
    page.get_by_role("searchbox").fill("Max")
    expect(results(page)).to_have_count(1)
    expect(page.get_by_role("link", name="Maximilian")).to_be_visible()


def test_a_nested_form_describes_what_a_relation_points_at(page: Page, data):
    open_form(page)
    add_filter(page, "has role")
    pick(
        page.get_by_role("combobox", name=re.compile("^Condition on has role", re.I)),
        "match",
    )
    # (the field can point at a role or at a type of one, but there are only roles: so no menu, the button chooses it)
    expect(
        page.locator('button[aria-haspopup="menu"]', has_text="Choose a type")
    ).to_have_count(0)
    page.get_by_role("button", name="Choose a type").click()
    nested = page.locator('[data-search-node="Role"]')
    expect(nested).to_be_visible()
    add_filter(nested, "Label")
    nested.get_by_role("textbox", name="Label").fill("secretary")
    expect(results(page)).to_have_count(1)
    expect(page.get_by_role("link", name="Maximilian")).to_be_visible()


def test_an_entity_is_found_by_what_refers_to_it(page: Page, data):
    open_form(page)
    add_filter(page, "Referred to by")
    pick(
        page.get_by_role("combobox", name="Add what refers to it"),
        label="Statement · About",
    )
    expect(results(page)).to_have_count(1)
    expect(page.get_by_role("link", name="Marie of Burgundy")).to_be_visible()
    nested = page.locator('[data-search-node="Statement"]')
    add_filter(nested, "Text")
    nested.get_by_role("textbox", name="Text").fill("Bruges")
    expect(results(page)).to_have_count(0)
    nested.get_by_role("textbox", name="Text").fill("Ghent")
    expect(results(page)).to_have_count(1)


def test_a_document_is_found_by_what_it_mentions(page: Page, data):
    open_form(page, "Statement")
    add_filter(page, "Mentions")
    page.get_by_role("combobox", name="Find an entity…").fill("Maxim")
    page.get_by_role("option", name="Person Maximilian").click()
    expect(results(page)).to_have_count(0)
    page.get_by_role("button", name="Remove Maximilian").click()
    page.get_by_role("combobox", name="Find an entity…").fill("Marie of")
    page.get_by_role("option", name="Person Marie of Burgundy").click()
    expect(results(page)).to_have_count(1)
    expect(page.get_by_role("link", name="Court at Ghent")).to_be_visible()


def test_the_panel_is_a_little_in_from_the_ends_of_the_console(page: Page, data):
    open_form(page)
    console = box(page.get_by_role("banner", name="Console"))
    top = box(panel(page))
    assert top["x"] >= console["x"] + 8
    assert top["x"] + top["width"] <= console["x"] + console["width"] - 8


def test_the_results_can_be_ordered(page: Page, data):
    open_form(page)
    add_filter(page, "Order by")
    pick(page.get_by_role("combobox", name="Order by"), "label")
    pick(page.get_by_role("combobox", name="Direction of Label"), "desc")
    expect(results(page)).to_have_text(
        ["PersonMaximilian", "PersonMarie of Burgundy", "PersonCharles the Bold"]
    )
    pick(page.get_by_role("combobox", name="Direction of Label"), "asc")
    expect(results(page)).to_have_text(
        ["PersonCharles the Bold", "PersonMarie of Burgundy", "PersonMaximilian"]
    )


def test_alternatives_and_two_conditions_on_one_field(page: Page, data):
    open_form(page)
    add_filter(page, "Any of")
    alternatives = page.get_by_role("group", name="Alternatives 1")
    for alternative in alternatives.locator('[data-search-node="Person"]').all():
        add_filter(alternative, "Label")
    labels = alternatives.get_by_role("textbox", name="Label", exact=True)
    labels.nth(0).fill("Max")
    labels.nth(1).fill("Charles")
    expect(results(page)).to_have_count(2)
    # (and a label that also does not contain "Bold": both conditions on the label)
    add_filter(page, "Label")
    label = page.get_by_role("textbox", name="Label", exact=True).first
    label.fill("a")
    # (the first: the form's own label, before those of the alternatives)
    page.get_by_role("button", name="And another condition on Label").first.click()
    page.get_by_role("textbox", name="Label", exact=True).nth(1).fill("Bold")
    page.get_by_role("button", name="Not: Label").nth(1).click()
    expect(results(page)).to_have_count(1)
    expect(page.get_by_role("link", name="Maximilian")).to_be_visible()


def test_a_search_is_saved_in_the_browser_and_loaded_again(page: Page, data):
    open_form(page)
    add_filter(page, "has role")
    pick(
        page.get_by_role("combobox", name=re.compile("^Condition on has role", re.I)),
        "missing",
    )
    expect(results(page)).to_have_count(1)
    page.get_by_role("button", name="Save…").click()
    page.get_by_role("textbox", name="Name of this search").fill("No role")
    page.get_by_role("button", name="Save", exact=True).click()
    # (another visit, with nothing in the form)
    page.goto("/Person")
    hydrated(page)
    page.get_by_role("button", name="Search by fields").click()
    expect(results(page)).to_have_count(3)
    pick(page.get_by_role("combobox", name="Saved searches"), "No role")
    expect(results(page)).to_have_count(1)
    expect(page.get_by_role("link", name="Charles the Bold")).to_be_visible()
    page.get_by_role("button", name="Delete the saved search No role").click()
    expect(page.get_by_role("combobox", name="Saved searches")).to_have_count(0)


def test_a_menu_opens_over_the_edge_of_the_panel(page: Page, data):
    # (the panel's code is loaded when it is first opened, so it is made open, with no slide: it was left clipped,
    # waiting for the end of a slide, and every menu was cut off at its foot)
    open_form(page)
    # (clipped while it slides, 300 ms)
    page.wait_for_timeout(400)
    menu = page.get_by_role("combobox", name="Add a filter").last
    menu.click()
    last = page.locator(
        f"[id='{menu.get_attribute('aria-controls')}'] [role='option']"
    ).last
    found = box(last)
    panel_box = box(panel(page))
    assert found["y"] + found["height"] > panel_box["y"] + panel_box["height"]
    # (what is under its middle is the option, not the list below the panel)
    expect(last).to_be_visible()
    hit = page.evaluate(
        "([x, y]) => document.elementFromPoint(x, y)?.getAttribute('role')",
        [found["x"] + found["width"] / 2, found["y"] + found["height"] / 2],
    )
    assert hit == "option"
