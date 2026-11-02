"""A list with a search, and the page of one item with what it refers to"""

import re

from helpers import hydrated
from playwright.sync_api import Page, expect


def results(page: Page):
    return page.locator("main ul > li")


def test_a_list_shows_every_item_and_how_many(page: Page, data):
    page.goto("/Person")
    expect(results(page)).to_have_count(3)
    expect(page.get_by_title("Found")).to_have_text("3")
    for name in ("Maximilian", "Marie of Burgundy", "Charles the Bold"):
        expect(page.get_by_role("link", name=name)).to_be_visible()


def test_a_search_narrows_the_list_and_is_kept_in_the_address(page: Page, data):
    page.goto("/Person")
    hydrated(page)
    page.get_by_role("searchbox").fill("Maxim")
    expect(results(page)).to_have_count(1)
    expect(page.get_by_title("Found")).to_have_text("1")
    page.wait_for_url("**/Person?q=Maxim")
    page.get_by_role("searchbox").fill("")
    expect(results(page)).to_have_count(3)


def test_typing_is_not_held_up_or_undone_by_the_searches_it_makes(page: Page, data):
    page.goto("/Person")
    hydrated(page)
    box = page.get_by_role("searchbox")
    # (slower than the debounce: a search is made after each key, while the next is typed)
    box.press_sequentially("Marie of B", delay=300)
    expect(box).to_have_value("Marie of B")
    page.wait_for_url("**/Person?q=Marie+of+B")
    expect(results(page)).to_have_count(1)
    expect(box).to_have_value("Marie of B")


def test_a_search_with_no_result_says_none(page: Page, data):
    page.goto("/Person")
    hydrated(page)
    page.get_by_role("searchbox").fill("zzzzz")
    expect(results(page)).to_have_count(0)
    expect(page.get_by_title("Found")).to_have_text("0")
    expect(page.get_by_title("Found")).to_have_class(re.compile("text-red-800"))


def test_an_address_with_a_search_shows_it(page: Page, data):
    page.goto("/Person?q=Marie")
    expect(results(page)).to_have_count(1)
    expect(page.get_by_role("searchbox")).to_have_value("Marie")
    expect(page.get_by_role("link", name="Marie of Burgundy")).to_be_visible()


def test_a_deep_search_looks_in_the_documents_and_is_made_when_asked_for(
    page: Page, data
):
    # ("Ghent" is in a statement about Marie, not in her label: an ordinary search does not find it)
    page.goto("/Person?q=Ghent")
    expect(results(page)).to_have_count(0)
    page.goto("/Person")
    hydrated(page)
    deep = page.get_by_role("button", name="Deep search", exact=True)
    expect(deep).to_have_attribute("aria-pressed", "false")
    deep.click()
    expect(deep).to_have_attribute("aria-pressed", "true")
    page.get_by_role("searchbox").fill("Ghent")
    # (a deep search is slow, so typing makes none: all three are still listed)
    page.wait_for_timeout(600)
    expect(results(page)).to_have_count(3)
    page.get_by_role("searchbox").press("Enter")
    page.wait_for_url(re.compile(r"deep=1"))
    expect(results(page)).to_have_count(1)
    expect(page.get_by_role("link", name="Marie of Burgundy")).to_be_visible()
    # (turning it off goes back to the ordinary search of the same text, which finds nothing)
    deep.click()
    expect(deep).to_have_attribute("aria-pressed", "false")
    expect(results(page)).to_have_count(0)


def test_the_run_button_makes_a_deep_search(page: Page, data):
    page.goto("/Person")
    hydrated(page)
    page.get_by_role("button", name="Deep search", exact=True).click()
    page.get_by_role("searchbox").fill("Ghent")
    run = page.get_by_role("button", name="Run deep search (Enter)")
    expect(run).to_be_enabled()
    run.click()
    expect(results(page)).to_have_count(1)
    # (it is up to date: there is nothing to run)
    expect(run).to_be_disabled()


def test_an_item_shows_its_fields_and_what_it_refers_to(page: Page, data):
    page.goto("/Person")
    page.get_by_role("link", name="Maximilian").click()
    page.wait_for_url(f"**/Person/{data.maximilian}")
    expect(page.get_by_role("heading", name="Maximilian")).to_be_visible()
    expect(page.get_by_text("Has role", exact=True)).to_be_visible()
    page.get_by_role("link", name="Maximilian's secretary").click()
    page.wait_for_url(f"**/Role/{data.secretary_role}")
    expect(page.get_by_role("heading", name="Maximilian's secretary")).to_be_visible()
    # (a field that is a type, and what refers to this role from the other side)
    expect(page.get_by_text("Has type", exact=True)).to_be_visible()
    expect(page.get_by_role("link", name=re.compile(r"\bSecretary$"))).to_be_visible()
    expect(page.get_by_role("link", name=re.compile(r"\bMaximilian$"))).to_be_visible()


def test_a_type_in_a_field_leads_to_the_page_of_the_type(page: Page, data):
    page.goto(f"/Role/{data.secretary_role}")
    page.get_by_role("link", name=re.compile(r"\bSecretary$")).click()
    page.wait_for_url(f"**/RoleType/{data.type_id('Secretary')}")
    expect(page.get_by_role("navigation", name="Path")).to_have_text(
        "All›Clerk›Secretary"
    )
    expect(page.get_by_role("link", name="Maximilian's secretary")).to_be_visible()


def test_an_item_with_nothing_to_show_has_no_empty_rows(page: Page, data):
    page.goto(f"/Person/{data.charles}")
    expect(page.get_by_role("heading", name="Charles the Bold")).to_be_visible()
    expect(page.get_by_text("Has role", exact=True)).to_have_count(0)


def test_a_long_list_is_loaded_as_it_is_scrolled_and_starts_where_it_was_left(
    page: Page, types
):
    # (more than a page, LIST_PAGE_SIZE: 50; numbered so each label is its own)
    api = types.admin()
    for number in range(130):
        api.ok("POST", "/api/Person", {"label": f"Person {number:03d}", "has_role": []})
    page.goto("/Person")
    hydrated(page)
    expect(page.get_by_title("Found")).to_have_text("130")
    # (only what is on show, and a few beyond, is rendered)
    assert results(page).count() < 60

    # The last ones are fetched when they are scrolled to
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    expect(page.locator("main ul > li[data-index='129'] a")).to_be_visible()

    # Where it is is kept in the address, and the page loaded again starts there
    page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
    page.wait_for_url(re.compile(r"[?&]at=\d+"))
    at = int(re.search(r"at=(\d+)", page.url).group(1))  # ty: ignore[possibly-missing-attribute]
    assert 30 < at < 110
    label = page.locator(f"main ul > li[data-index='{at}']").text_content()
    page.reload()
    hydrated(page)
    expect(page.locator(f"main ul > li[data-index='{at}']")).to_have_text(label or "")
    expect(page.locator(f"main ul > li[data-index='{at}']")).to_be_in_viewport()

    # A new search starts at the top
    page.get_by_role("searchbox").fill("Person 00")
    expect(page.get_by_title("Found")).not_to_have_text("130")
    page.wait_for_url(re.compile(r"q=Person"))
    assert "at=" not in page.url
    assert page.evaluate("window.scrollY") == 0
