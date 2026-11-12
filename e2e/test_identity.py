"""What an entity is said to be the same as (the interface module of `pangloss_library`; implementation_docs/entity-identity.md,
part 2): a section above its contents, from the statements that have an `IdentityClaim()` relation."""

import os
import re
from types import SimpleNamespace

import pytest
from conftest import forget
from helpers import box, hydrated
from playwright.sync_api import Page, expect


@pytest.fixture
def claims(data) -> SimpleNamespace:
    """Maximilian is said to be the same as Charles in two ledgers (once with a reason) and, in one of them, said not
    to be; an alias (a document of its own) says he is the same as Marie; and a ledger denies that Marie is Charles"""
    forget("PGMerge", "PGMergeMove")
    api = data.api

    def person(id: str) -> dict:
        return {"type": "Person", "id": id}

    def same(label: str, one: str, other: str, **more) -> dict:
        return {"type": "SameEntity", "label": label, "target": [person(one), person(other)], **more}

    first = api.ok(
        "POST",
        "/api/Ledger",
        {
            "label": "Ledger of Ghent",
            "entries": [
                same("Max is Charles", data.maximilian, data.charles, argument="The same seal"),
                {"type": "Denied", "contents": [same("Max is not Charles", data.maximilian, data.charles)]},
            ],
        },
    )["id"]
    api.ok("POST", "/api/Ledger", {"label": "Ledger of Bruges", "entries": [same("Max is Charles again", data.charles, data.maximilian)]})
    api.ok(
        "POST",
        "/api/Ledger",
        {"label": "Ledger of Lille", "entries": [{"type": "Denied", "contents": [same("Marie is not Charles", data.marie, data.charles)]}]},
    )
    alias = api.ok("POST", "/api/Alias", {"label": "Max alias Marie", "entities": [person(data.maximilian), person(data.marie)]})["id"]
    return SimpleNamespace(**{**vars(data), "first": first, "alias": alias})


def other(section, id: str, spaces: str = ""):
    return section.locator(f"[data-testid='identity-context'][data-spaces='{spaces}'] [data-testid='identity-other'][data-id='{id}']")


def test_an_entity_page_lists_what_it_is_said_to_be_the_same_as(page: Page, claims):
    page.goto(f"/Person/{claims.maximilian}")
    section = page.get_by_test_id("identity-section")
    # Said plainly: Charles (by two statements held in ledgers) and Marie (by a document of its own)
    plain = section.locator("[data-testid='identity-context'][data-spaces='']")
    expect(plain).to_contain_text("Said to be the same as")
    charles = other(section, claims.charles)
    expect(charles.get_by_role("link", name=re.compile("Charles the Bold"))).to_have_attribute("href", f"/Person/{claims.charles}")
    expect(charles.get_by_test_id("identity-count")).to_contain_text("2")
    expect(other(section, claims.marie).get_by_test_id("identity-count")).to_contain_text("1")
    # In a semantic space, under its name: Charles again, who is marked in both places as said otherwise too
    denied = section.locator("[data-testid='identity-context'][data-spaces='Denied']")
    expect(denied).to_contain_text("Said to be the same as, in Denied")
    expect(other(section, claims.charles, "Denied").get_by_test_id("identity-count")).to_contain_text("1")
    expect(charles.get_by_test_id("identity-contested")).to_be_visible()
    expect(other(section, claims.marie).get_by_test_id("identity-contested")).to_have_count(0)
    # (the section is above the entity's own fields)
    assert box(section)["y"] < box(page.locator("main").get_by_text("has role", exact=False).first)["y"]
    if os.environ.get("PANGLOSS_SHOTS"):
        hydrated(page)
        charles.get_by_test_id("identity-count").click()
        page.screenshot(path=f"{os.environ['PANGLOSS_SHOTS']}/identity.png", full_page=True)
        charles.get_by_test_id("identity-count").click()

    # The statements are shown on demand: each a chip to its place in its document, with the reason given
    hydrated(page)
    charles.get_by_test_id("identity-count").click()
    statements = charles.get_by_test_id("identity-claims")
    expect(statements.get_by_role("listitem")).to_have_count(2)
    expect(statements).to_contain_text("The same seal")
    link = statements.get_by_role("link", name=re.compile("Max is Charles$"))
    expect(link).to_have_attribute("href", re.compile(rf"^/Ledger/{claims.first}\?show=[0-9a-f-]+$"))
    expect(statements.get_by_role("link", name=re.compile("Ledger of Bruges"))).to_be_visible()
    # (the alias is its own document: its chip goes to its page)
    marie = other(section, claims.marie)
    marie.get_by_test_id("identity-count").click()
    expect(marie.get_by_test_id("identity-claims").get_by_role("link")).to_have_attribute("href", f"/Alias/{claims.alias}")
    # Someone not logged in is not offered the comparison
    expect(section.get_by_test_id("identity-compare")).to_have_count(0)

    # The other entity's page says the same of this one; one that no claim names has no section
    page.goto(f"/Person/{claims.charles}")
    section = page.get_by_test_id("identity-section")
    expect(other(section, claims.maximilian).get_by_test_id("identity-count")).to_contain_text("2")
    expect(other(section, claims.marie, "Denied")).to_be_visible()
    page.goto(f"/Role/{claims.secretary_role}")
    hydrated(page)
    expect(page.get_by_test_id("identity-section")).to_have_count(0)


def test_two_said_to_be_the_same_are_merged_from_the_section_and_the_claims_still_name_both(logged_in: Page, claims):
    page = logged_in
    page.goto(f"/Person/{claims.maximilian}")
    section = page.get_by_test_id("identity-section")
    hydrated(page)
    # Logged in, each has the way to the comparison of the two, where they are merged
    other(section, claims.charles).get_by_test_id("identity-compare").click()
    expect(page).to_have_url(re.compile(rf"/Person/{claims.maximilian}/merge/{claims.charles}$"))
    page.get_by_test_id("merge-start").click()
    page.get_by_test_id("merge-confirm").click()
    expect(page.get_by_test_id("merge-summary")).to_be_visible()

    # The statements stay as they were written: Charles is still named, as merged into this, with nothing to compare
    page.goto(f"/Person/{claims.maximilian}")
    section = page.get_by_test_id("identity-section")
    charles = other(section, claims.charles)
    expect(charles.get_by_test_id("identity-merged")).to_have_text("merged into this")
    expect(charles.get_by_test_id("identity-count")).to_contain_text("2")
    expect(charles.get_by_test_id("identity-compare")).to_have_count(0)
    expect(other(section, claims.charles, "Denied")).to_be_visible()
    # (Marie, who is not merged, can still be compared; and what was said of Charles and Marie is now said of this one)
    expect(other(section, claims.marie).get_by_test_id("identity-compare")).to_be_visible()
    # The ledger still reads "Max is Charles", not "Max is Max"
    status, ledger = claims.api.send("GET", f"/api/Ledger/{claims.first}")
    assert status == 200
    assert [entity["id"] for entity in ledger["entries"][0]["target"]] == [claims.maximilian, claims.charles]
    assert ledger["entries"][0]["target"][1]["mergedInto"] == claims.maximilian
