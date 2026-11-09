"""The pages of users (the module of `pangloss_users`): the link in the navigation bar, the list of users, a user's
page with what they made or changed, and the link to it from a name in the console."""

import re
import subprocess

from conftest import USERNAME, environment
from helpers import expand_nav, hydrated
from playwright.sync_api import Page, expect


def test_the_users_pages(logged_in: Page, data):
    page = logged_in
    page.goto("/")
    expand_nav(page)
    page.get_by_role("link", name="Users", exact=True).click()
    expect(page).to_have_url(re.compile(r"/users$"))
    page.get_by_test_id("users-row").filter(has_text=USERNAME).get_by_role("link").click()
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
