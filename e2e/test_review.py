"""Review in the interface (the module of `pangloss_review`): the button in the console of a reviewed document, the panel
that slides out with the status and the comments, and what another user does reaching an open page without a reload (the
`live()` feed), comments about a part (`#`), and the queue page. The e2e project's `Report` is reviewed (with nested
`ReportSection`s); `Statement` is not. No one may check what they made (`REVIEW_ALLOW_SELF_REVIEW = False`): the reports
are made by `ann`."""

import re
import subprocess
from types import SimpleNamespace

import pytest
from conftest import (
    AUTHOR_PASSWORD,
    AUTHOR_USERNAME,
    OTHER_PASSWORD,
    OTHER_USERNAME,
    Stack,
    environment,
    forget,
)
from helpers import box, expand_nav, hydrated
from playwright.sync_api import Page, expect


SECTIONS = [
    {"type": "ReportSection", "label": "Income in the first half", "body": "Rose"},
    {"type": "ReportSection", "label": "Costs", "body": "Fell"},
]


FINDINGS = [
    {
        "type": "Finding",
        "label": "Overspend",
        "note": "Found in the audit",
        "target": [{"type": "ReportSection", "label": "Audit notes", "body": "Spent"}],
    }
]


def make_report(
    stack: Stack, label: str = "Annual report", sections=SECTIONS, findings=FINDINGS
) -> str:
    """A Report made by ann (so that the others may check it)"""
    author = stack.client(AUTHOR_USERNAME, AUTHOR_PASSWORD)
    made = author.ok(
        "POST",
        "/api/Report",
        {
            "label": label,
            "text": "Things happened",
            "sections": sections,
            "findings": findings,
        },
    )
    return made["id"]


@pytest.fixture
def report(types: Stack) -> SimpleNamespace:
    """A new Report (unchecked, no comments, two sections) made by ann; clients for the project's user (e2e, whose page
    the tests use) and for bob"""
    forget("Report", "ReportSection", "PGReviewComment")
    return SimpleNamespace(
        id=make_report(types),
        api=types.admin(),
        bob=types.client(OTHER_USERNAME, OTHER_PASSWORD),
        stack=types,
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
    box = panel(page).get_by_role("combobox", name="Comment")
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


def test_parts_are_referred_to_with_a_hash_and_shown_inline(logged_in: Page, report):
    page = logged_in
    sections = report.api.ok("GET", f"/api/Report/{report.id}")["sections"]
    income, costs = sections[0]["id"], sections[1]["id"]
    open_panel(page, report.id)
    box = panel(page).get_by_role("combobox", name="Comment")
    box.press_sequentially("The figure in #inco")
    parts = panel(page).get_by_role("listbox", name="Parts of the document")
    expect(parts.get_by_role("option")).to_have_count(1)
    expect(parts.get_by_role("option")).to_contain_text("Income in the first half")
    box.press("Enter")
    expect(parts).to_have_count(0)
    # (the reference is in the text, as #<id>; a second one too)
    expect(box).to_have_value(f"The figure in #{income} ")
    box.press_sequentially("does not match #cos")
    box.press("Enter")
    expect(box).to_have_value(f"The figure in #{income} does not match #{costs} ")
    panel(page).get_by_role("button", name="Send").click()
    mine = (
        panel(page).get_by_test_id("review-comment").filter(has_text="does not match")
    )
    expect(mine.get_by_role("button", name="Resolve")).to_be_visible()
    # (read, the references are chips in their places)
    chips = mine.get_by_test_id("review-ref")
    expect(chips).to_have_text(
        ["Report sectionIncome in the first half", "Report sectionCosts"]
    )
    expect(mine.locator("div.rounded-lg")).to_have_text(
        "The figure in Report sectionIncome in the first half does not match Report sectionCosts"
    )
    comment = report.api.ok("GET", f"/api/review/{report.id}")["comments"][0]
    assert comment["text"] == f"The figure in #{income} does not match #{costs}"
    # (the API keeps the first as the part it is about, with its label)
    assert (comment["targetId"], comment["targetLabel"]) == (
        income,
        "Income in the first half",
    )
    # (a chip shows its part on the page)
    section = page.locator(f'[data-item-id="{costs}"]')
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    chips.nth(1).click()
    expect(section).to_be_in_viewport()


def test_the_button_opens_the_list_and_escape_closes_only_it(logged_in: Page, report):
    page = logged_in
    open_panel(page, report.id)
    panel(page).get_by_role("button", name="Refer to a part…").click()
    parts = panel(page).get_by_role("listbox", name="Parts of the document")
    # (the two sections, the finding (a reified relation that is a document) and the section inside it)
    expect(parts.get_by_role("option")).to_have_text(
        [
            "Report sectionIncome in the first half",
            "Report sectionCosts",
            "FindingOverspend",
            "Report sectionAudit notes",
        ]
    )
    page.keyboard.press("Escape")
    expect(parts).to_have_count(0)
    expect(panel(page)).to_have_attribute("data-open", "true")
    parts_box = panel(page).get_by_role("combobox", name="Comment")
    expect(parts_box).to_have_value("#")


def test_a_comment_about_a_part_since_removed_says_so(logged_in: Page, report):
    page = logged_in
    section = report.api.ok("GET", f"/api/Report/{report.id}")["sections"][1]
    report.bob.ok(
        "POST",
        f"/api/review/{report.id}/comments",
        {"text": f"Cut #{section['id']}", "targetId": section["id"]},
    )
    # (ann takes the section out)
    author = report.stack.client(AUTHOR_USERNAME, AUTHOR_PASSWORD)
    edit = author.ok("GET", f"/api/Report/{report.id}/edit")
    status, result = author.send(
        "PUT",
        f"/api/Report/{report.id}",
        {**edit, "sections": edit["sections"][:1]},
        headers={"If-Match": "*"},
    )
    assert status < 300, result
    open_panel(page, report.id)
    target = panel(page).get_by_test_id("review-ref")
    expect(target).to_have_attribute("data-gone", "true")
    expect(target).to_have_text("Costs(no longer there)")


def test_checking_what_one_made_is_refused_and_said(logged_in: Page, types):
    """With REVIEW_ALLOW_SELF_REVIEW false, the change is undone and the API's reason shown in a red toast"""
    forget("Report", "ReportSection", "PGReviewComment")
    page = logged_in
    mine = types.admin().ok(
        "POST",
        "/api/Report",
        {"label": "My report", "text": "Mine", "sections": [], "findings": []},
    )["id"]
    open_panel(page, mine)
    with page.expect_response(lambda r: r.url.endswith("/status")) as answer:
        panel(page).get_by_role("button", name="Checked", exact=True).click()
    assert answer.value.status == 403
    expect(page.get_by_role("status", name="Notifications")).to_contain_text(
        "The status was not changed: e2e created or last edited this document, and cannot check it"
    )
    expect(review_button(page)).to_have_attribute("aria-label", "Review: Unchecked")
    assert types.admin().ok("GET", f"/api/review/{mine}")["status"] == "unchecked"


def queue_rows(page: Page):
    return page.get_by_test_id("review-queue-row")


def test_the_queue_lists_what_is_to_be_checked_by_status(logged_in: Page, report):
    page = logged_in
    checked = make_report(report.stack, "Checked report", [], [])
    report.bob.ok("POST", f"/api/review/{checked}/status", {"status": "checked"})
    report.bob.ok("POST", f"/api/review/{report.id}/comments", {"text": "One thing"})
    page.goto("/")
    hydrated(page)
    expand_nav(page)
    page.get_by_role("navigation", name="Main").get_by_role(
        "link", name="Review"
    ).click()
    expect(page.get_by_role("heading", name="Documents to review")).to_be_visible()
    tabs = page.get_by_role("tablist", name="Status")
    expect(tabs.get_by_role("tab", name="Unchecked", exact=True)).to_have_attribute(
        "aria-selected", "true"
    )
    expect(queue_rows(page)).to_have_count(1)
    row = queue_rows(page).first
    expect(row).to_contain_text("Annual report")
    expect(row).to_contain_text("ann")
    expect(row).to_contain_text("1")
    tabs.get_by_role("tab", name="Checked", exact=True).click()
    expect(page).to_have_url(re.compile(r"status=checked"))
    expect(queue_rows(page)).to_have_count(1)
    expect(queue_rows(page).first).to_contain_text("Checked report")
    expect(queue_rows(page).first).to_contain_text("bob")
    # (the type filter offers the classes that are reviewed)
    select = page.get_by_role("combobox", name="Type")
    expect(select.locator("option")).to_have_text(["All types", "Report"])
    select.select_option("Report")
    expect(page).to_have_url(re.compile(r"type=Report"))
    expect(queue_rows(page)).to_have_count(1)
    # (back: the unchecked list again; and a row leads to its document)
    page.go_back()
    page.go_back()
    expect(queue_rows(page).first).to_contain_text("Annual report")
    queue_rows(page).first.get_by_role("link").click()
    expect(page.get_by_role("heading", name="Annual report")).to_be_visible()


def test_the_queue_goes_a_page_at_a_time(logged_in: Page, report):
    page = logged_in
    author = report.stack.client(AUTHOR_USERNAME, AUTHOR_PASSWORD)
    for n in range(25):
        author.ok(
            "POST",
            "/api/Report",
            {"label": f"Report {n:02}", "text": "x", "sections": [], "findings": []},
        )
    page.goto("/review")
    hydrated(page)
    expect(page.get_by_test_id("review-queue-count")).to_have_text("Documents: 26")
    expect(queue_rows(page)).to_have_count(25)
    pages = page.get_by_role("navigation", name="Pages")
    expect(pages).to_contain_text("Page 1 of 2")
    pages.get_by_role("button", name="Next").click()
    expect(page).to_have_url(re.compile(r"page=2"))
    expect(queue_rows(page)).to_have_count(1)
    expect(pages.get_by_role("button", name="Next")).to_be_disabled()


def test_the_queue_needs_a_login(page: Page, types):
    page.goto("/review")
    hydrated(page)
    expect(page.get_by_role("dialog", name="Log in")).to_be_visible()
    expect(page.get_by_role("heading", name="Documents to review")).to_have_count(0)


def test_a_reified_relation_document_can_be_referred_to(logged_in: Page, report):
    page = logged_in
    finding = report.api.ok("GET", f"/api/Report/{report.id}")["findings"][0]["id"]
    open_panel(page, report.id)
    box = panel(page).get_by_role("combobox", name="Comment")
    box.press_sequentially("Is #oversp")
    expect(
        panel(page)
        .get_by_role("listbox", name="Parts of the document")
        .get_by_role("option")
    ).to_have_text(["FindingOverspend"])
    box.press("Enter")
    expect(box).to_have_value(f"Is #{finding} ")
    box.press_sequentially("right?")
    panel(page).get_by_role("button", name="Send").click()
    mine = panel(page).get_by_test_id("review-comment").filter(has_text="right?")
    expect(mine.get_by_test_id("review-ref")).to_have_text("FindingOverspend")
    expect(mine.get_by_role("button", name="Resolve")).to_be_visible()
    comment = report.api.ok("GET", f"/api/review/{report.id}")["comments"][0]
    assert (comment["targetId"], comment["targetLabel"]) == (finding, "Overspend")
    # (its block on the page is marked, so the chip can show it)
    expect(page.locator(f'[data-item-id="{finding}"]')).to_contain_text("Overspend")


def list_flags(page: Page):
    return page.get_by_test_id("list-review-status")


def test_the_list_flags_the_status_of_what_is_reviewed(logged_in: Page, report):
    page = logged_in
    checked = make_report(report.stack, "Checked report", [], [])
    report.bob.ok("POST", f"/api/review/{checked}/status", {"status": "checked"})
    page.goto("/Report")
    hydrated(page)
    expect(list_flags(page)).to_have_count(2)
    row = page.get_by_role("listitem").filter(has_text="Checked report")
    expect(row.get_by_test_id("list-review-status")).to_have_attribute(
        "data-status", "checked"
    )
    row = page.get_by_role("listitem").filter(has_text="Annual report")
    flag = row.get_by_test_id("list-review-status")
    expect(flag).to_have_attribute("data-status", "unchecked")
    expect(flag).to_have_attribute("title", "Unchecked")
    # (on the right: after the label)
    label = row.get_by_text("Annual report")
    assert box(flag)["x"] > box(label)["x"]


def test_what_is_inside_a_reviewed_document_has_the_flag_then_the_link_to_it(
    logged_in: Page, report
):
    page = logged_in
    page.goto("/ReportSection")
    hydrated(page)
    row = page.get_by_role("listitem").filter(has_text="Costs")
    flag = row.get_by_test_id("list-review-status")
    expect(flag).to_have_attribute("data-status", "unchecked")
    head = row.get_by_role("link", name="Go to the Report")
    expect(head).to_have_attribute("href", f"/Report/{report.id}")
    assert box(head)["x"] > box(flag)["x"]
    assert (
        box(head)["x"]
        > box(row.get_by_role("link", name="Costs"))["x"]
    )


def test_the_list_flags_nothing_not_reviewed_or_for_a_reader_logged_out(
    logged_in: Page, report
):
    report.bob.ok("POST", f"/api/review/{report.id}/status", {"status": "checked"})
    report.api.ok("POST", "/api/Person", {"label": "Someone unreviewed", "hasRole": []})
    logged_in.goto("/Person")
    hydrated(logged_in)
    expect(logged_in.get_by_text("Someone unreviewed")).to_be_visible()
    expect(list_flags(logged_in)).to_have_count(0)
    logged_in.context.clear_cookies()
    logged_in.goto("/Report")
    hydrated(logged_in)
    expect(logged_in.get_by_text("Annual report")).to_be_visible()
    expect(list_flags(logged_in)).to_have_count(0)
