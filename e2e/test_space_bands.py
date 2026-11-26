"""What kind of space a band is (`spaceBand`, `primitives/kindTint.ts`): a faint pattern over the band's tint, by what the
space says of what it holds. In the e2e project (conftest.py) `Not` (`logical="not"`) denies, so is hatched; `Denied`
is a plain space (only a colour), so has no pattern; `Reported`, also plain, asks for dots (`InterfaceMeta(band="dots")`)."""

import re
from types import SimpleNamespace

import pytest
from conftest import forget
from helpers import hydrated
from playwright.sync_api import Page, expect


@pytest.fixture
def ledgers(data) -> SimpleNamespace:
    """A ledger with an entry in `Not` and one in `Denied`; an affidavit with a claim in `Not`; a hearsay reported"""
    forget("Affidavit", "Hearsay", "Not", "Reported", "Denied", "Claim")
    api = data.api

    def same(label: str) -> dict:
        return {
            "type": "SameEntity",
            "label": label,
            "target": [{"type": "Person", "id": data.maximilian}, {"type": "Person", "id": data.charles}],
        }

    ledger = api.ok(
        "POST",
        "/api/Ledger",
        {
            "label": "Ledger of Bruges",
            "entries": [
                {"type": "Not", "contents": [same("Max is not Charles")]},
                {"type": "Denied", "contents": [same("Max is Charles, denied")]},
            ],
        },
    )["id"]
    api.ok(
        "POST",
        "/api/Affidavit",
        {
            "label": "An affidavit",
            "deponent": {"type": "Person", "id": data.marie},
            "claims": [{"type": "Not", "contents": [{"type": "Claim", "label": "The mill burnt", "text": "It did not"}]}],
        },
    )
    hearsay = api.ok(
        "POST",
        "/api/Hearsay",
        {
            "label": "Hearsay",
            "account": {"type": "Reported", "contents": [{"type": "Claim", "label": "The well ran dry", "text": "So they say"}]},
        },
    )["id"]
    return SimpleNamespace(ledger=ledger, hearsay=hearsay)


def band_of(page: Page, space: str):
    """The band of a space on an item's page: the box its head is in"""
    return page.locator(f"main div:has(> div > [data-type-info='{space}'])").first


def background_image(locator) -> str:
    return locator.evaluate("element => getComputedStyle(element).backgroundImage")


def test_a_not_band_is_hatched_a_plain_one_is_not_and_a_class_has_its_own(page: Page, ledgers):
    page.goto(f"/Ledger/{ledgers.ledger}")
    hydrated(page)
    hatched = band_of(page, "Not")
    expect(hatched).to_have_attribute("data-band", "hatch")
    expect(hatched).to_contain_text("Max is not Charles")
    assert "repeating-linear-gradient" in background_image(hatched)
    plain = band_of(page, "Denied")
    expect(plain).to_contain_text("Max is Charles, denied")
    expect(plain).not_to_have_attribute("data-band", re.compile("."))
    assert background_image(plain) == "none"

    # A class's own pattern, over its kind's (a plain space's, none)
    page.goto(f"/Hearsay/{ledgers.hearsay}")
    hydrated(page)
    dotted = band_of(page, "Reported")
    expect(dotted).to_have_attribute("data-band", "dots")
    assert "radial-gradient" in background_image(dotted)

    # The tabs round a row of a list: the same
    page.goto("/Claim")
    hydrated(page)
    row = page.locator("main li", has=page.get_by_role("link", name=re.compile("The mill burnt")))
    tab = row.locator("[data-band='hatch']")
    expect(tab).to_have_count(1)
    expect(tab).to_contain_text("Not")
    assert "repeating-linear-gradient" in background_image(tab)
    dry = page.locator("main li", has=page.get_by_role("link", name=re.compile("The well ran dry")))
    expect(dry.locator("[data-band='dots']")).to_have_count(1)
