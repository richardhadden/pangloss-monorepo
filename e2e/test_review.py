"""Review in the interface (the module of `pangloss_review`): the button in the console of a reviewed document, the panel
that slides out with the status and the comments, and what another user does reaching an open page without a reload (the
`live()` feed). The e2e project's `Report` is reviewed; `Statement` is not."""

import subprocess
from types import SimpleNamespace

import pytest
from conftest import (
    OTHER_PASSWORD,
    OTHER_USERNAME,
    Stack,
    environment,
    forget,
)
from helpers import hydrated
from playwright.sync_api import Page, expect


@pytest.fixture
def report(types: Stack) -> SimpleNamespace:
    """A new Report (unchecked, no comments), made by the project's user; and a client for another user, bob"""
    forget("Report", "PGReviewComment")
    api = types.admin()
    made = api.ok(
        "POST", "/api/Report", {"label": "Annual report", "text": "Things happened"}
    )
    return SimpleNamespace(
        id=made["id"], api=api, bob=types.client(OTHER_USERNAME, OTHER_PASSWORD)
    )


def review_button(page: Page):
    return page.get_by_role("banner", name="Console").get_by_role(
        "button", name="Review: ", exact=False
    )


def panel(page: Page):
    return page.get_by_role("complementary", name="Review")


def open_panel(page: Page, item: str) -> None:
    page.goto(f"/Report/{item}")
    hydrated(page)
    review_button(page).click()
    expect(panel(page)).to_have_attribute("data-open", "true")


def test_a_reviewed_document_has_a_review_button_with_its_status(
    logged_in: Page, report
):
    page = logged_in
    page.goto(f"/Report/{report.id}")
    hydrated(page)
    button = review_button(page)
    expect(button).to_have_attribute("aria-label", "Review: Unchecked")
    expect(button.locator('[data-testid="review-button"]')).to_have_attribute(
        "data-status", "unchecked"
    )
    expect(button).to_have_attribute("aria-pressed", "false")
    # (the panel is there, off to the right, until the button opens it)
    expect(panel(page)).to_have_count(
        0
    )  # (hidden from the accessibility tree while closed)
    button.click()
    expect(button).to_have_attribute("aria-pressed", "true")
    expect(panel(page)).to_have_attribute("data-open", "true")
    expect(panel(page)).to_be_in_viewport()
    page.keyboard.press("Escape")
    expect(button).to_have_attribute("aria-pressed", "false")


def test_a_document_that_is_not_reviewed_has_none(logged_in: Page, data):
    page = logged_in
    page.goto(f"/Statement/{data.statement}")
    hydrated(page)
    expect(page.get_by_role("banner", name="Console")).to_contain_text("Court at Ghent")
    # (long enough for the feed to have answered)
    page.wait_for_timeout(1000)
    expect(review_button(page)).to_have_count(0)


def test_changing_the_status_publishes_it_and_goes_to_the_api(logged_in: Page, report):
    page = logged_in
    open_panel(page, report.id)
    status = panel(page).get_by_role("group", name="Status")
    expect(
        status.get_by_role("button", name="Unchecked", exact=True)
    ).to_have_attribute("aria-pressed", "true")
    status.get_by_role("button", name="Checked", exact=True).click()
    expect(status.get_by_role("button", name="Checked", exact=True)).to_have_attribute(
        "aria-pressed", "true"
    )
    expect(review_button(page)).to_have_attribute("aria-label", "Review: Checked")
    expect(panel(page).get_by_test_id("review-reviewed-by")).to_contain_text(
        "Reviewed by e2e"
    )
    state = report.api.ok("GET", f"/api/review/{report.id}")
    assert (state["status"], state["published"]) == ("checked", True)
    # (shown at once, before the API has answered: the check of the API waits for the answer)
    with page.expect_response(lambda r: r.url.endswith("/status")):
        status.get_by_role("button", name="Errors found", exact=True).click()
    expect(review_button(page)).to_have_attribute("aria-label", "Review: Errors found")
    expect(
        review_button(page).locator('[data-testid="review-button"]')
    ).to_have_attribute("data-status", "errors_found")
    assert report.api.ok("GET", f"/api/review/{report.id}")["status"] == "errors_found"


def test_a_comment_is_mine_on_the_right_and_counted(logged_in: Page, report):
    page = logged_in
    open_panel(page, report.id)
    box = panel(page).get_by_role("textbox", name="Comment")
    box.fill("The date in the second paragraph is wrong")
    panel(page).get_by_role("button", name="Send").click()
    expect(box).to_have_value("")
    mine = (
        panel(page).get_by_test_id("review-comment").filter(has_text="second paragraph")
    )
    expect(mine).to_have_attribute("data-mine", "true")
    expect(mine).to_contain_text("You")
    # (confirmed by the feed: no longer "Sending…", and it can be resolved)
    expect(mine.get_by_role("button", name="Resolve")).to_be_visible()
    expect(review_button(page)).to_have_attribute(
        "aria-label", "Review: Unchecked, open comments: 1"
    )
    expect(page.get_by_test_id("review-count")).to_have_text("1")
    comments = report.api.ok("GET", f"/api/review/{report.id}")["comments"]
    assert [(c["username"], c["text"]) for c in comments] == [
        ("e2e", "The date in the second paragraph is wrong")
    ]


def test_what_someone_else_does_reaches_the_open_page_without_a_reload(
    logged_in: Page, report
):
    page = logged_in
    open_panel(page, report.id)
    expect(panel(page)).to_contain_text("No comments")
    navigations = []
    page.on("framenavigated", lambda frame: navigations.append(frame.url))
    report.bob.ok(
        "POST", f"/api/review/{report.id}/comments", {"text": "Who wrote this?"}
    )
    theirs = (
        panel(page).get_by_test_id("review-comment").filter(has_text="Who wrote this?")
    )
    expect(theirs).to_be_visible(timeout=10_000)
    expect(theirs).to_have_attribute("data-mine", "false")
    expect(theirs).to_contain_text("bob")
    expect(page.get_by_test_id("review-count")).to_have_text("1")
    report.bob.ok("POST", f"/api/review/{report.id}/status", {"status": "checked"})
    expect(review_button(page)).to_have_attribute(
        "aria-label", "Review: Checked, open comments: 1", timeout=10_000
    )
    expect(
        panel(page)
        .get_by_role("group", name="Status")
        .get_by_role("button", name="Checked", exact=True)
    ).to_have_attribute("aria-pressed", "true")
    assert navigations == []


def test_a_comment_is_resolved_and_shown_again_on_asking(logged_in: Page, report):
    page = logged_in
    report.bob.ok(
        "POST", f"/api/review/{report.id}/comments", {"text": "Check the names"}
    )
    open_panel(page, report.id)
    theirs = (
        panel(page).get_by_test_id("review-comment").filter(has_text="Check the names")
    )
    theirs.get_by_role("button", name="Resolve").click()
    expect(theirs).to_have_count(0)
    expect(page.get_by_test_id("review-count")).to_have_count(0)
    panel(page).get_by_role("checkbox", name="Show resolved (1)").check()
    expect(theirs).to_contain_text("Resolved by e2e")
    comment = report.api.ok("GET", f"/api/review/{report.id}?resolved=true")[
        "comments"
    ][0]
    assert (comment["resolved"], comment["resolvedBy"]) == (True, "e2e")


def test_the_edit_page_has_it_too_apart_from_saving(logged_in: Page, report):
    page = logged_in
    page.goto(f"/Report/{report.id}/edit")
    hydrated(page)
    review_button(page).click()
    with page.expect_response(lambda r: r.url.endswith("/status")):
        panel(page).get_by_role("group", name="Status").get_by_role(
            "button", name="Errors found", exact=True
        ).click()
    expect(review_button(page)).to_have_attribute("aria-label", "Review: Errors found")
    # (the form is untouched, and still on the page: the change was not a save)
    expect(page).to_have_url(f"{page.url.split('/Report/')[0]}/Report/{report.id}/edit")
    expect(page.get_by_role("textbox", name="Text")).to_have_value("Things happened")
    assert report.api.ok("GET", f"/api/review/{report.id}")["status"] == "errors_found"


def test_the_module_tests_pass_in_the_built_project(stack: Stack):
    """The review module's own vitest tests and type-check, run where a project builds it (a module has no
    node_modules of its own)"""
    interface = stack.project / ".pangloss" / "interface"
    for command in (
        ["npx", "vitest", "run", "--root", "modules/pangloss_review"],
        ["npx", "tsc", "--noEmit", "-p", "modules/pangloss_review/tsconfig.json"],
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
