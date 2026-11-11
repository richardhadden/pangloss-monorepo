"""The pages in the development build of Solid, which stops on mistakes that the production build lets through
(such as state written while a page is rendered: `REACTIVE_WRITE_IN_OWNED_SCOPE`), so the other tests, which use the
built interface, do not see them. Each test goes through pages as a person would, mostly by following links (what is
rendered in the browser, not on the server), and fails on any error in the page."""

import re

import pytest
from helpers import add_filter, drag, expand_nav, hydrated, pick, row
from playwright.sync_api import Page, expect

# (what an error of the development build of Solid says first: `[PRIMITIVE_IN_FORBIDDEN_SCOPE] Cannot create ...`)
SOLID_ERROR = re.compile(r"\[[A-Z]+(_[A-Z]+)+\]")


@pytest.fixture
def errors(page: Page) -> list[str]:
    found: list[str] = []
    page.on("pageerror", lambda error: found.append(str(error)))
    return found


def test_homepage_and_a_page(page: Page, data, dev_url: str, errors: list[str]):
    page.goto(f"{dev_url}/")
    hydrated(page)
    box = page.get_by_role("searchbox", name="Quick search")
    box.press_sequentially("person Max")
    expect(page.locator("main li a", has_text="Maximilian").first).to_be_visible()
    box.fill("")
    page.get_by_role("navigation", name="Pages").get_by_role(
        "link", name="About"
    ).click()
    expect(page.get_by_role("heading", level=1, name="About")).to_be_visible()
    assert errors == []
    assert not any(SOLID_ERROR.search(text) for text in errors)


def test_homepage_opened_with_a_search(
    page: Page, data, dev_url: str, errors: list[str]
):
    page.goto(f"{dev_url}/?q=ma&type=Person")
    hydrated(page)
    expect(page.locator("main li a", has_text="Maximilian").first).to_be_visible()
    assert errors == []


def test_lists_items_and_searching(page: Page, data, dev_url: str, errors: list[str]):
    page.goto(f"{dev_url}/Person")
    hydrated(page)
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
    add_filter(page, "has role")
    pick(
        page.get_by_role("combobox", name=re.compile("^Condition on has role", re.I)),
        "missing",
    )
    expect(page.get_by_title("Found")).to_have_text("1")
    pick(
        page.get_by_role("combobox", name=re.compile("^Condition on has role", re.I)),
        "match",
    )
    # (only roles are there: the button chooses the type)
    expect(
        page.locator('button[aria-haspopup="menu"]', has_text="Choose a type")
    ).to_have_count(0)
    page.get_by_role("button", name="Choose a type").click()
    role = page.locator('[data-search-node="Role"]')
    add_filter(role, "Label")
    role.get_by_role("textbox", name="Label").fill("secretary")
    expect(page.get_by_title("Found")).to_have_text("1")
    add_filter(page, "Referred to by")
    pick(
        page.get_by_role("combobox", name="Add what refers to it").last,
        label="Statement · About",
    )
    expect(page.get_by_title("Found")).to_have_text("0")
    # (the address of a search made with the form, opened again)
    page.reload()
    hydrated(page)
    expect(page.locator('[data-search-node="Statement"]')).to_be_visible()
    expect(page.locator("main")).not_to_contain_text(SOLID_ERROR)
    page.get_by_role("button", name="Clear").click()
    # (the nested forms go with what was in them: one form, so one menu to add a filter)
    expect(page.get_by_role("combobox", name="Add a filter")).to_have_count(1)
    add_filter(page, "Any of")
    alternative = (
        page.get_by_role("group", name="Alternatives 1")
        .locator('[data-search-node="Person"]')
        .first
    )
    add_filter(alternative, "Label")
    alternative.get_by_role("textbox", name="Label", exact=True).fill("Max")
    add_filter(page, "Order by")
    pick(page.get_by_role("combobox", name="Order by"), "label")
    expect(page.get_by_title("Found")).to_have_text("1")
    page.get_by_role("button", name="Save…").click()
    page.get_by_role("textbox", name="Name of this search").fill("Max")
    page.get_by_role("button", name="Save", exact=True).click()
    page.get_by_role("button", name="Clear").click()
    pick(page.get_by_role("combobox", name="Saved searches"), "Max")
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
    # (Save is on once there is a change)
    page.get_by_role("textbox", name="Text").fill("Marie held court at Ghent, again")
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
    # (the shortcut, with the bar closed: the filter is made, and then takes the cursor)
    page.mouse.move(800, 400)
    expect(page.get_by_label("Filter types")).to_have_count(0)
    page.keyboard.press("ControlOrMeta+k")
    expect(page.get_by_label("Filter types")).to_be_focused()
    page.keyboard.press("Escape")
    expect(page.get_by_label("Filter types")).to_have_count(0)
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
    panel.get_by_role("button", name="Published", exact=True).click()
    expect(
        console.get_by_role("button", name="Review: Published, open comments: 1")
    ).to_be_visible()
    page.get_by_role("link", name=re.compile("^Edit")).click()
    page.wait_for_url(re.compile(r"/edit$"))
    expect(
        console.get_by_role("button", name=re.compile("^Review: Published"))
    ).to_be_visible()
    expect(page.locator("main")).not_to_contain_text(SOLID_ERROR)
    assert errors == []
    # (the queue page: it was checked above)
    page.goto(f"{dev_url}/review?status=published")
    expect(page.get_by_role("heading", name="Documents to review")).to_be_visible()
    expect(page.get_by_test_id("review-queue-row").first).to_contain_text("Dev report")
    expect(page.locator("main")).not_to_contain_text(SOLID_ERROR)
    assert errors == []


def test_the_users_pages(page: Page, data, dev_url: str, errors: list[str]):
    """The list of users and a user's page, without an error of the development build"""
    from conftest import PASSWORD, USERNAME

    response = page.request.post(
        f"{dev_url}/api/users/session",
        form={"username": USERNAME, "password": PASSWORD},
    )
    assert response.ok, response.text()
    page.goto(f"{dev_url}/users")
    hydrated(page)
    page.get_by_test_id("users-row").get_by_role("link", name=USERNAME, exact=True).click()
    expect(page.get_by_test_id("user-item").first).to_be_visible()
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
    # (the long periods over the day, read by the button)
    covering = page.get_by_test_id("calendar-covering")
    covering.get_by_role("button", name="Show them").click()
    expect(covering.get_by_role("link", name="Event Reign of the king")).to_be_visible()
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


def test_the_history_panel_and_page(page: Page, types, dev_url: str, errors: list[str]):
    """The history button, panel and drawer (the module of pangloss_history), a restore, and the page of every version,
    reached by its link, on a document with parts inside it"""
    import time

    from conftest import PASSWORD, USERNAME, forget

    forget("Report", "ReportSection")
    api = types.admin()
    made = api.ok(
        "POST",
        "/api/Report",
        {
            "label": "Dev history",
            "text": "First text",
            "sections": [{"type": "ReportSection", "label": "A part", "body": "B"}],
            "findings": [],
        },
    )
    edit = api.ok("GET", f"/api/Report/{made['id']}/edit")
    status, result = api.send(
        "PUT",
        f"/api/Report/{made['id']}",
        {**edit, "text": "Second text", "sections": []},
        headers={"If-Match": "*"},
    )
    assert status < 300, result
    # (the versions are recorded just after the writes)
    deadline = time.monotonic() + 10
    while True:
        status, listing = api.send("GET", f"/api/Report/{made['id']}/history")
        if status == 200 and len(listing["versions"]) >= 2:
            break
        assert time.monotonic() < deadline, (status, listing)
        time.sleep(0.1)
    response = page.request.post(
        f"{dev_url}/api/users/session",
        form={"username": USERNAME, "password": PASSWORD},
    )
    assert response.ok, response.text()
    page.goto(f"{dev_url}/Report/{made['id']}")
    hydrated(page)
    page.get_by_role("button", name="History", exact=True).click()
    panel = page.get_by_test_id("history-panel")
    expect(panel).to_have_attribute("data-open", "true")
    panel.locator('[data-testid="history-version"][data-version="1"]').click()
    expect(page.get_by_test_id("history-drawer")).to_contain_text("A part")
    page.get_by_test_id("history-restore").click()
    expect(page.get_by_test_id("history-change-row")).to_have_count(2)
    page.get_by_test_id("history-restore-confirm").click()
    expect(page.get_by_text("Restored version 1 as version 3")).to_be_visible()
    expect(page.locator("main")).to_contain_text("First text")
    panel.get_by_test_id("history-compare").click()
    page.wait_for_url(re.compile(r"/history$"))
    expect(page.get_by_test_id("history-column")).to_have_count(3)
    expect(page.locator("main")).not_to_contain_text(SOLID_ERROR)
    assert errors == []


def test_what_refers_to_a_person_by_date(
    page: Page, appointed, dev_url: str, errors: list[str]
):
    page.goto(f"{dev_url}/Person/{appointed.ada}")
    hydrated(page)
    page.get_by_role("button", name="Sort by date").click()
    expect(page.get_by_test_id("dated-item")).to_have_count(3)
    # (the timeline scrolls the page, which it then follows: no write while rendering in the dev build)
    page.get_by_role("slider", name="Go to year").press("End")
    page.mouse.wheel(0, -400)
    # (the next person's page, by a link, and back: the choice is kept)
    page.get_by_role("link", name=re.compile("Bishop")).click()
    expect(page.get_by_role("heading", name="Bishop")).to_be_visible()
    page.go_back()
    expect(page.get_by_test_id("dated-item")).to_have_count(3)
    page.get_by_role("button", name="Sort by date").click()
    expect(page.get_by_test_id("dated-item")).to_have_count(0)
    expect(page.locator("main")).not_to_contain_text(SOLID_ERROR)
    assert errors == []


def test_a_book_from_zotero_and_unlinked(
    page: Page, types, dev_url: str, errors: list[str]
):
    """The module of pangloss_zotero: the *Zotero item* row of the form of a new Book, its picker, Save, and *Unlink* in
    the console of the Book"""
    from conftest import PASSWORD, USERNAME
    from test_zotero import forget_items, pick, seed

    forget_items()
    made = seed(types, "DEVONE")
    response = page.request.post(
        f"{dev_url}/api/users/session",
        form={"username": USERNAME, "password": PASSWORD},
    )
    assert response.ok, response.text()
    page.goto(f"{dev_url}/Book/new")
    hydrated(page)
    page.get_by_role("button", name="Find in the library").click()
    pick(page, "Smith, DEVONE")
    expect(page.get_by_test_id("zotero-based-on")).to_contain_text("Smith, DEVONE")
    page.get_by_role("button", name="Save").click()
    page.wait_for_url(re.compile(rf"/Book/{made['DEVONE']}$"))
    page.get_by_role("button", name="Unlink from Zotero").click()
    page.get_by_test_id("zotero-unlink-dialog").get_by_role(
        "button", name="Unlink from Zotero"
    ).click()
    expect(page.get_by_role("button", name="Link to Zotero")).to_be_visible()
    expect(page.locator("main")).not_to_contain_text(SOLID_ERROR)
    assert errors == []


def test_the_list_of_zotero_items_and_an_items_page(
    page: Page, types, dev_url: str, errors: list[str]
):
    """What is only on the pages of Zotero items: the list of what is used, its button and bubbles, and the item's page"""
    from test_zotero import forget_items, seed

    forget_items()
    made = seed(types, "DEVTWO")
    page.goto(f"{dev_url}/ZoteroObject")
    hydrated(page)
    expect(page.get_by_title("Found")).to_have_text("0")
    page.get_by_role("button", name="Show all").click()
    expect(page.get_by_test_id("use-count")).to_have_text("0")
    page.get_by_role("link", name=re.compile("DEVTWO")).click()
    expect(page.get_by_test_id("zotero-item")).to_contain_text("The book DEVTWO")
    page.goto(f"{dev_url}/ZoteroObject/{made['DEVTWO']}")
    expect(page.get_by_test_id("zotero-item")).to_contain_text("The book DEVTWO")
    expect(page.locator("main")).not_to_contain_text(SOLID_ERROR)
    assert errors == []


def test_narrowing_and_widening_a_document_in_a_form(
    page: Page, provenance, dev_url: str, errors: list[str]
):
    from conftest import PASSWORD, USERNAME

    response = page.request.post(
        f"{dev_url}/api/users/session",
        form={"username": USERNAME, "password": PASSWORD},
    )
    assert response.ok, response.text()
    page.goto(f"{dev_url}/Provenance/{provenance.of_artwork}/edit")
    hydrated(page)
    narrow = page.get_by_role("button", name="Narrow Making it to a type below it")
    narrow.click()
    menu = page.get_by_role("menu")
    # (one that cannot be chosen, saying why; one that can)
    expect(menu.locator("[data-reason]")).to_have_text("Would lose: Object created")
    menu.locator("[data-unavailable]").click(force=True)
    menu.get_by_role("menuitem", name="Creation of artwork").click()
    expect(
        page.locator(f"[data-item-id='{provenance.artwork_step}'] [data-tint]").first
    ).to_have_text("Creation of artwork")
    # (and back, which loses nothing: no question)
    page.get_by_role("button", name="Widen Making it to a type above it").click()
    expect(page.get_by_role("dialog")).to_have_count(0)
    # (the document is as it was loaded: nothing to save)
    expect(page.get_by_role("button", name="Save")).to_be_disabled()
    # (every block folded from the console, and unfolded again)
    head = page.get_by_role("button", name=re.compile("^Fold or unfold")).first
    expect(head).to_have_attribute("aria-expanded", "true")
    page.get_by_role("button", name="Fold all").click()
    expect(head).to_have_attribute("aria-expanded", "false")
    page.get_by_role("button", name="Unfold all").click()
    expect(head).to_have_attribute("aria-expanded", "true")
    # (a new one whose subject a creation of a painting cannot hold: said at the field)
    page.goto(f"{dev_url}/Provenance/new")
    hydrated(page)
    page.locator("form").get_by_role("combobox").first.fill("thing")
    page.get_by_role("option", name=re.compile("The thing")).click()
    page.get_by_role("button", name="Add Steps").click()
    page.get_by_role("button", name="Creation of painting", exact=True).click()
    expect(page.get_by_text("cannot go here: choose one that can")).to_be_visible()
    expect(page.locator("main")).not_to_contain_text(SOLID_ERROR)
    assert errors == []


def test_leaving_and_stashing(page: Page, data, dev_url: str, errors: list[str]):
    from conftest import PASSWORD, USERNAME

    response = page.request.post(
        f"{dev_url}/api/users/session",
        form={"username": USERNAME, "password": PASSWORD},
    )
    assert response.ok, response.text()
    page.goto(f"{dev_url}/Statement/new")
    hydrated(page)
    page.get_by_role("textbox", name="Text").fill("Half done")
    page.get_by_role("button", name="Cancel").click()
    dialog = page.get_by_role("dialog", name="Leave without saving?")
    dialog.get_by_label("A label, to know it by").fill("A stashed statement")
    dialog.get_by_role("button", name="Stash and leave").click()
    page.wait_for_url(re.compile(r"/Statement$"))
    stashed = page.get_by_role("region", name="Stashed")
    expect(stashed).to_contain_text("A stashed statement")
    stashed.get_by_role("button", name=re.compile("^Stashed")).click()
    stashed.get_by_role("link", name="Go on with A stashed statement").click()
    page.wait_for_url(re.compile(r"/Statement/new\?stash="))
    expect(page.get_by_role("textbox", name="Text")).to_have_value("Half done")
    expect(page.locator("main")).not_to_contain_text(SOLID_ERROR)
    # (opened from the stash, and taken up again on a page loaded afresh: read once settled)
    page.reload()
    hydrated(page)
    expect(page.get_by_role("textbox", name="Text")).to_have_value("Half done")
    expect(page.locator("main")).not_to_contain_text(SOLID_ERROR)
    assert errors == []


def test_the_popup_of_a_type(page: Page, data, dev_url: str, errors: list[str]):
    page.goto(f"{dev_url}/Person")
    hydrated(page)
    page.get_by_role("link", name="Maximilian").locator(
        "[data-type-info]"
    ).first.hover()
    page.keyboard.down("Alt")
    expect(page.get_by_role("tooltip")).to_contain_text("Person")
    page.keyboard.up("Alt")
    expect(page.get_by_role("tooltip")).to_have_count(0)
    assert errors == []


def test_the_admin_page(page: Page, data, dev_url: str, errors: list[str]):
    from conftest import PASSWORD, USERNAME

    response = page.request.post(
        f"{dev_url}/api/users/session",
        form={"username": USERNAME, "password": PASSWORD},
    )
    assert response.ok, response.text()
    page.goto(f"{dev_url}/admin")
    hydrated(page)
    expect(page.get_by_test_id("admin-job-form-rdf_dump")).to_be_visible()
    expect(page.get_by_test_id("users-admin-row").first).to_be_visible()
    assert errors == []
    assert not any(SOLID_ERROR.search(text) for text in errors)


def test_the_quick_search_popup(page: Page, data, dev_url: str, errors: list[str]):
    """Opening an item in the popup, without an error of the development build"""
    page.goto(f"{dev_url}/Statement")
    hydrated(page)
    page.keyboard.press("/")
    popup = page.get_by_test_id("quick-search")
    popup.get_by_role("searchbox").fill("Maximilian")
    expect(
        popup.get_by_test_id("quick-search-results").get_by_role("link").first
    ).to_be_visible()
    page.keyboard.press("Enter")
    expect(popup.get_by_test_id("quick-search-back")).to_be_visible()
    page.wait_for_timeout(500)
    expect(popup).not_to_contain_text(SOLID_ERROR)
    assert errors == []


def test_the_tasks_of_review(page: Page, types, dev_url: str, errors: list[str]):
    """An unreconciled mention reconciled in its dialog, an identification confirmed, the form of both, and the pages
    of tasks, without an error of the development build"""
    from conftest import PASSWORD, TOOLCHAIN, USERNAME, forget

    forget("Hearing", "Testimony", "Unreconciled", "Witness", "IdentificationByToolchain")
    api = types.admin()
    john = api.ok("POST", "/api/Witness", {"label": "Dev witness"})["id"]

    def hearing(label: str, **testimony) -> str:
        made = api.ok(
            "POST",
            f"/api/Hearing?toolchain={TOOLCHAIN}",
            {
                "label": label,
                "testimonies": [
                    {
                        "type": "Testimony",
                        "label": f"{label}: testimony",
                        "givenBy": [],
                        "names": [],
                        **testimony,
                    }
                ],
            },
        )
        return made["id"]

    def mention(label: str) -> dict:
        return {"type": "Unreconciled", "unreconciledType": "Witness", "label": label}

    suggestion = {
        "type": "IdentificationByToolchain",
        "target": [
            {
                "type": "WeightedAlternative",
                "alternatives": [
                    {"type": "Witness", "id": john, "edgeProperties": {"percent": 100}}
                ],
            }
        ],
    }
    first = hearing("Dev hearing", givenBy=[mention("Dev mention")], names=[suggestion])
    hearing("Dev hearing two", givenBy=[mention("dev mention")], names=[suggestion])
    response = page.request.post(
        f"{dev_url}/api/users/session",
        form={"username": USERNAME, "password": PASSWORD},
    )
    assert response.ok, response.text()

    # the item's page: the chip, the review flag that counts the tasks, and the panel that lists the mention
    page.goto(f"{dev_url}/Hearing/{first}")
    hydrated(page)
    expect(page.get_by_test_id("unreconciled")).to_be_visible()
    page.get_by_test_id("review-button").click()
    expect(page.get_by_test_id("review-outstanding-mention")).to_have_count(1)
    page.get_by_test_id("review-outstanding-mention").click()
    expect(page.locator("main")).not_to_contain_text(SOLID_ERROR)
    assert errors == []
    page.keyboard.press("Escape")

    # the form: the mention's dialog, then the button that confirms
    page.get_by_role("link", name=re.compile("^Edit")).click()
    page.wait_for_url(re.compile(r"/edit$"))
    page.get_by_test_id("unreconciled-editor").get_by_test_id("reconcile-button").click()
    dialog = page.get_by_role("dialog", name="Reconcile")
    expect(dialog.get_by_test_id("reconcile-similar-row")).to_have_count(1)
    dialog.get_by_label("Find Witness, or + to make one").fill("Dev")
    page.get_by_role("option", name="Dev witness").click()
    expect(dialog.get_by_test_id("reconcile-chosen")).to_be_visible()
    expect(page.locator("main")).not_to_contain_text(SOLID_ERROR)
    assert errors == []
    dialog.get_by_role("button", name="Cancel").click()
    page.get_by_test_id("confirm-button").click()
    dialog = page.get_by_role("dialog", name="Confirm an identification")
    expect(dialog.get_by_test_id("confirm-similar-row")).to_have_count(1)
    expect(page.locator("main")).not_to_contain_text(SOLID_ERROR)
    assert errors == []
    dialog.get_by_role("button", name="Cancel").click()

    # the mention's editor, a new one added, and the button
    expect(page.get_by_test_id("unreconciled-editor")).to_have_count(1)
    expect(page.get_by_test_id("confirm-button")).to_be_visible()
    page.get_by_role("button", name="Add Unreconciled").first.click()
    expect(page.get_by_test_id("unreconciled-editor")).to_have_count(2)
    expect(page.locator("main")).not_to_contain_text(SOLID_ERROR)
    assert errors == []

    # the pages of tasks, from tab to tab
    page.goto(f"{dev_url}/review")
    hydrated(page)
    # (the kinds of task are links in the console)
    tabs = page.get_by_role("banner", name="Console")
    expect(tabs.get_by_test_id("review-count-reconciliations")).to_have_text("2")
    tabs.get_by_role("link", name="Reconciliations").click()
    rows = page.get_by_test_id("reconciliations-row")
    expect(rows).to_have_count(2)
    rows.first.get_by_test_id("reconciliations-choose").click()
    dialog = page.get_by_role("dialog", name="Reconcile")
    expect(dialog.get_by_test_id("reconcile-panel")).to_be_visible()
    expect(page.locator("main")).not_to_contain_text(SOLID_ERROR)
    assert errors == []
    dialog.get_by_role("button", name="Cancel").click()
    tabs.get_by_role("link", name="Identifications").click()
    expect(page.get_by_test_id("identifications-row")).to_have_count(2)
    pick(page.get_by_role("combobox", name="Tasks of"), "me")
    expect(page.get_by_test_id("identifications-row")).to_have_count(0)
    expect(page.locator("main")).not_to_contain_text(SOLID_ERROR)
    assert errors == []
