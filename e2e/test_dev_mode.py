"""The pages in the development build of Solid, which stops on mistakes that the production build lets through
(such as state written while a page is rendered: `REACTIVE_WRITE_IN_OWNED_SCOPE`), so the other tests, which use the
built interface, do not see them. Each test goes through pages as a person would, mostly by following links (what is
rendered in the browser, not on the server), and fails on any error in the page."""

import re

import pytest
from helpers import drag, expand_nav, hydrated, row
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
    # (a new entity of one of several types: the dialog shows the types first, then the form of the one chosen)
    page.goto(f"{dev_url}/Meeting/new")
    hydrated(page)
    page.get_by_role("button", name="Make a new one").click()
    dialog = page.get_by_role("dialog", name="Select a type…")
    dialog.get_by_role("button", name="Group", exact=True).click()
    expect(page.get_by_role("dialog", name="New Group")).to_be_visible()
    page.get_by_role("button", name="‹ Back").click()
    dialog.get_by_role("button", name="Person", exact=True).click()
    dialog = page.get_by_role("dialog", name="New Person")
    expect(dialog.get_by_label("Label", exact=True)).to_be_focused()
    dialog.get_by_label("Label", exact=True).fill("Bede")
    dialog.get_by_role("button", name="Save").click()
    expect(dialog).to_have_count(0)
    expect(page.get_by_text("Bede", exact=True)).to_be_visible()
    expect(page.locator("main")).not_to_contain_text(SOLID_ERROR)
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


def test_a_typology_changed_in_the_tree(
    page: Page, types, dev_url: str, errors: list[str]
):
    """The tree's live feed from the dev server's own server functions, a drag and a label edited in place"""
    from conftest import PASSWORD, USERNAME

    response = page.request.post(
        f"{dev_url}/api/users/session",
        form={"username": USERNAME, "password": PASSWORD},
    )
    assert response.ok, response.text()
    page.goto(f"{dev_url}/RoleType")
    hydrated(page)
    drag(page, "Advisor", "Clerk")
    expect(row(page, "Advisor")).to_have_attribute("data-depth", "1")
    row(page, "Secretary").hover()
    page.get_by_role("button", name="Edit the label of Secretary").click()
    field = page.get_by_role("textbox", name="Label of Secretary")
    field.fill("Scribe")
    field.press("Enter")
    expect(row(page, "Scribe")).to_be_visible()
    expect(page.locator("main")).not_to_contain_text(SOLID_ERROR)
    assert errors == []


def test_the_review_panel(page: Page, types, dev_url: str, errors: list[str]):
    """The review button and panel (the module of pangloss_review), with its live feed from the dev server's own
    server functions: a comment by someone else arrives, and one is written, resolved and the status changed"""
    from conftest import (
        AUTHOR_PASSWORD,
        AUTHOR_USERNAME,
        OTHER_PASSWORD,
        OTHER_USERNAME,
        PASSWORD,
        USERNAME,
        forget,
    )

    forget("Report", "ReportSection", "PGReviewComment")
    made = types.client(AUTHOR_USERNAME, AUTHOR_PASSWORD).ok(
        "POST",
        "/api/Report",
        {
            "label": "Dev report",
            "text": "Text",
            "sections": [{"type": "ReportSection", "label": "A part", "body": "B"}],
            "findings": [],
        },
    )
    response = page.request.post(
        f"{dev_url}/api/users/session",
        form={"username": USERNAME, "password": PASSWORD},
    )
    assert response.ok, response.text()
    page.goto(f"{dev_url}/Report/{made['id']}")
    hydrated(page)
    console = page.get_by_role("banner", name="Console")
    console.get_by_role("button", name="Review: Unchecked").click()
    panel = page.get_by_role("complementary", name="Review")
    types.client(OTHER_USERNAME, OTHER_PASSWORD).ok(
        "POST", f"/api/review/{made['id']}/comments", {"text": "From bob"}
    )
    expect(panel.get_by_text("From bob")).to_be_visible(timeout=10_000)
    box = panel.get_by_role("combobox", name="Comment")
    box.press_sequentially("From me about #a pa")
    box.press("Enter")
    expect(box).to_have_value(re.compile(r"^From me about #[0-9a-f-]{36} $"))
    panel.get_by_role("button", name="Send").click()
    expect(
        panel.get_by_test_id("review-comment").filter(has_text="From me")
    ).to_have_attribute("data-mine", "true")
    expect(
        panel.get_by_test_id("review-comment")
        .filter(has_text="From me")
        .get_by_test_id("review-ref")
    ).to_have_text("Report sectionA part")
    panel.get_by_test_id("review-comment").filter(has_text="From bob").get_by_role(
        "button", name="Resolve"
    ).click()
    panel.get_by_role("button", name="Checked", exact=True).click()
    expect(
        console.get_by_role("button", name="Review: Checked, open comments: 1")
    ).to_be_visible()
    page.get_by_role("link", name=re.compile("^Edit")).click()
    page.wait_for_url(re.compile(r"/edit$"))
    expect(
        console.get_by_role("button", name=re.compile("^Review: Checked"))
    ).to_be_visible()
    expect(page.locator("main")).not_to_contain_text(SOLID_ERROR)
    assert errors == []
    # (the queue page: it was checked above)
    page.goto(f"{dev_url}/review?status=checked")
    expect(page.get_by_role("heading", name="Documents to review")).to_be_visible()
    expect(page.get_by_test_id("review-queue-row").first).to_contain_text("Dev report")
    expect(page.locator("main")).not_to_contain_text(SOLID_ERROR)
    assert errors == []


def test_the_calendar(page: Page, dated, dev_url: str, errors: list[str]):
    """The years, a month and a day, by following the links, without an error of the development build"""
    page.goto(f"{dev_url}/calendar")
    hydrated(page)
    page.get_by_test_id("calendar-year").nth(1).get_by_role(
        "link", name="March 1500"
    ).click()
    expect(
        page.get_by_test_id("calendar-month").get_by_role(
            "link", name="Event Coronation"
        )
    ).to_be_visible()
    page.get_by_test_id("calendar-month").get_by_role(
        "link", name="2 March 1500", exact=True
    ).click()
    expect(
        page.get_by_role("heading", name=re.compile("^Monday 2 March 1500"))
    ).to_be_visible()
    page.get_by_role("link", name="Next day").click()
    expect(
        page.get_by_role("heading", name=re.compile("^Tuesday 3 March 1500"))
    ).to_be_visible()
    page.get_by_role("banner", name="Console").get_by_role(
        "link", name="Julian"
    ).click()
    expect(
        page.get_by_role("heading", name=re.compile("^Tuesday 13 March 1500"))
    ).to_be_visible()
    page.get_by_role("banner", name="Console").get_by_role("link", name="Years").click()
    expect(page.get_by_role("heading", name=re.compile("^Years"))).to_be_visible()
    assert errors == []
