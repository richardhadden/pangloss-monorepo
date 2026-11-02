"""The pages in the development build of Solid, which stops on mistakes that the production build lets through
(such as state written while a page is rendered: `REACTIVE_WRITE_IN_OWNED_SCOPE`), so the other tests, which use the
built interface, do not see them. Each test goes through pages as a person would, mostly by following links (what is
rendered in the browser, not on the server), and fails on any error in the page."""

import re

import pytest
from helpers import expand_nav, hydrated
from playwright.sync_api import Page, expect


# (what an error of the development build of Solid says first: `[PRIMITIVE_IN_FORBIDDEN_SCOPE] Cannot create ...`)
SOLID_ERROR = re.compile(r"\[[A-Z]+(_[A-Z]+)+\]")


@pytest.fixture
def errors(page: Page) -> list[str]:
    found: list[str] = []
    page.on("pageerror", lambda error: found.append(str(error)))
    return found


def test_lists_items_and_searching(page: Page, data, dev_url: str, errors: list[str]):
    page.goto(f"{dev_url}/")
    hydrated(page)
    page.get_by_role("link", name="Person", exact=True).click()
    expect(page.get_by_role("link", name="Maximilian")).to_be_visible()
    page.get_by_role("searchbox").fill("Marie")
    expect(page.get_by_title("Found")).to_have_text("1")
    page.get_by_role("searchbox").fill("")
    expect(page.get_by_title("Found")).to_have_text("3")
    page.get_by_role("link", name="Maximilian").click()
    expect(page.get_by_role("heading", name="Maximilian")).to_be_visible()
    page.go_back()
    expect(page.get_by_role("link", name="Charles the Bold")).to_be_visible()
    page.goto(f"{dev_url}/Statement/{data.statement}")
    expect(page.get_by_role("heading", name="Court at Ghent")).to_be_visible()
    assert errors == []


def test_the_search_form(page: Page, data, dev_url: str, errors: list[str]):
    page.goto(f"{dev_url}/Person")
    hydrated(page)
    page.get_by_role("button", name="Search by fields").click()
    page.get_by_role(
        "combobox", name=re.compile("^Condition on has role", re.I)
    ).select_option("missing")
    expect(page.get_by_title("Found")).to_have_text("1")
    page.get_by_role(
        "combobox", name=re.compile("^Condition on has role", re.I)
    ).select_option("match")
    page.get_by_role("button", name="Choose a type").click()
    page.get_by_role("menuitem", name="Role", exact=True).click()
    page.locator('[data-search-node="Role"]').get_by_role("textbox", name="Label").fill(
        "secretary"
    )
    expect(page.get_by_title("Found")).to_have_text("1")
    page.get_by_role("combobox", name="Add what refers to it").last.select_option(
        label="Statement · About"
    )
    expect(page.get_by_title("Found")).to_have_text("0")
    # (the address of a search made with the form, opened again)
    page.reload()
    hydrated(page)
    expect(page.locator('[data-search-node="Statement"]')).to_be_visible()
    expect(page.locator("main")).not_to_contain_text(SOLID_ERROR)
    page.get_by_role("button", name="Clear").click()
    # (the nested forms go with what was in them: one form, so one group of alternatives to add)
    expect(page.get_by_role("button", name="+ Add alternatives")).to_have_count(1)
    page.get_by_role("button", name="+ Add alternatives").click()
    page.get_by_role("group", name="Alternatives 1").get_by_role(
        "textbox", name="Label", exact=True
    ).first.fill("Max")
    page.get_by_role("combobox", name="Order by").select_option("label")
    expect(page.get_by_title("Found")).to_have_text("1")
    page.get_by_role("button", name="Save…").click()
    page.get_by_role("textbox", name="Name of this search").fill("Max")
    page.get_by_role("button", name="Save", exact=True).click()
    page.get_by_role("button", name="Clear").click()
    page.get_by_role("combobox", name="Saved searches").select_option("Max")
    expect(page.get_by_title("Found")).to_have_text("1")
    page.get_by_role("button", name="Clear").click()
    expect(page.get_by_title("Found")).to_have_text("3")
    assert errors == []


def test_pages_that_are_not_there(page: Page, data, dev_url: str, errors: list[str]):
    page.goto(f"{dev_url}/Person")
    hydrated(page)
    # (an item deleted after the list was read: its page is rendered in the browser)
    data.api.ok("DELETE", f"/api/Person/{data.charles}")
    page.get_by_role("link", name="Charles the Bold").click()
    expect(page.get_by_role("heading", name="Page not found")).to_be_visible()
    page.go_back()
    expect(page.get_by_role("link", name="Maximilian")).to_be_visible()
    page.goto(f"{dev_url}/this/is/not/a/page")
    expect(page.get_by_role("heading", name="Page not found")).to_be_visible()
    assert errors == []


def test_making_and_editing(page: Page, data, dev_url: str, errors: list[str]):
    from conftest import PASSWORD, USERNAME

    # (logged in at the development server's own address: `logged_in` is for the other one)
    response = page.request.post(
        f"{dev_url}/api/users/session",
        form={"username": USERNAME, "password": PASSWORD},
    )
    assert response.ok, response.text()
    page.goto(f"{dev_url}/Statement/{data.statement}")
    hydrated(page)
    page.get_by_role("link", name=re.compile("^Edit")).click()
    page.wait_for_url(re.compile(r"/edit$"))
    expect(page.get_by_role("button", name="Save")).to_be_visible()
    # (an error that the page's boundary catches is no error in the page, but shown in place of the form: the
    # Save button is in the console, outside it, so the form itself is looked for)
    expect(page.get_by_role("textbox", name="Text")).to_be_visible()
    expect(page.locator("main")).not_to_contain_text(SOLID_ERROR)
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_role("status", name="Notifications")).to_contain_text("saved")
    page.goto(f"{dev_url}/Statement/new")
    hydrated(page)
    expect(page.get_by_role("button", name="Save")).to_be_visible()
    # (the filter of the types in the navigation bar)
    expand_nav(page)
    page.get_by_label("Filter types").fill("stat")
    expect(
        page.get_by_role("navigation", name="Main").get_by_role("link", name="Person")
    ).to_have_count(0)
    page.get_by_role("button", name="Clear the filter").click()
    assert errors == []


def test_a_typology(page: Page, types, dev_url: str, errors: list[str]):
    page.goto(f"{dev_url}/RoleType")
    hydrated(page)
    page.get_by_role("link", name="Secretary").first.click()
    page.wait_for_url(f"**/RoleType/{types.type_id('Secretary')}")
    path = page.get_by_role("navigation", name="Path")
    expect(path).to_have_text("All›Clerk›Secretary")
    path.get_by_role("link", name="Clerk").click()
    expect(page.get_by_role("navigation", name="Path")).to_have_text("All›Clerk")
    assert errors == []
