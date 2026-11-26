"""The "not" toggle of a form (`Affidavit` of the e2e project, conftest.py: `deponent: Person | Not[Person]`,
`claims: list[Claim | Not[Claim]]`, where `Not` is a space with `logical="not"`): an item offered both plainly and in
the "not" has a toggle that puts it in the space or takes it out, and the type menu has no "Not" section for it. What is
saved is what the menu would have made: `{"type": "Not", "contents": [item]}`, or the item alone."""

import re
from types import SimpleNamespace

import pytest
from conftest import forget
from helpers import hydrated
from playwright.sync_api import Page, expect


@pytest.fixture
def affidavit(data) -> SimpleNamespace:
    forget("Affidavit", "Not", "Claim")
    made = data.api.ok(
        "POST",
        "/api/Affidavit",
        {
            "label": "An affidavit",
            "deponent": {"type": "Person", "id": data.marie},
            "claims": [
                {"type": "Claim", "label": "The mill burnt", "text": "It burnt down"},
                {"type": "Claim", "label": "The bridge fell", "text": "It fell in"},
            ],
        },
    )["id"]
    return SimpleNamespace(id=made, api=data.api, marie=data.marie)


def row(page: Page, name: str):
    """The row of a field of the form, or of the page"""
    return page.locator("main dl > div").filter(has=page.locator("> dt", has_text=re.compile(f"^{name}", re.I))).first


def toggle(scope, of: str):
    """The "not" toggle in the bar of the block, or the chip, that says `of`"""
    return (
        scope.locator("[data-item-id], span.inline-flex", has_text=of)
        .locator("[data-not-toggle='Not']")
        .first
    )


def save(page: Page, made: str) -> None:
    with page.expect_response(
        lambda response: response.request.method == "PUT" and f"/api/Affidavit/{made}" in response.url
    ) as answer:
        page.get_by_role("button", name="Save", exact=True).click()
    assert answer.value.ok, answer.value.text()
    expect(page).to_have_url(re.compile(rf"/Affidavit/{made}$"))
    hydrated(page)


def test_a_claim_is_put_in_the_not_and_taken_out_by_its_toggle(logged_in: Page, affidavit):
    page = logged_in
    page.goto(f"/Affidavit/{affidavit.id}/edit")
    hydrated(page)
    claims = row(page, "Claims")
    mill = toggle(claims, "The mill burnt")
    expect(mill).to_have_attribute("aria-pressed", "false")
    expect(mill).to_have_text(re.compile("^Not$", re.I))
    # (the menu: one type left, so the button adds it at once; there is no "Not › Claim" to choose)
    adding = claims.get_by_role("button", name="Add Claims")
    expect(adding).not_to_have_attribute("aria-expanded", re.compile("."))
    expect(claims).not_to_contain_text("Not ›")

    # On and off again: nothing to save
    save_button = page.get_by_role("button", name="Save", exact=True)
    expect(save_button).to_be_disabled()
    mill.click()
    mill = toggle(claims, "The mill burnt")
    expect(mill).to_have_attribute("aria-pressed", "true")
    expect(claims.locator("[data-negated='Not']")).to_contain_text("The mill burnt")
    expect(save_button).to_be_enabled()
    mill.click()
    expect(toggle(claims, "The mill burnt")).to_have_attribute("aria-pressed", "false")
    expect(claims.locator("[data-negated]")).to_have_count(0)
    expect(save_button).to_be_disabled()

    # On, saved: inside a "not" in its place, as the menu would have made it
    toggle(claims, "The mill burnt").click()
    save(page, affidavit.id)
    saved = affidavit.api.ok("GET", f"/api/Affidavit/{affidavit.id}")["claims"]
    assert [item["type"] for item in saved] == ["Not", "Claim"], saved
    assert [(claim["label"], claim["text"]) for claim in saved[0]["contents"]] == [("The mill burnt", "It burnt down")]
    assert saved[1]["label"] == "The bridge fell"
    # (the page: in the space's band, with its head, as before)
    shown = row(page, "Claims")
    expect(shown).to_contain_text(re.compile("Not", re.I))
    expect(shown.get_by_role("link", name="Claim The mill burnt")).to_be_visible()

    # Edited again: drawn as the claim, pressed, and taken out
    page.goto(f"/Affidavit/{affidavit.id}/edit")
    hydrated(page)
    claims = row(page, "Claims")
    mill = toggle(claims, "The mill burnt")
    expect(mill).to_have_attribute("aria-pressed", "true")
    expect(claims.get_by_role("button", name="Remove Not")).to_have_count(0)
    claims.get_by_label("Text", exact=True).first.fill("It burnt to the ground")
    mill.click()
    expect(toggle(claims, "The mill burnt")).to_have_attribute("aria-pressed", "false")
    save(page, affidavit.id)
    saved = affidavit.api.ok("GET", f"/api/Affidavit/{affidavit.id}")["claims"]
    assert [(item["type"], item["label"], item["text"]) for item in saved] == [
        ("Claim", "The mill burnt", "It burnt to the ground"),
        ("Claim", "The bridge fell", "It fell in"),
    ], saved


def test_a_person_is_put_in_the_not_by_the_toggle_on_their_chip(logged_in: Page, affidavit):
    page = logged_in
    page.goto(f"/Affidavit/{affidavit.id}/edit")
    hydrated(page)
    deponent = row(page, "Deponent")
    marie = deponent.locator("[data-not-toggle='Not']")
    expect(marie).to_have_attribute("aria-pressed", "false")
    expect(marie).to_have_attribute("title", "Put Marie of Burgundy in Not")
    marie.click()
    expect(deponent.locator("[data-negated='Not']")).to_contain_text("Marie of Burgundy")
    expect(deponent.locator("[data-not-toggle='Not']")).to_have_attribute("aria-pressed", "true")
    save(page, affidavit.id)
    saved = affidavit.api.ok("GET", f"/api/Affidavit/{affidavit.id}")["deponent"]
    assert saved["type"] == "Not", saved
    assert [(person["type"], person["id"]) for person in saved["contents"]] == [("Person", affidavit.marie)]
    shown = row(page, "Deponent")
    expect(shown).to_contain_text(re.compile("Not", re.I))
    expect(shown.get_by_role("link", name=re.compile("Marie of Burgundy"))).to_be_visible()

    # And out again
    page.goto(f"/Affidavit/{affidavit.id}/edit")
    hydrated(page)
    deponent = row(page, "Deponent")
    marie = deponent.locator("[data-not-toggle='Not']")
    expect(marie).to_have_attribute("aria-pressed", "true")
    marie.click()
    expect(deponent.locator("[data-negated]")).to_have_count(0)
    save(page, affidavit.id)
    saved = affidavit.api.ok("GET", f"/api/Affidavit/{affidavit.id}")["deponent"]
    assert (saved["type"], saved["id"]) == ("Person", affidavit.marie), saved
