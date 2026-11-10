"""The pages of users (the module of `pangloss_users`): the link in the navigation bar, the list of users, a user's
page with what they made or changed, and the link to it from a name in the console."""

import re
import subprocess

from conftest import AUTHOR_PASSWORD, AUTHOR_USERNAME, USERNAME, environment, forget
from helpers import expand_nav, hydrated
from playwright.sync_api import Page, expect


def test_the_users_pages(logged_in: Page, data):
    page = logged_in
    page.goto("/")
    expand_nav(page)
    page.get_by_role("link", name="Users", exact=True).click()
    expect(page).to_have_url(re.compile(r"/users$"))
    page.get_by_test_id("users-row").get_by_role("link", name=USERNAME, exact=True).click()
    expect(page).to_have_url(re.compile(rf"/users/{USERNAME}$"))

    rows = page.get_by_test_id("user-item")
    expect(rows.first).to_contain_text("Created")
    # (an item is a chip that links to it)
    expect(rows.first.get_by_role("link")).to_have_attribute("href", re.compile(r"^/\w+/"))


def test_the_nav_link_and_pages_are_for_someone_logged_in(page: Page, data):
    page.goto("/")
    expand_nav(page)
    expect(page.get_by_role("link", name="Users", exact=True)).to_have_count(0)
    page.goto(f"/users/{USERNAME}")
    hydrated(page)
    expect(page.get_by_test_id("user-item")).to_have_count(0)


def test_a_users_items_are_read_a_page_at_a_time_the_latest_first(logged_in: Page, data, types):
    # (ann makes 27 groups, and then changes the first: more than one page of 25, and the change is the latest)
    ann = types.client(AUTHOR_USERNAME, AUTHOR_PASSWORD)
    try:
        ids = [ann.ok("POST", "/api/Group", {"label": f"Guild {n + 1:02}"})["id"] for n in range(27)]
        edit = ann.ok("GET", f"/api/Group/{ids[0]}/edit")
        status, result = ann.send(
            "PUT", f"/api/Group/{ids[0]}", {**edit, "label": "Guild renamed"}, headers={"If-Match": "*"}
        )
        assert status < 300, result

        page = logged_in
        page.goto(f"/users/{AUTHOR_USERNAME}")
        hydrated(page)
        rows = page.get_by_test_id("user-item")
        expect(rows).to_have_count(25)
        # (what was changed last is first, and says it was changed; it is a chip of its type, to its page)
        expect(rows.first).to_contain_text("Guild renamed")
        expect(rows.first).to_contain_text("Modified")
        expect(rows.first.get_by_role("link")).to_have_attribute("href", f"/Group/{ids[0]}")
        expect(rows.nth(1)).to_contain_text("Guild 27")
        expect(rows.nth(1)).to_contain_text("Created")

        pager = page.get_by_role("navigation", name="Pages")
        expect(pager).to_contain_text(re.compile(r"Page 1 of \d+"))
        expect(pager.get_by_role("button", name="Previous")).to_be_disabled()
        pager.get_by_role("button", name="Next").click()
        # (the page is in the address, so it can be linked to and gone back from)
        expect(page).to_have_url(re.compile(rf"/users/{AUTHOR_USERNAME}\?page=2$"))
        expect(pager).to_contain_text(re.compile(r"Page 2 of \d+"))
        expect(rows.first).to_be_visible()
        expect(rows.filter(has_text="Guild renamed")).to_have_count(0)
        page.go_back()
        expect(page).to_have_url(re.compile(rf"/users/{AUTHOR_USERNAME}$"))
        expect(rows.first).to_contain_text("Guild renamed")

        # (the address alone gives the page)
        page.goto(f"/users/{AUTHOR_USERNAME}?page=2")
        hydrated(page)
        expect(pager).to_contain_text(re.compile(r"Page 2 of \d+"))
    finally:
        forget("Group")


def test_a_user_with_a_full_name_and_nothing_made_and_a_user_there_is_not(logged_in: Page, data, types):
    if "carol" not in types.run("users", "list"):
        types.run(
            "users", "create", "--username", "carol", "--email", "carol@example.com", "--password", "carol-password",
            "--full-name", "Carol Example", "--no-admin",
        )  # fmt: skip
    page = logged_in
    page.goto("/users")
    hydrated(page)
    row = page.get_by_test_id("users-row").filter(has_text="carol")
    expect(row).to_contain_text("Carol Example")
    row.get_by_role("link").click()
    expect(page).to_have_url(re.compile(r"/users/carol$"))
    expect(page.get_by_role("heading", level=1)).to_contain_text("carol")
    expect(page.get_by_role("heading", level=1)).to_contain_text("Carol Example")
    expect(page.get_by_text("Nothing made or changed yet")).to_be_visible()
    expect(page.get_by_test_id("user-item")).to_have_count(0)
    expect(page.get_by_role("navigation", name="Pages")).to_have_count(0)

    page.goto("/users/nobody-at-all")
    hydrated(page)
    expect(page.get_by_role("alert")).to_contain_text("There is no user 'nobody-at-all'")
    expect(page.get_by_test_id("user-item")).to_have_count(0)


def test_the_users_pages_ask_for_a_login_and_giving_up_goes_home(page: Page, data):
    for address in ("/users", f"/users/{USERNAME}"):
        page.goto(address)
        hydrated(page)
        expect(page.get_by_role("dialog")).to_be_visible()
        expect(page.get_by_test_id("users-row")).to_have_count(0)
        page.keyboard.press("Escape")
        expect(page).to_have_url(re.compile(r"/$"))


def test_the_console_names_link_to_the_user(logged_in: Page, data):
    page = logged_in
    page.goto(f"/Statement/{data.statement}")
    hydrated(page)
    page.get_by_test_id("console-meta").get_by_role("link", name=USERNAME).first.click()
    expect(page).to_have_url(re.compile(rf"/users/{USERNAME}$"))


def test_the_console_names_are_not_links_logged_out(page: Page, data):
    page.goto(f"/Statement/{data.statement}")
    hydrated(page)
    meta = page.get_by_test_id("console-meta")
    expect(meta).to_contain_text(USERNAME)
    expect(meta.get_by_role("link")).to_have_count(0)


def test_the_module_tests_pass_in_the_built_project(stack):
    """The users module's own vitest tests and type-check, run where a project builds it (a module has no
    node_modules of its own)"""
    interface = stack.project / ".pangloss" / "interface"
    for command in (
        ["npx", "vitest", "run", "--root", "modules/pangloss_users"],
        ["npx", "tsc", "--noEmit", "-p", "modules/pangloss_users/tsconfig.json"],
    ):
        done = subprocess.run(
            command, cwd=interface, env=environment(), capture_output=True, text=True, timeout=300, check=False
        )
        assert done.returncode == 0, (done.stdout + done.stderr)[-3000:]
