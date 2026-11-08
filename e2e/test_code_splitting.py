"""What the built interface fetches: code only for someone logged in, or only for a form, is not fetched by a reader
who does not need it, and is there for one who does. Only a browser on the built interface can show this."""

import re

from helpers import hydrated
from playwright.sync_api import Page, expect

FOR_LOGGED_IN = re.compile(r"/(ReviewAction|ReviewPanel|HistoryAction|ZoteroLinkAction)-")
FORM = re.compile(r"/(ItemForm|ModelFields|SearchPanel)-")
ASSET = "/assets/"


def fetching(page: Page) -> list[str]:
    """The code the page fetches from now on"""
    fetched: list[str] = []
    page.on(
        "request",
        lambda request: fetched.append(request.url) if ASSET in request.url else None,
    )
    return fetched


def test_a_page_read_by_someone_logged_out_fetches_neither_forms_nor_review_or_history(
    page: Page, data
):
    fetched = fetching(page)
    page.goto("/Person")
    hydrated(page)
    expect(page.get_by_role("link", name="Maximilian")).to_be_visible()
    page.goto(f"/Person/{data.maximilian}")
    hydrated(page)
    page.wait_for_load_state("networkidle")
    assert fetched, "nothing was seen being fetched"
    assert [url for url in fetched if FOR_LOGGED_IN.search(url)] == []
    assert [url for url in fetched if FORM.search(url)] == []


def test_the_search_form_is_fetched_when_it_is_opened(page: Page, data):
    fetched = fetching(page)
    page.goto("/Person")
    hydrated(page)
    assert [url for url in fetched if "/SearchPanel-" in url] == []
    page.get_by_role("button", name="Search by fields").click()
    expect(page.get_by_role("region", name=re.compile("^Search .* by fields"))).to_be_visible()
    assert [url for url in fetched if "/SearchPanel-" in url]


def test_someone_logged_in_fetches_what_the_console_of_an_item_offers_them(
    page: Page, data, logged_in
):
    fetched = fetching(page)
    page.goto(f"/Person/{data.maximilian}")
    hydrated(page)
    expect(page.get_by_role("button", name="History")).to_be_visible()
    assert [url for url in fetched if "/HistoryAction-" in url]
