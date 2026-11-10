"""What the rules derive about an item (`pangloss_derived`): its interface module adds a "Derived" section after the item's
contents (`itemSections.Derived`). The e2e project's rule `same_group` derives that two people with a `Membership` of one
group are of the same group. (The fixture `grouped` is in conftest.py.)"""

import re

from helpers import expand_nav, hydrated
from playwright.sync_api import Page, expect


def derived_in(page: Page, heading: str):
    return page.locator("main section").filter(has=page.locator("h2", has_text=heading))


def derived(page: Page):
    return derived_in(page, "Derived")


def facts_of(section):
    """The facts (not the justifications that "why" lists under one)"""
    return section.locator("dd > ul > li")


def test_what_is_derived_about_a_person_is_a_section_after_their_facts(
    page: Page, grouped
):
    page.goto(f"/Person/{grouped.jan}")
    hydrated(page)
    expect(page.locator("main h2")).to_have_text(["Derived"])
    section = derived(page)
    # (its class, with how many there are, and the first page of them: 25 of 27)
    expect(section.locator("dt")).to_have_text([re.compile(r"Same group\s*\(27\)")])
    facts = facts_of(section)
    expect(facts).to_have_count(25)
    # (each with the other member and the group, by the names of the fields (the two members are one "member"; not Jan),
    # and why)
    fact = re.compile(
        r"^Member\s*Person\s*(Pieter|Margriet|Councillor \d\d)\s*Group\s*Group\s*The (guild|council)\s*▸\s*Why \(1\)$",
        re.IGNORECASE,
    )
    expect(facts).to_have_text([fact] * 25)
    expect(section.locator(f'a[href="/Person/{grouped.jan}"]')).to_have_count(0)
    # (what refers to Jan stays with his facts, above; the section is not inside them)
    refers = page.get_by_test_id("incoming-by-field")
    expect(refers.get_by_role("link", name=re.compile("Jan in The guild"))).to_be_visible()

    # (it looks as a section: below the facts, well apart from them, under a bar across the page)
    facts_box = refers.bounding_box()
    bar = section.locator("h2").bounding_box()
    main = page.locator("main").bounding_box()
    assert facts_box and bar and main
    assert bar["y"] - (facts_box["y"] + facts_box["height"]) >= 48
    assert bar["width"] >= facts_box["width"] - 1
    assert bar["width"] <= main["width"]
    expect(section.locator("h2")).to_have_css("text-transform", "uppercase")


def all_facts(page: Page):
    """The facts of the section, all of them (the first page has 25: which, depends on their keys)"""
    section = derived(page)
    section.get_by_role("button", name="and 2 more").click()
    expect(facts_of(section)).to_have_count(27)
    return facts_of(section)


def test_why_shows_the_rule_and_the_documents_a_fact_rests_on(page: Page, grouped):
    page.goto(f"/Person/{grouped.jan}")
    hydrated(page)
    fact = all_facts(page).filter(
        has=page.get_by_role("link", name=re.compile("Margriet"))
    )
    why = fact.get_by_role("button", name="Why (1)")
    expect(why).to_have_attribute("aria-expanded", "false")
    why.click()
    expect(why).to_have_attribute("aria-expanded", "true")
    expect(fact).to_contain_text("Two people said to be members of one group")
    # (the evidence: the two memberships, each a chip that is a link to it)
    for membership in (
        grouped.memberships["jan_guild"],
        grouped.memberships["margriet"],
    ):
        expect(fact.locator(f'a[href="/Membership/{membership}"]')).to_be_visible()
    why.click()
    expect(fact).not_to_contain_text("Two people said to be members of one group")


def test_the_rest_of_the_facts_are_read_a_page_at_a_time(page: Page, grouped):
    page.goto(f"/Person/{grouped.jan}")
    hydrated(page)
    section = derived(page)
    all_facts(page)
    expect(section.get_by_role("button", name=re.compile("more"))).to_have_count(0)
    # (each councillor once)
    expect(section.get_by_role("link", name=re.compile("Councillor"))).to_have_count(25)


def test_the_sections_follow_one_another_and_one_with_nothing_is_not_there(
    page: Page, grouped
):
    # (sorted by date, the timeline comes before what is derived)
    page.goto(f"/Person/{grouped.jan}")
    hydrated(page)
    page.get_by_role("button", name="Sort by date").click()
    expect(page.locator("main h2")).to_have_text(["Timeline", "Derived"])
    page.get_by_role("button", name="Sort by date").click()
    expect(page.locator("main h2")).to_have_text(["Derived"])
    # (a person of no group: no section)
    page.goto(f"/Person/{grouped.hendrik}")
    hydrated(page)
    expect(page.get_by_role("heading", level=1)).to_have_text("Hendrik")
    expect(page.locator("main h2")).to_have_count(0)


def test_a_document_has_no_section_for_what_it_is_evidence_of(page: Page, grouped):
    """What a document is evidence of is what it says itself, so its page does not repeat it as derived: the API gives
    it when asked (`?evidence=`), and the person's "Why" links to the document"""
    membership = grouped.memberships["pieter"]
    # (Pieter's membership of the guild is evidence that he is of one group with Jan, and with Margriet)
    assert grouped.api.ok("GET", f"/api/derived/SameGroup?evidence={membership}")["count"] == 2
    assert grouped.api.ok("GET", f"/api/derived/about/Membership/{membership}") == {}
    page.goto(f"/Membership/{membership}")
    hydrated(page)
    expect(page.get_by_role("heading", level=1, name="Pieter in The guild")).to_be_visible()
    expect(page.locator("main").get_by_role("link", name="Person Pieter")).to_be_visible()
    expect(page.get_by_test_id("derived-section")).to_have_count(0)
    expect(page.locator("main h2")).to_have_count(0)


def test_a_fact_whose_evidence_is_deleted_is_gone_at_once(page: Page, grouped):
    grouped.api.ok("DELETE", f"/api/Membership/{grouped.memberships['margriet']}")
    page.goto(f"/Person/{grouped.jan}")
    hydrated(page)
    section = derived(page)
    expect(section.locator("dt")).to_have_text([re.compile(r"Same group\s*\(26\)")])
    section.get_by_role("button", name="and 1 more").click()
    expect(facts_of(section)).to_have_count(26)
    expect(section.get_by_role("link", name=re.compile("Margriet"))).to_have_count(0)
    expect(section.get_by_role("link", name=re.compile("Pieter"))).to_have_count(1)


def test_the_words_of_the_modules_are_their_own_and_follow_the_language(
    page: Page, grouped
):
    # (each interface module's texts are in its app's translations/ui.jsonc, not the interface's: the derived section,
    # the timeline and its button (pangloss_dates), the calendar's link and the typologies' section in the bar)
    page.goto(f"/Person/{grouped.jan}")
    expand_nav(page)
    page.get_by_role("button", name="Deutsch").click()
    expect(page.locator("html")).to_have_attribute("lang", "de")
    nav = page.locator("nav[aria-label]").first
    expect(nav.get_by_role("link", name="Kalender")).to_be_visible()
    expect(nav).to_contain_text("Typologien")
    # (off the bar: it closes)
    page.mouse.move(600, 400)
    expect(page.locator("main h2")).to_have_text(["Abgeleitet"])
    expect(
        facts_of(derived_in(page, "Abgeleitet")).first.get_by_role("button")
    ).to_have_text("▸Warum (1)")
    page.get_by_role("button", name="Nach Datum sortieren").click()
    expect(page.locator("main h2")).to_have_text(["Zeitleiste", "Abgeleitet"])
    page.get_by_role("button", name="Nach Datum sortieren").click()
    page.locator("nav[aria-label]").first.hover()
    page.get_by_role("button", name="English").click()
    expect(page.locator("main h2")).to_have_text(["Derived"])
