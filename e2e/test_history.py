"""History in the interface (the module of `pangloss_history`): the button in the console of an item, the panel of its
versions, a version sliding out beside it, "Restore to this point" with what it would undo, the page of every version
side by side, one panel on the right at a time (with review's), and an item from before history was installed, with
`pangloss history baseline`."""

import sqlite3
import subprocess
import time
from types import SimpleNamespace

import pytest
from conftest import AUTHOR_PASSWORD, AUTHOR_USERNAME, Stack, environment
from helpers import expand_nav, hydrated
from playwright.sync_api import Page, expect


def wait_for_versions(api, id: str, count: int, type: str = "Statement") -> dict:
    """The history of an item once it has `count` versions (they are recorded just after the write)"""
    deadline = time.monotonic() + 10
    while True:
        status, listing = api.send("GET", f"/api/{type}/{id}/history")
        if status == 200 and len(listing["versions"]) >= count:
            return listing
        assert time.monotonic() < deadline, (status, listing)
        time.sleep(0.1)


def update(api, id: str, **fields) -> None:
    edit = api.ok("GET", f"/api/Statement/{id}/edit")
    status, result = api.send(
        "PUT", f"/api/Statement/{id}", {**edit, **fields}, headers={"If-Match": "*"}
    )
    assert status < 300, result


@pytest.fixture
def statement(types: Stack) -> SimpleNamespace:
    """A statement with three versions: made about Marie at Ghent (v1), moved to Bruges (v2), about Mary instead and
    renamed (v3)"""
    api = types.admin()
    marie = api.ok("POST", "/api/Person", {"label": "Marie", "has_role": []})["id"]
    mary = api.ok("POST", "/api/Person", {"label": "Mary", "has_role": []})["id"]
    id = api.ok(
        "POST",
        "/api/Statement",
        {
            "label": "Court",
            "text": "Marie held court at Ghent",
            "about": {"type": "Person", "id": marie},
        },
    )["id"]
    update(api, id, text="Marie held court at Bruges")
    update(api, id, label="Court at Bruges", about={"type": "Person", "id": mary})
    wait_for_versions(api, id, 3)
    return SimpleNamespace(id=id, api=api, stack=types)


def history_button(page: Page):
    return page.get_by_role("button", name="History", exact=True)


def panel(page: Page):
    # (by its test id: while it is closed it is hidden from the accessibility tree)
    return page.get_by_test_id("history-panel")


def drawer(page: Page):
    return page.get_by_test_id("history-drawer")


def card(page: Page, version: int):
    return panel(page).locator(f'[data-testid="history-version"][data-version="{version}"]')


def open_history(page: Page, id: str, type: str = "Statement") -> None:
    page.goto(f"/{type}/{id}")
    hydrated(page)
    history_button(page).click()
    expect(panel(page)).to_have_attribute("data-open", "true")


def test_the_panel_lists_the_versions_and_one_slides_out_beside_it(logged_in: Page, statement):
    page = logged_in
    open_history(page, statement.id)
    cards = panel(page).get_by_test_id("history-version")
    expect(cards).to_have_count(3)
    expect(cards.nth(0)).to_have_attribute("data-version", "3")
    expect(card(page, 3).get_by_test_id("history-current")).to_be_visible()
    expect(card(page, 3).get_by_test_id("history-label")).to_have_text("Court at Bruges")
    expect(card(page, 3)).to_contain_text("Edited")
    expect(card(page, 1)).to_contain_text("Created")
    # (what changed in each, as tags)
    expect(card(page, 2).get_by_test_id("history-change")).to_have_text(["Text"])

    expect(drawer(page)).to_have_attribute("data-open", "false")
    card(page, 1).click()
    expect(drawer(page)).to_have_attribute("data-open", "true")
    expect(drawer(page)).to_contain_text("Marie held court at Ghent")
    expect(drawer(page).get_by_role("link", name="Marie")).to_be_visible()
    # (it comes out from under the panel, to its left)
    expect(drawer(page)).to_be_in_viewport()
    page.wait_for_function(
        "([d, p]) => Math.abs(d.getBoundingClientRect().right - p.getBoundingClientRect().left) < 2",
        arg=[drawer(page).element_handle(), panel(page).element_handle()],
    )

    # Escape puts the version back, then closes the panel
    page.keyboard.press("Escape")
    expect(drawer(page)).to_have_attribute("data-open", "false")
    page.keyboard.press("Escape")
    expect(panel(page)).to_have_attribute("data-open", "false")


def test_the_history_follows_the_language(logged_in: Page, statement):
    # (its words are in pangloss_history's own translations/ui.jsonc)
    page = logged_in
    page.goto(f"/Statement/{statement.id}")
    expand_nav(page)
    page.get_by_role("button", name="Deutsch").click()
    expect(page.locator("html")).to_have_attribute("lang", "de")
    page.mouse.move(600, 400)
    page.get_by_role("button", name="Verlauf", exact=True).click()
    expect(panel(page)).to_have_attribute("data-open", "true")
    expect(panel(page)).to_contain_text("Alle vergleichen")
    expect(card(page, 3)).to_contain_text("Bearbeitet")
    expect(card(page, 3).get_by_test_id("history-current")).to_have_text("Aktuell")
    expect(card(page, 1)).to_contain_text("Erstellt")
    card(page, 1).click()
    expect(drawer(page)).to_contain_text("Nichts wird gelöscht")
    expect(drawer(page).get_by_role("button", name="Bis hierhin wiederherstellen")).to_be_visible()


def test_restoring_asks_first_listing_what_is_undone_and_then_changes_the_item(logged_in: Page, statement):
    page = logged_in
    open_history(page, statement.id)
    card(page, 1).click()
    expect(page.get_by_test_id("history-restore")).to_be_enabled()
    page.get_by_test_id("history-restore").click()

    dialog = page.get_by_role("dialog", name="Restore version 1?")
    expect(dialog).to_be_visible()
    expect(dialog.get_by_test_id("history-undone")).to_have_count(2)
    expect(dialog.get_by_test_id("history-undone").nth(0)).to_contain_text("v3")
    trails = dialog.get_by_test_id("history-trail")
    expect(trails).to_have_text(["Label", "Text", "About", "About"])
    expect(dialog.get_by_test_id("history-change-row").nth(1).locator('[data-kind="added"]')).to_have_text("Ghent")
    expect(dialog).to_contain_text("Nothing is erased")

    # (cancelled, nothing happens)
    dialog.get_by_role("button", name="Cancel").click()
    expect(dialog).to_be_hidden()
    assert statement.api.ok("GET", f"/api/Statement/{statement.id}")["text"] == "Marie held court at Bruges"

    page.get_by_test_id("history-restore").click()
    page.get_by_test_id("history-restore-confirm").click()
    expect(page.get_by_text("Restored version 1 as version 4")).to_be_visible()
    # (the page reads the item again; the panel its versions)
    expect(page.locator("main")).to_contain_text("Marie held court at Ghent")
    expect(card(page, 4)).to_contain_text("Restored from version 1")
    expect(card(page, 4).get_by_test_id("history-current")).to_be_visible()
    assert statement.api.ok("GET", f"/api/Statement/{statement.id}")["text"] == "Marie held court at Ghent"


def test_a_restore_after_someone_else_changed_it_is_refused(logged_in: Page, statement):
    page = logged_in
    open_history(page, statement.id)
    card(page, 1).click()
    page.get_by_test_id("history-restore").click()
    # (someone saves meanwhile)
    update(statement.api, statement.id, text="Changed meanwhile")
    page.get_by_test_id("history-restore-confirm").click()
    expect(page.get_by_text("it was changed meanwhile")).to_be_visible()
    assert statement.api.ok("GET", f"/api/Statement/{statement.id}")["text"] == "Changed meanwhile"


def test_the_compare_page_shows_every_version_side_by_side(logged_in: Page, statement):
    page = logged_in
    open_history(page, statement.id)
    panel(page).get_by_test_id("history-compare").click()
    expect(page).to_have_url(f"{statement.stack.url}/Statement/{statement.id}/history")
    hydrated(page)
    columns = page.get_by_test_id("history-column")
    expect(columns).to_have_count(3)
    expect(columns.nth(2)).to_contain_text("Current")

    def cells(row: str):
        return page.locator(f'[data-testid="history-cell"][data-row="{row}"]')

    expect(cells(".text")).to_have_count(3)
    assert [cells(".text").nth(i).get_attribute("data-mark") for i in range(3)] == ["same", "changed", "same"]
    expect(cells(".text").nth(1).locator('[data-kind="removed"]')).to_have_text("Ghent")
    expect(cells(".text").nth(1).locator('[data-kind="added"]')).to_have_text("Bruges")
    # (the person referred to is a part matched by id: Marie taken out in v3, Mary put in, each on a row of its own)
    about = page.locator('[data-testid="history-cell"][data-row^=".about["]')
    expect(about).to_have_count(6)
    # (the rows line up: a cell is as tall as the others of its row)
    heights = {round(cells(".text").nth(i).bounding_box()["height"]) for i in range(3)}
    assert len(heights) == 1, heights
    # (it starts at the newest, scrolled to the right)
    box = page.get_by_test_id("history-compare-box")
    expect(box).to_be_visible()
    page.wait_for_function(
        "el => el.scrollLeft > 0 || el.scrollWidth <= el.clientWidth", arg=box.element_handle()
    )


def make_report(stack: Stack) -> str:
    author = stack.client(AUTHOR_USERNAME, AUTHOR_PASSWORD)
    return author.ok(
        "POST",
        "/api/Report",
        {"label": "A report", "text": "Things happened", "sections": [], "findings": []},
    )["id"]


def test_one_panel_on_the_right_at_a_time(logged_in: Page, types: Stack):
    page = logged_in
    id = make_report(types)
    wait_for_versions(types.admin(), id, 1, "Report")
    page.goto(f"/Report/{id}")
    hydrated(page)
    review = page.get_by_test_id("review-panel")
    page.get_by_test_id("review-button").click()
    expect(review).to_have_attribute("data-open", "true")
    history_button(page).click()
    expect(panel(page)).to_have_attribute("data-open", "true")
    expect(review).to_have_attribute("data-open", "false")
    page.get_by_test_id("review-button").click()
    expect(review).to_have_attribute("data-open", "true")
    expect(panel(page)).to_have_attribute("data-open", "false")


def test_an_item_from_before_history_has_none_until_a_baseline_is_recorded(logged_in: Page, types: Stack):
    page = logged_in
    api = types.admin()
    id = api.ok("POST", "/api/Person", {"label": "Old Person", "has_role": []})["id"]
    wait_for_versions(api, id, 1, "Person")
    # (as if it had been written before pangloss_history was installed)
    with sqlite3.connect(types.project / ".pangloss" / "history.sqlite3") as db:
        db.execute("DELETE FROM history WHERE head_id = ?", (id,))
    open_history(page, id, "Person")
    expect(panel(page).get_by_test_id("history-none")).to_contain_text("pangloss history baseline")

    output = types.run("history", "baseline", "--model", "Person")
    assert "1 recorded" in output, output

    history_button(page).click()
    history_button(page).click()
    expect(card(page, 1)).to_contain_text("Recorded as it was")
    expect(card(page, 1).get_by_test_id("history-current")).to_be_visible()


def test_the_module_tests_pass_in_the_built_project(stack: Stack):
    """The history module's own vitest tests and type-check, run where a project builds it (a module has no
    node_modules of its own)"""
    interface = stack.project / ".pangloss" / "interface"
    for command in (
        ["npx", "vitest", "run", "--root", "modules/pangloss_history"],
        ["npx", "tsc", "--noEmit", "-p", "modules/pangloss_history/tsconfig.json"],
    ):
        done = subprocess.run(
            command,
            cwd=interface,
            env=environment(),
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert done.returncode == 0, (done.stdout + done.stderr)[-3000:]
