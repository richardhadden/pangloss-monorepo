"""What an item's path says of it (the walk, `schema/spaces.ts` in the interface): a mark where it is listed without
its bands ("Denied" for a claim in `Not`; none for a plain one, nor for one in a plain space); the degree of a space
beside its head (`Hearsay.account: Reported[Claim] | Claim`, `Reported` with a field marked `Degree()`), on the page
and in the form; and a claim of identity in `Not` (`Ledger.entries`), which says the two are different, in an
entity's section and its cluster (conftest.py)."""

import re
from types import SimpleNamespace

import pytest
from conftest import forget
from helpers import hydrated, pick
from playwright.sync_api import Page, expect


@pytest.fixture
def claims(data) -> SimpleNamespace:
    """An affidavit whose one claim is in `Not` and the other plain; a hearsay whose claim is reported with no degree,
    and one reported as likely"""
    forget("Affidavit", "Hearsay", "Not", "Reported", "Claim")
    api = data.api
    affidavit = api.ok(
        "POST",
        "/api/Affidavit",
        {
            "label": "An affidavit",
            "deponent": {"type": "Person", "id": data.marie},
            "claims": [
                {"type": "Not", "contents": [{"type": "Claim", "label": "The mill burnt", "text": "It did not"}]},
                {"type": "Claim", "label": "The bridge fell", "text": "It fell in"},
            ],
        },
    )["id"]

    def hearsay(label: str, claim: str, **degree) -> str:
        return api.ok(
            "POST",
            "/api/Hearsay",
            {
                "label": label,
                "account": {
                    "type": "Reported",
                    **degree,
                    "contents": [{"type": "Claim", "label": claim, "text": "So they say"}],
                },
            },
        )["id"]

    plain = hearsay("Hearsay", "The well ran dry")
    likely = hearsay("Likely hearsay", "The tower leant", howLikely="likely")
    return SimpleNamespace(api=api, affidavit=affidavit, plain=plain, likely=likely)


def row_of(page: Page, label: str):
    """A row of a list, by its label"""
    return page.locator("main li", has=page.get_by_role("link", name=re.compile(label)))


def test_a_claim_in_not_is_marked_denied_in_the_list_and_a_plain_one_is_not(page: Page, claims):
    page.goto("/Claim")
    hydrated(page)
    denied = row_of(page, "The mill burnt")
    expect(denied.locator("[data-assertion]")).to_have_text("Denied")
    expect(denied.locator("[data-assertion]")).to_have_attribute("data-assertion", "denied")
    # (a plain one, and one in a plain space, which its band names: nothing)
    expect(row_of(page, "The bridge fell")).to_be_visible()
    expect(row_of(page, "The bridge fell").locator("[data-assertion]")).to_have_count(0)
    expect(row_of(page, "The well ran dry").locator("[data-assertion]")).to_have_count(0)
    # (reported with a degree: marked, the degree in its title)
    reported = row_of(page, "The tower leant").locator("[data-assertion]")
    expect(reported).to_have_text("Reported")
    expect(reported).to_have_attribute("title", "Reported: likely")

    # Its own page says it once, beside what it is contained in; the bands round the page say where
    denied.get_by_role("link", name=re.compile("The mill burnt")).click()
    expect(page).to_have_url(re.compile(r"/Claim/[0-9a-f-]+$"))
    hydrated(page)
    main = page.locator("main")
    expect(main).to_contain_text("Contained in")
    expect(main.locator("[data-assertion]")).to_have_count(1)
    expect(main.locator("[data-assertion]")).to_have_text("Denied")


def test_the_degree_is_beside_a_spaces_head_on_the_page_and_set_in_the_form(logged_in: Page, claims):
    page = logged_in
    page.goto(f"/Hearsay/{claims.likely}")
    hydrated(page)
    degree = page.locator("main [data-space-degree]")
    expect(degree).to_have_text("likely")
    # (beside the head, not a row of its own)
    expect(page.locator("main dt", has_text=re.compile("^How likely", re.I))).to_have_count(0)

    # In the form: a menu in the head's bar, which says there is no default for this class
    page.goto(f"/Hearsay/{claims.plain}/edit")
    hydrated(page)
    menu = page.get_by_role("combobox", name="How likely")
    expect(menu).to_be_visible()
    expect(menu).to_contain_text("No degree")
    expect(page.locator("main dt", has_text=re.compile("^How likely", re.I))).to_have_count(0)
    pick(menu, "unlikely")
    expect(menu).to_have_attribute("data-value", "unlikely")
    with page.expect_response(
        lambda response: response.request.method == "PUT" and f"/api/Hearsay/{claims.plain}" in response.url
    ) as answer:
        page.get_by_role("button", name="Save", exact=True).click()
    assert answer.value.ok, answer.value.text()
    assert claims.api.ok("GET", f"/api/Hearsay/{claims.plain}")["account"]["howLikely"] == "unlikely"
    expect(page).to_have_url(re.compile(rf"/Hearsay/{claims.plain}$"))
    hydrated(page)
    expect(page.locator("main [data-space-degree]")).to_have_text("unlikely")

    # And read back into the form as chosen
    page.goto(f"/Hearsay/{claims.plain}/edit")
    hydrated(page)
    expect(page.get_by_role("combobox", name="How likely")).to_have_attribute("data-value", "unlikely")


@pytest.fixture
def different(data) -> SimpleNamespace:
    """Maximilian is said to be Charles in one ledger and, in `Not`, said not to be in another"""
    forget("PGMerge", "PGMergeMove")

    def person(id: str) -> dict:
        return {"type": "Person", "id": id}

    def same(label: str) -> dict:
        return {"type": "SameEntity", "label": label, "target": [person(data.maximilian), person(data.charles)]}

    data.api.ok("POST", "/api/Ledger", {"label": "Ledger of Ghent", "entries": [same("Max is Charles")]})
    denial = data.api.ok(
        "POST", "/api/Ledger", {"label": "Ledger of Lille", "entries": [{"type": "Not", "contents": [same("Max is not Charles")]}]}
    )["id"]
    return SimpleNamespace(**{**vars(data), "denial": denial})


def test_a_claim_of_identity_in_not_says_the_two_are_different_and_joins_nothing(page: Page, different):
    page.goto(f"/Person/{different.maximilian}")
    hydrated(page)
    section = page.get_by_test_id("identity-section")
    # (the page's reading of the claims: the one in `Not` is not among those that say they are the same)
    plain = section.locator("[data-testid='identity-context'][data-said='1']")
    expect(plain).to_contain_text("Said to be the same as")
    expect(plain.locator(f"[data-testid='identity-other'][data-id='{different.charles}'] [data-testid='identity-count']")).to_contain_text("1")
    apart = section.locator("[data-testid='identity-context'][data-said='-1']")
    expect(apart).to_contain_text("Said to be different from")
    expect(apart.locator(f"[data-testid='identity-other'][data-id='{different.charles}']")).to_be_visible()
    expect(section.locator(f"[data-testid='identity-other'][data-id='{different.charles}'] [data-testid='identity-contested']").first).to_be_visible()
    # (the cluster: two, and the claim given apart, a chip to its place in its ledger)
    cluster = section.get_by_test_id("identity-cluster")
    expect(cluster.get_by_test_id("identity-size")).to_have_text("These statements join 2 entities.")
    said = cluster.get_by_test_id("identity-said-different")
    expect(said).to_have_count(1)
    expect(said).to_contain_text("are both in this group, though a statement says they are different")
    expect(said.get_by_role("link", name=re.compile("Max is not Charles"))).to_have_attribute(
        "href", re.compile(rf"^/Ledger/{different.denial}\?show=[0-9a-f-]+$")
    )
    expect(cluster.get_by_test_id("identity-dispute")).to_have_count(0)
