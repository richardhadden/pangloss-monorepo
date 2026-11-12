"""Merging two entities that are one (the interface module of `pangloss_interface`; implementation_docs/entity-identity.md):
the button on an entity's page, the comparison, the merge and what it says it did, the address of the entity absorbed,
the undo; and, for someone who may not merge alone, the proposal that someone else verifies."""

import os
import re
from types import SimpleNamespace

import pytest
from conftest import (
    AUTHOR_PASSWORD,
    AUTHOR_USERNAME,
    OTHER_PASSWORD,
    OTHER_USERNAME,
    forget,
)
from helpers import expand_nav, hydrated
from playwright.sync_api import Page, expect


@pytest.fixture
def duplicates(data) -> SimpleNamespace:
    """Maximilian twice over ("Maximilian", with his secretary, and "Maximilian I", with an advisor), with a statement
    about the second and one about the first, and no merges from earlier tests"""
    forget("PGMerge", "PGMergeMove")
    api = data.api
    second = api.ok(
        "POST",
        "/api/Person",
        {
            "label": "Maximilian I",
            "has_role": [{"type": "Role", "id": data.advisor_role}],
        },
    )["id"]
    about_second = api.ok(
        "POST",
        "/api/Statement",
        {
            "label": "Crowned at Aachen",
            "text": "He was crowned",
            "about": {"type": "Person", "id": second},
        },
    )["id"]
    return SimpleNamespace(
        api=api,
        first=data.maximilian,
        second=second,
        about_second=about_second,
        stack=data,
    )


def shot(page: Page, name: str) -> None:
    """A picture of the page, when `PANGLOSS_SHOTS` names a directory for them (to look at what was built)"""
    if os.environ.get("PANGLOSS_SHOTS"):
        page.wait_for_timeout(300)
        page.screenshot(
            path=f"{os.environ['PANGLOSS_SHOTS']}/{name}.png", full_page=True
        )


def log_in(page: Page, username: str, password: str) -> None:
    response = page.request.post(
        "/api/users/session", form={"username": username, "password": password}
    )
    assert response.ok, response.text()


def test_an_admin_merges_two_people_and_undoes_it(logged_in: Page, duplicates):
    page = logged_in
    page.goto(f"/Person/{duplicates.first}")
    hydrated(page)
    # The button in the console opens a dialog that finds the other one
    page.get_by_role("button", name="Merge with…").click()
    dialog = page.get_by_test_id("merge-dialog")
    dialog.get_by_role("combobox").fill("Maximilian I")
    dialog.get_by_role("option", name=re.compile("Maximilian I")).click()
    expect(page).to_have_url(
        re.compile(rf"/Person/{duplicates.first}/merge/{duplicates.second}$")
    )

    # The two side by side: each a chip, a row for the roles (both of a list, to begin with), and what refers to each
    comparison = page.get_by_test_id("merge-comparison")
    expect(
        comparison.get_by_test_id("merge-survivor").get_by_role("link")
    ).to_have_attribute("href", f"/Person/{duplicates.first}")
    expect(comparison.get_by_test_id("merge-absorbed")).to_contain_text("Maximilian I")
    roles = comparison.locator("[data-testid='merge-row'][data-field='hasRole']")
    expect(roles).to_have_attribute("data-choice", "both")
    expect(roles.get_by_test_id("merge-result-value")).to_contain_text(
        "Maximilian's secretary"
    )
    expect(roles.get_by_test_id("merge-result-value")).to_contain_text(
        "Marie's advisor"
    )
    expect(
        comparison.get_by_test_id("merge-refer-absorbed").locator(
            "[data-type='Statement']"
        )
    ).to_contain_text("1")
    expect(comparison.get_by_test_id("merge-refer-survivor")).to_contain_text(
        "Nothing refers to it"
    )
    expect(comparison.get_by_test_id("merge-heads")).to_contain_text("will write")

    shot(page, "compare")
    # A choice changes what the survivor is to have; the label can be typed
    roles.get_by_role("button", name="Stays").click()
    expect(roles.get_by_test_id("merge-result-value")).not_to_contain_text(
        "Marie's advisor"
    )
    roles.get_by_role("button", name="Both").click()
    comparison.get_by_test_id("merge-label").fill("Maximilian I of Habsburg")

    # Merging asks first, naming both, and then says what it did
    comparison.get_by_test_id("merge-start").click()
    confirm = page.get_by_test_id("merge-confirm-dialog")
    expect(confirm).to_contain_text("Maximilian I")
    expect(confirm).to_contain_text("Maximilian I of Habsburg")
    shot(page, "confirm")
    confirm.get_by_test_id("merge-confirm").click()
    summary = page.get_by_test_id("merge-summary")
    expect(summary.get_by_test_id("merge-summary-counts")).to_contain_text(
        "1 references moved"
    )
    shot(page, "summary")

    # The statement about the one absorbed is about the survivor, which has the roles of both and the label typed
    page.goto(f"/Statement/{duplicates.about_second}")
    expect(
        page.locator("main").get_by_role(
            "link", name=re.compile("Maximilian I of Habsburg")
        )
    ).to_have_attribute("href", f"/Person/{duplicates.first}")
    # The address of the one absorbed shows the survivor, and says how the reader came there
    page.goto(f"/Person/{duplicates.second}")
    expect(page).to_have_url(
        re.compile(rf"/Person/{duplicates.first}\?merged={duplicates.second}$")
    )
    expect(page.get_by_role("heading", name="Maximilian I of Habsburg")).to_be_visible()
    expect(page.locator("main")).to_contain_text("Marie's advisor")
    notice = page.get_by_test_id("merge-notice-merged")
    expect(notice).to_contain_text("was merged into this")
    shot(page, "notice")
    # The list of people has one of them
    page.goto("/Person?q=Maximilian")
    expect(page.locator("main ul > li")).to_have_count(1)
    expect(page.locator("main ul > li")).to_contain_text("Maximilian I of Habsburg")

    # The page of the merge says what undoing it would do, and undoes it, asking first
    page.goto(f"/Person/{duplicates.first}?merged={duplicates.second}")
    page.get_by_test_id("merge-notice-merged").get_by_role("link").click()
    expect(page).to_have_url(re.compile(r"/merges/[0-9a-f-]+$"))
    hydrated(page)
    undo = page.get_by_test_id("merge-undo-screen")
    expect(undo.get_by_test_id("merge-age")).to_contain_text("made today")
    expect(undo.get_by_test_id("merge-undo-restored")).to_contain_text(
        "1 references go back"
    )
    shot(page, "undo")
    undo.get_by_test_id("merge-undo-start").click()
    page.get_by_test_id("merge-undo-dialog").get_by_test_id(
        "merge-undo-confirm"
    ).click()
    expect(page.get_by_test_id("merge-page")).to_have_attribute("data-state", "undone")
    expect(page.get_by_test_id("merge-undo-report")).to_contain_text(
        "1 references went back"
    )

    # The two are two again: the statement is about the second, which has its own page
    page.goto(f"/Statement/{duplicates.about_second}")
    expect(
        page.locator("main").get_by_role("link", name="Maximilian I", exact=False)
    ).to_have_attribute("href", f"/Person/{duplicates.second}")
    page.goto(f"/Person/{duplicates.second}")
    expect(page.get_by_role("heading", name="Maximilian I", exact=True)).to_be_visible()
    expect(page).to_have_url(re.compile(rf"/Person/{duplicates.second}$"))


def test_one_user_proposes_a_merge_and_another_verifies_it(page: Page, duplicates):
    # ann, who is no admin, may not merge alone: she proposes, with a note
    log_in(page, AUTHOR_USERNAME, AUTHOR_PASSWORD)
    page.goto(f"/Person/{duplicates.first}/merge/{duplicates.second}")
    hydrated(page)
    comparison = page.get_by_test_id("merge-comparison")
    expect(comparison.get_by_test_id("merge-start")).to_have_count(0)
    comparison.get_by_test_id("merge-note").fill("Same emperor, entered twice")
    comparison.get_by_test_id("merge-propose").click()
    expect(page).to_have_url(re.compile(r"/merges/[0-9a-f-]+$"))
    # (her own proposal: she cannot verify it, only withdraw it)
    expect(page.get_by_test_id("merge-own-proposal")).to_be_visible()
    expect(page.get_by_test_id("merge-start")).to_be_disabled()
    # Nothing has moved
    status, about = duplicates.api.send(
        "GET", f"/api/Statement/{duplicates.about_second}"
    )
    assert status == 200 and about["about"]["id"] == duplicates.second

    # bob sees the proposal on both entities' pages, and in the list of merges, which the navigation bar links to
    log_in(page, OTHER_USERNAME, OTHER_PASSWORD)
    page.goto(f"/Person/{duplicates.second}")
    notice = page.get_by_test_id("merge-notice-proposed")
    expect(notice).to_contain_text(f"{AUTHOR_USERNAME} proposed a merge with")
    expect(
        notice.get_by_role("link", name=re.compile("^Person Maximilian$|Maximilian$"))
    ).to_have_attribute("href", f"/Person/{duplicates.first}")
    expand_nav(page)
    page.get_by_role("link", name="Merges", exact=True).click()
    expect(page).to_have_url(re.compile(r"/merges$"))
    rows = page.get_by_test_id("merges-row")
    expect(rows).to_have_count(1)
    expect(rows.first.get_by_test_id("merge-state")).to_have_text("Proposed")
    shot(page, "merges")
    rows.first.get_by_test_id("merges-open").click()

    # The proposal is the comparison again, with her note; he verifies it, which carries it out
    expect(page.get_by_test_id("merge-proposal-note")).to_contain_text(
        "Same emperor, entered twice"
    )
    hydrated(page)
    shot(page, "proposal")
    page.get_by_test_id("merge-start").click()
    page.get_by_test_id("merge-confirm").click()
    expect(page.get_by_test_id("merge-summary")).to_be_visible()
    expect(page.get_by_test_id("merge-page")).to_have_attribute("data-state", "done")
    status, about = duplicates.api.send(
        "GET", f"/api/Statement/{duplicates.about_second}"
    )
    assert status == 200 and about["about"]["id"] == duplicates.first
    # Nothing waits any more; the merge is among those made
    page.goto("/merges")
    expect(page.get_by_test_id("merges-none")).to_be_visible()
    page.goto("/merges?show=done")
    expect(page.get_by_test_id("merges-row")).to_have_count(1)

    # bob may not undo alone either: he proposes it, and ann (someone else) leaves it merged
    page.get_by_test_id("merges-open").click()
    hydrated(page)
    expect(page.get_by_test_id("merge-undo-start")).to_have_count(0)
    page.get_by_test_id("merge-undo-note-box").fill("Two emperors after all?")
    page.get_by_test_id("merge-undo-propose").click()
    expect(page.get_by_test_id("merge-undo-own-proposal")).to_be_visible()
    merge_url = page.url
    log_in(page, AUTHOR_USERNAME, AUTHOR_PASSWORD)
    page.goto(f"/Person/{duplicates.first}")
    expect(page.get_by_test_id("merge-notice-undo-proposed")).to_contain_text(
        OTHER_USERNAME
    )
    page.goto(merge_url)
    hydrated(page)
    expect(page.get_by_test_id("merge-undo-note")).to_contain_text(
        "Two emperors after all?"
    )
    # (someone else proposed it, so she could undo it: she rejects that instead)
    expect(page.get_by_test_id("merge-undo-start")).to_be_enabled()
    page.get_by_test_id("merge-undo-reject").click()
    page.get_by_test_id("merge-undo-reject-reason").fill("One emperor")
    page.get_by_test_id("merge-undo-reject-confirm").click()
    expect(page.get_by_test_id("merge-undo-proposed")).to_have_count(0)
    expect(page.get_by_test_id("merge-page")).to_have_attribute("data-state", "done")


def test_a_proposal_is_rejected_with_a_reason(page: Page, duplicates):
    ann = duplicates.stack.api  # (the admin's client makes the proposal: bob, who is not the proposer, rejects it)
    proposal = ann.ok(
        "POST",
        f"/api/Person/{duplicates.first}/merge/propose",
        {"absorb": duplicates.second, "note": "Alike"},
    )
    log_in(page, OTHER_USERNAME, OTHER_PASSWORD)
    page.goto(f"/merges/{proposal['id']}")
    hydrated(page)
    page.get_by_test_id("merge-reject").click()
    page.get_by_test_id("merge-reject-reason").fill("Father and son")
    page.get_by_test_id("merge-reject-confirm").click()
    expect(page.get_by_test_id("merge-page")).to_have_attribute(
        "data-state", "rejected"
    )
    expect(page.get_by_test_id("merge-rejected-reason")).to_contain_text(
        "Father and son"
    )
    # (the two can be compared again from there)
    expect(page.get_by_test_id("merge-compare-again")).to_have_attribute(
        "href", f"/Person/{duplicates.first}/merge/{duplicates.second}"
    )
    page.goto(f"/Person/{duplicates.first}")
    hydrated(page)
    expect(page.get_by_test_id("merge-notices")).to_have_count(0)


def test_the_merge_pages_and_button_are_for_someone_logged_in(page: Page, duplicates):
    page.goto(f"/Person/{duplicates.first}")
    hydrated(page)
    expect(page.get_by_role("button", name="Merge with…")).to_have_count(0)
    expand_nav(page)
    expect(page.get_by_role("link", name="Merges", exact=True)).to_have_count(0)
    page.goto(f"/Person/{duplicates.first}/merge/{duplicates.second}")
    hydrated(page)
    expect(page.get_by_test_id("merge-comparison")).to_have_count(0)
    # (a document is not merged: its page has no button, logged in or not)
    log_in(page, OTHER_USERNAME, OTHER_PASSWORD)
    page.goto(f"/Statement/{duplicates.about_second}")
    hydrated(page)
    expect(page.get_by_role("button", name="History")).to_be_visible()
    expect(page.get_by_role("button", name="Merge with…")).to_have_count(0)


def test_an_admin_sees_the_merges_made_lately_on_the_admin_page(
    logged_in: Page, duplicates
):
    page = logged_in
    page.goto("/admin")
    section = page.get_by_test_id("admin-merges")
    expect(section.get_by_test_id("admin-merges-none")).to_be_visible()
    # (a merge made while the page is open appears on it: the section follows a feed)
    duplicates.api.ok(
        "POST", f"/api/Person/{duplicates.first}/merge", {"absorb": duplicates.second}
    )
    row = section.get_by_test_id("merges-row")
    expect(row).to_have_count(1)
    expect(row.get_by_test_id("merge-pair")).to_contain_text("Maximilian I")
    expect(row.get_by_test_id("merges-open")).to_have_attribute(
        "href", re.compile(r"^/merges/[0-9a-f-]+$")
    )
    # (and the check for references left on merged entities is one of the jobs)
    expect(page.get_by_test_id("admin-job-form-check_merged")).to_contain_text(
        "Check references to merged entities"
    )
