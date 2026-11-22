"""The candidates of a mention in review's reconcile dialog (the module of `pangloss_reconcile`, in review's place
`reconcileCandidates`): above the picker, "Suggested" lists the entities the mention may be, best first, each a chip
with a bar of its score, Choose, and under it whom it is also named with. The e2e project's profile `who` weighs the
name and the graph (`RECONCILE_PROFILE`); the worker of the vectors keeps the entities' vectors current, so each test
waits for it by asking the route until the answer is as it should be."""

import re
from types import SimpleNamespace

import pytest
from conftest import AUTHOR_PASSWORD, AUTHOR_USERNAME, OTHER_PASSWORD, OTHER_USERNAME, Stack, forget
from helpers import hydrated, until_candidates
from playwright.sync_api import Page, expect

# (the least score the module shows: `LEAST_SCORE` in its `candidates.ts`)
LEAST_SCORE = 0.3


def mention(label: str) -> dict:
    return {"type": "Unreconciled", "unreconciledType": "Witness", "label": label}


def witness_ref(id_: str) -> dict:
    return {"type": "Witness", "id": id_}


@pytest.fixture
def court(types: Stack) -> SimpleNamespace:
    """Nothing of the hearings of an earlier test; the admin (whose page the tests use) and ann, who makes hearings"""
    forget("Hearing", "Testimony", "Unreconciled", "Witness", "IdentificationByToolchain", "PGUriClaim")
    admin = types.admin()
    ann = types.client(AUTHOR_USERNAME, AUTHOR_PASSWORD)

    def hearing(label: str, given_by: list[dict]) -> dict:
        return ann.ok(
            "POST",
            "/api/Hearing?detail=true",
            {
                "label": label,
                "testimonies": [
                    {"type": "Testimony", "label": f"{label}: testimony", "givenBy": given_by, "names": []}
                ],
            },
        )

    return SimpleNamespace(
        admin=admin,
        bob=types.client(OTHER_USERNAME, OTHER_PASSWORD),
        hearing=hearing,
        witness=lambda label: admin.ok("POST", "/api/Witness", {"label": label})["id"],
    )


def reconcile_dialog(page: Page, hearing_id: str, label: str):
    """The form of the hearing, and the reconcile dialog of its mention `label`, opened as `test_reconcile.py` opens it"""
    page.goto(f"/Hearing/{hearing_id}/edit")
    hydrated(page)
    page.get_by_test_id("unreconciled-editor").get_by_role("button", name=f"Reconcile {label}").click()
    return page.get_by_role("dialog", name="Reconcile")


def test_the_namesake_who_keeps_that_company_is_suggested_first_and_chosen(logged_in: Page, court):
    page = logged_in
    # two witnesses of one name, one of them heard before with a third witness (in a published hearing, which the
    # graph of similarity sees)
    elder = court.witness("John Fletcher")
    younger = court.witness("John Fletcher")
    alice = court.witness("Alice Marsh")
    earlier = court.hearing("Earlier hearing", [witness_ref(elder), witness_ref(alice)])
    court.bob.ok("POST", f"/api/review/{earlier['id']}/status", {"status": "published"})
    # a new hearing names a John Fletcher beside her
    made = court.hearing("New hearing", [mention("John Fletcher"), witness_ref(alice)])
    mention_id = made["testimonies"][0]["givenBy"][0]["id"]

    def ready(candidates: list[dict]) -> bool:
        return (
            len(candidates) >= 2
            and candidates[0]["id"] == elder
            and candidates[1]["id"] == younger
            and candidates[0]["score"] > candidates[1]["score"]
            and [shared["id"] for shared in candidates[0]["shared"]] == [alice]
        )

    candidates = until_candidates(court.admin, mention_id, ready)
    # (she is a candidate as well, by the graph alone, and is not put forward)
    assert all(each["score"] < LEAST_SCORE for each in candidates if each["id"] == alice), candidates

    dialog = reconcile_dialog(page, made["id"], "John Fletcher")
    suggested = dialog.get_by_test_id("reconcile-candidates")
    expect(suggested).to_contain_text("Suggested")
    rows = suggested.get_by_test_id("reconcile-candidate")
    expect(rows).to_have_count(2)
    first, second = rows.nth(0), rows.nth(1)
    # (best first: the one who keeps that company; each a chip that links to the witness, a bar and the figure)
    expect(first).to_have_attribute("data-id", elder)
    expect(second).to_have_attribute("data-id", younger)
    expect(first.locator("a").first).to_have_attribute("href", f"/Witness/{elder}")
    expect(first.locator("a").first).to_contain_text("John Fletcher")
    expect(first.get_by_role("meter")).to_have_attribute("aria-label", re.compile(r"^Score \d\.\d\d: (name|graph) "))
    # (the reason: the third witness, a chip; nothing under the other)
    reasons = first.get_by_test_id("reconcile-candidate-reasons")
    expect(reasons).to_contain_text("also named with")
    expect(reasons.locator("a")).to_have_attribute("href", f"/Witness/{alice}")
    expect(second.get_by_test_id("reconcile-candidate-reasons")).to_have_count(0)
    # (above the picker)
    picker = dialog.get_by_label("Find Witness, or + to make one")
    assert (suggested.bounding_box() or {})["y"] < (picker.bounding_box() or {})["y"]

    # Choose makes them the chosen entity; Reconcile puts them in the mention's place, saved with the form
    first.get_by_role("button", name="Choose John Fletcher").click()
    chosen = dialog.get_by_test_id("reconcile-chosen")
    expect(chosen.locator("a")).to_have_attribute("href", f"/Witness/{elder}")
    expect(suggested).to_have_count(0)
    dialog.get_by_test_id("reconcile-submit").click()
    expect(page.get_by_role("status", name="Notifications")).to_contain_text(
        "Reconciled with John Fletcher: it is saved with the document"
    )
    expect(page.get_by_test_id("unreconciled-editor")).to_have_count(0)
    page.get_by_role("banner", name="Console").get_by_role("button", name="Save", exact=True).click()
    page.wait_for_url(re.compile(rf"/Hearing/{made['id']}$"))
    saved = court.admin.ok("GET", f"/api/Hearing/{made['id']}")
    assert [each["id"] for each in saved["testimonies"][0]["givenBy"]] == [elder, alice]


def test_a_mention_like_nobody_shows_no_suggestions_and_the_picker_works(logged_in: Page, court):
    page = logged_in
    court.witness("John Fletcher")
    court.witness("Alice Marsh")
    made = court.hearing("Odd hearing", [mention("Zbigniew Quolp")])
    mention_id = made["testimonies"][0]["givenBy"][0]["id"]
    # (the route may give the nearest all the same: none is near enough to be put forward)
    candidates = until_candidates(court.admin, mention_id)
    assert all(each["score"] < LEAST_SCORE for each in candidates), candidates

    with page.expect_response(re.compile(rf"/api/reconcile/candidates/{mention_id}\?limit=5$")) as asked:
        dialog = reconcile_dialog(page, made["id"], "Zbigniew Quolp")
    assert asked.value.ok
    expect(dialog.get_by_test_id("reconcile-panel")).to_be_visible()
    expect(dialog.get_by_test_id("reconcile-candidates")).to_have_count(0)
    expect(dialog).not_to_contain_text("Suggested")
    dialog.get_by_label("Find Witness, or + to make one").fill("Alice")
    page.get_by_role("option", name="Alice Marsh").click()
    expect(dialog.get_by_test_id("reconcile-chosen")).to_contain_text("Alice Marsh")
    expect(dialog.get_by_test_id("reconcile-submit")).to_be_enabled()
