"""Logging in and out through the dialog, and what needs a login"""

from conftest import PASSWORD, USERNAME
from helpers import expand_nav, hydrated
from playwright.sync_api import Page, expect


def open_dialog(page: Page):
    page.goto("/")
    expand_nav(page)
    page.get_by_role("button", name="Log in").click()
    dialog = page.get_by_role("dialog", name="Log in")
    expect(dialog).to_be_visible()
    return dialog


def test_logging_in_through_the_dialog(page: Page, types):
    dialog = open_dialog(page)
    dialog.get_by_label("Username").fill(USERNAME)
    dialog.get_by_label("Password").fill(PASSWORD)
    dialog.get_by_role("button", name="Log in").click()
    expect(dialog).to_have_count(0)
    expect(page.get_by_role("img", name=f"Logged in as {USERNAME}")).to_be_visible()
    # (the bar closed when the mouse left it for the dialog)
    expand_nav(page)
    expect(page.get_by_role("button", name=f"Log out {USERNAME}")).to_be_visible()
    # (the session is a cookie: it is there after a reload, from the server's first answer)
    page.reload()
    expect(page.get_by_role("img", name=f"Logged in as {USERNAME}")).to_be_visible()


def test_a_wrong_password_is_explained_and_the_dialog_stays(page: Page, types):
    dialog = open_dialog(page)
    dialog.get_by_label("Username").fill(USERNAME)
    dialog.get_by_label("Password").fill("not the password")
    dialog.get_by_role("button", name="Log in").click()
    expect(dialog.get_by_role("alert")).to_be_visible()
    expect(page.get_by_role("img", name="Not logged in")).to_be_visible()
    # (and the right one then works)
    dialog.get_by_label("Password").fill(PASSWORD)
    dialog.get_by_role("button", name="Log in").click()
    expect(dialog).to_have_count(0)
    expect(page.get_by_role("img", name=f"Logged in as {USERNAME}")).to_be_visible()


def test_the_dialog_can_be_given_up(page: Page, types):
    dialog = open_dialog(page)
    page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    open_dialog(page)
    page.get_by_role("dialog").get_by_role("button", name="Close").click()
    expect(page.get_by_role("dialog")).to_have_count(0)


def test_logging_out(logged_in: Page, types):
    page = logged_in
    page.goto("/")
    expand_nav(page)
    page.get_by_role("button", name=f"Log out {USERNAME}").click()
    expect(page.get_by_role("button", name="Log in")).to_be_visible()
    expect(page.get_by_role("img", name="Not logged in")).to_be_visible()
    page.reload()
    expect(page.get_by_role("img", name="Not logged in")).to_be_visible()


def test_a_page_that_needs_a_login_opens_the_dialog_and_giving_up_goes_home(
    page: Page, types
):
    page.goto("/Person/new")
    expect(page.get_by_role("dialog", name="Log in")).to_be_visible()
    page.keyboard.press("Escape")
    page.wait_for_url(lambda url: url.rstrip("/").endswith(page.url.split("/")[2]))
    expect(page.get_by_role("dialog")).to_have_count(0)


def test_a_page_that_needs_a_login_is_shown_once_logged_in(page: Page, types):
    page.goto("/Person/new")
    dialog = page.get_by_role("dialog", name="Log in")
    dialog.get_by_label("Username").fill(USERNAME)
    dialog.get_by_label("Password").fill(PASSWORD)
    dialog.get_by_role("button", name="Log in").click()
    expect(dialog).to_have_count(0)
    assert page.url.endswith("/Person/new")
    expect(page.get_by_role("banner", name="Console")).to_contain_text("New")


def test_a_new_button_is_for_someone_logged_in(page: Page, data):
    page.goto("/Person")
    hydrated(page)
    expect(page.get_by_role("link", name="Maximilian")).to_be_visible()
    expect(page.get_by_role("link", name="New Person")).to_have_count(0)
    page.request.post(
        "/api/users/session", form={"username": USERNAME, "password": PASSWORD}
    )
    page.reload()
    expect(page.get_by_role("link", name="New Person")).to_be_visible()
