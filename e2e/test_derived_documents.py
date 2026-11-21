"""Derived documents (`pangloss_derived`; implementation_docs/derived.md): the e2e project's rule `fellow_apprentices`
writes a `DerivedFellowship` of two apprentices of one master. Its page says why it is there and is not edited; a
source's page lists what is derived from it; someone makes it their own (a `Fellowship`, in place); a search divides
derived documents from the others; and a document that cites one cites what it rests on, and says when the derivation
no longer holds."""

import re
import time
from types import SimpleNamespace

import pytest
from conftest import Stack, forget
from helpers import add_filter, hydrated, outside_similar, pick
from playwright.sync_api import Page, expect


def wait_until(condition, what: str, seconds: float = 60):
    deadline = time.monotonic() + seconds
    while True:
        found = condition()
        if found:
            return found
        assert time.monotonic() < deadline, f"the worker did not {what}"
        time.sleep(0.3)


@pytest.fixture
def fellows(types: Stack) -> SimpleNamespace:
    """Anna and Bram, each an apprentice of Master Claes: so the rule derives one fellowship of the two"""
    forget("PGJustification", "PGCitation", "PGUnprotectedCitation", "PGCitedBasis")
    api = types.admin()

    def made(kind: str, label: str, **fields) -> str:
        return api.ok("POST", f"/api/{kind}", {"label": label, **fields})["id"]

    claes, anna, bram = (
        made("Person", name, has_role=[]) for name in ("Master Claes", "Anna", "Bram")
    )

    def apprenticed(person: str, name: str) -> str:
        return made(
            "Apprenticeship",
            f"{name}, apprentice of Claes",
            apprentice={"type": "Person", "id": person},
            master={"type": "Person", "id": claes},
        )

    of_anna, of_bram = apprenticed(anna, "Anna"), apprenticed(bram, "Bram")
    listed = wait_until(
        lambda: api.ok("GET", "/api/DerivedFellowship")["results"],
        "derive the fellowship",
    )
    assert len(listed) == 1
    return SimpleNamespace(
        api=api,
        claes=claes,
        anna=anna,
        bram=bram,
        of_anna=of_anna,
        of_bram=of_bram,
        derived=listed[0]["id"],
    )


def why(page: Page):
    return page.get_by_test_id("derived-why")


def test_a_derived_document_says_why_it_is_there_and_is_not_edited(
    logged_in: Page, fellows
):
    page = logged_in
    page.goto(f"/DerivedFellowship/{fellows.derived}")
    hydrated(page)
    expect(page.get_by_role("heading", level=1)).to_have_text("Fellow apprentices")
    main = page.locator("main")
    # (what it says, as any document: the two fellows) (the section "Similar" after the contents lists other items too)
    expect(outside_similar(main.get_by_role("link", name="Person Anna"))).to_be_visible()
    expect(outside_similar(main.get_by_role("link", name="Person Bram"))).to_be_visible()
    # (its sources are citations, shown as what they cite: chips, never a block of a citation's own fields)
    for source in (fellows.of_anna, fellows.of_bram):
        expect(
            main.locator(f"[data-citation='{source}']").get_by_role("link")
        ).to_have_attribute("href", f"/Apprenticeship/{source}")
    expect(main).not_to_contain_text("Target id")

    section = why(page)
    expect(section.locator("h2")).to_have_text("Derived")
    expect(section).to_contain_text("Made by the rule fellow_apprentices")
    expect(section).to_contain_text("it is not edited by hand")
    expect(section.locator(f'a[href="/Apprenticeship/{fellows.of_anna}"]')).to_be_visible()
    expect(section.locator(f'a[href="/Apprenticeship/{fellows.of_bram}"]')).to_be_visible()
    # (nobody writes one but the worker: no Edit, no Delete, though someone is logged in; and no "New" of the class)
    expect(page.get_by_role("link", name="Edit")).to_have_count(0)
    expect(page.get_by_role("button", name="Delete")).to_have_count(0)
    expect(section.get_by_test_id("derived-convert")).to_have_text(
        re.compile("Make it my own: Fellowship", re.I)
    )
    page.goto("/DerivedFellowship")
    hydrated(page)
    expect(page.get_by_role("link", name=re.compile("^New"))).to_have_count(0)
    # (the form of one is not to be had by its address either)
    assert fellows.api.send(
        "PUT",
        f"/api/DerivedFellowship/{fellows.derived}",
        {"id": fellows.derived, "label": "Mine", "fellows": [], "sources": []},
    )[0] in (400, 403, 405, 409, 422, 428)


def test_a_reader_sees_why_and_is_not_offered_to_make_it_their_own(page: Page, fellows):
    page.goto(f"/DerivedFellowship/{fellows.derived}")
    hydrated(page)
    expect(why(page)).to_contain_text("Made by the rule fellow_apprentices")
    expect(page.get_by_test_id("derived-convert")).to_have_count(0)


def test_a_source_lists_what_is_derived_from_it(page: Page, fellows):
    page.goto(f"/Apprenticeship/{fellows.of_anna}")
    hydrated(page)
    section = page.get_by_test_id("derived-from-this")
    expect(section.locator("h2")).to_have_text(re.compile(r"Derived from this \(1\)", re.I))
    expect(section.get_by_role("link", name=re.compile("Fellow apprentices"))).to_have_attribute(
        "href", f"/DerivedFellowship/{fellows.derived}"
    )
    # (a document nothing is derived from has no such section, nor one that says why it is there)
    page.goto(f"/Person/{fellows.anna}")
    hydrated(page)
    expect(page.get_by_role("heading", level=1)).to_have_text("Anna")
    expect(page.get_by_test_id("derived-from-this")).to_have_count(0)
    expect(why(page)).to_have_count(0)


def converted(page: Page, fellows) -> None:
    """Makes the derived fellowship a `Fellowship`, through the form, with a note"""
    page.goto(f"/DerivedFellowship/{fellows.derived}")
    hydrated(page)
    why(page).get_by_test_id("derived-convert").click()
    expect(page).to_have_url(
        re.compile(f"/derived/convert/DerivedFellowship/{fellows.derived}/Fellowship$")
    )
    hydrated(page)
    expect(page.get_by_test_id("convert-note")).to_contain_text("Nothing is written until you save")
    page.get_by_label("Note", exact=True).fill("As the guild book has it")
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page).to_have_url(re.compile(f"/Fellowship/{fellows.derived}$"))


def test_someone_makes_a_derived_document_their_own(logged_in: Page, fellows):
    page = logged_in
    page.goto(f"/DerivedFellowship/{fellows.derived}")
    hydrated(page)
    why(page).get_by_test_id("derived-convert").click()
    hydrated(page)
    # The form of a Fellowship, filled in with what the two share; its sources are its evidence now, as citations
    expect(page.get_by_label("Label", exact=True)).to_have_value("Fellow apprentices")
    form = page.locator("main form")
    expect(form.get_by_text("Anna", exact=True)).to_be_visible()
    expect(form.get_by_text("Bram", exact=True)).to_be_visible()
    for source in (fellows.of_anna, fellows.of_bram):
        expect(form.locator(f"[data-citation='{source}']")).to_have_count(1)
    # (nothing is written yet: it is still the derived document)
    assert fellows.api.ok("GET", f"/api/DerivedFellowship/{fellows.derived}")["id"] == fellows.derived
    # (Cancel goes back to it, as it was)
    page.get_by_role("button", name="Cancel", exact=True).click()
    expect(page).to_have_url(re.compile(f"/DerivedFellowship/{fellows.derived}$"))

    converted(page, fellows)
    hydrated(page)
    # The same address but for its class; it says what it was, and is edited as any document now
    main = page.locator("main")
    expect(main).to_contain_text("As the guild book has it")
    section = why(page)
    expect(section.locator("h2")).to_have_text(re.compile("Made from a derivation", re.I))
    expect(section).to_contain_text("made by the rule fellow_apprentices")
    expect(section.get_by_test_id("derived-convert")).to_have_count(0)
    expect(section.get_by_test_id("derived-lost")).to_have_count(0)
    expect(page.get_by_role("link", name="Edit")).to_be_visible()
    api = fellows.api
    assert api.send("GET", f"/api/DerivedFellowship/{fellows.derived}")[0] == 404
    item = api.ok("GET", f"/api/Fellowship/{fellows.derived}")
    assert item["meta"]["version"] == 2
    assert sorted(c["targetId"] for c in item["evidence"]) == sorted(
        [fellows.of_anna, fellows.of_bram]
    )
    # (whoever reviews it is told what it was: an open comment on it, of the kind)
    comments = api.ok("GET", f"/api/review/{fellows.derived}")["comments"]
    assert [c["kind"] for c in comments] == ["converted"]
    assert "DerivedFellowship" in comments[0]["text"]

    # The worker leaves it alone: no second one is derived in its place
    time.sleep(1.5)
    assert api.ok("GET", "/api/DerivedFellowship")["results"] == []
    # Its sources are cited now (and protected), not what something is derived from
    page.goto(f"/Apprenticeship/{fellows.of_anna}")
    hydrated(page)
    expect(page.get_by_role("heading", level=1)).to_contain_text("Anna")
    expect(page.get_by_test_id("derived-from-this")).to_have_count(0)
    assert api.send("DELETE", f"/api/Apprenticeship/{fellows.of_anna}")[0] == 409


def test_the_queue_of_review_shows_the_documents_with_something_open(
    logged_in: Page, fellows
):
    page = logged_in
    converted(page, fellows)
    # (published, as the derived document was; among the published, it is the one with something to look at)
    page.goto("/review?status=published")
    hydrated(page)
    rows = page.get_by_test_id("review-queue-row")
    expect(rows.filter(has_text="Fellow apprentices")).to_have_count(1)
    pick(page.get_by_role("combobox", name="Show"), label="With open comments")
    expect(page).to_have_url(re.compile("commented=true"))
    expect(rows).to_have_count(1)
    expect(rows).to_contain_text("Fellow apprentices")
    pick(page.get_by_role("combobox", name="Show"), label="All")
    expect(page).not_to_have_url(re.compile("commented"))


def test_a_search_divides_the_derived_documents_from_the_others(logged_in: Page, fellows):
    page = logged_in
    api = fellows.api
    # (a fellowship someone wrote, beside the derived one)
    api.ok(
        "POST",
        "/api/Fellowship",
        {
            "label": "Written by hand",
            "fellows": [{"type": "Person", "id": fellows.anna}],
            "evidence": [],
        },
    )
    page.goto("/AbstractFellowship")
    hydrated(page)
    results = page.locator("main ul[style] > li")
    expect(results).to_have_count(2)
    page.get_by_role("button", name="Search by fields").click()
    add_filter(page, "Derived")
    # (yes, as it is added)
    expect(results).to_have_count(1)
    expect(results).to_contain_text("Fellow apprentices")
    pick(page.get_by_role("combobox", name="Derived", exact=True), label="No")
    expect(results).to_have_count(1)
    expect(results).to_contain_text("Written by hand")
    # (it is in the address, and so kept through a reload)
    page.reload()
    hydrated(page)
    expect(results).to_have_count(1)
    expect(results).to_contain_text("Written by hand")
    page.get_by_role("button", name=re.compile("^Remove the condition on Derived", re.I)).click()
    expect(results).to_have_count(2)
    # (a class all of whose documents are derived, or none, is not offered the filter)
    page.goto("/Fellowship")
    hydrated(page)
    page.get_by_role("button", name="Search by fields").click()
    menu = page.get_by_role("combobox", name="Add a filter").last
    menu.click()
    listbox = page.locator(f"[id='{menu.get_attribute('aria-controls')}']")
    expect(listbox.get_by_role("option").first).to_be_visible()
    expect(listbox.get_by_role("option", name="Derived", exact=True)).to_have_count(0)


def test_a_document_that_cites_a_derived_one_cites_what_it_rests_on(
    logged_in: Page, fellows
):
    page = logged_in
    api = fellows.api
    remark = api.ok(
        "POST",
        "/api/Remark",
        {
            "label": "A remark",
            "cites": [{"type": "DerivedFellowship", "id": fellows.derived}],
        },
    )["id"]
    page.goto(f"/Remark/{remark}")
    hydrated(page)
    basis = page.locator(f"main [data-cited-basis='{fellows.derived}']")
    # What was chosen, as a chip that leads to it; the rule; and what it rests on, each as a citation is
    expect(basis.get_by_role("link", name=re.compile("Fellow apprentices"))).to_have_attribute(
        "href", f"/DerivedFellowship/{fellows.derived}"
    )
    expect(basis).to_contain_text("derived by the rule fellow_apprentices, from:")
    for source in (fellows.of_anna, fellows.of_bram):
        expect(
            basis.locator(f"[data-citation='{source}']").get_by_role("link")
        ).to_have_attribute("href", f"/Apprenticeship/{source}")
    expect(basis.locator("[data-derivation-state]")).to_have_count(0)
    expect(page.locator("main")).not_to_contain_text("Via id")

    # The derivation is lost (a source is deleted, by an admin who says so): the remark says it
    status, _ = api.send(
        "DELETE", f"/api/Apprenticeship/{fellows.of_bram}?acknowledge_citations=removals"
    )
    assert status < 300
    wait_until(
        lambda: api.ok("GET", f"/api/Remark/{remark}")["cites"][0]["derivationState"] == "lost",
        "mark the citation",
    )
    page.reload()
    hydrated(page)
    expect(basis.locator("[data-derivation-state='lost']")).to_have_text(
        "this derivation no longer holds"
    )
    # (what was chosen is gone: its name as it was cited, and no link to it)
    expect(basis).to_contain_text("Fellow apprentices")
    expect(basis.locator(f'a[href="/DerivedFellowship/{fellows.derived}"]')).to_have_count(0)

    # In the form it is one item, which goes whole or stays; "Seen" takes the mark off when it is saved
    page.get_by_role("link", name="Edit").click()
    hydrated(page)
    in_form = page.locator(f"main form [data-cited-basis='{fellows.derived}']")
    expect(in_form.locator("[data-derivation-state='lost']")).to_be_visible()
    expect(in_form.get_by_role("button", name=re.compile("^Remove the citation"))).to_have_count(1)
    in_form.get_by_role("button", name="Seen", exact=True).click()
    expect(in_form.locator("[data-derivation-state]")).to_have_count(0)
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page).to_have_url(re.compile(f"/Remark/{remark}$"))
    hydrated(page)
    expect(basis).to_be_visible()
    expect(basis.locator("[data-derivation-state]")).to_have_count(0)
    assert api.ok("GET", f"/api/Remark/{remark}")["cites"][0]["derivationState"] == ""


def test_a_citation_is_added_as_a_citation_never_as_a_basis(logged_in: Page, fellows):
    """The menu that adds to a `Cites` field offers the citation alone: a basis is what the server makes of one"""
    page = logged_in
    page.goto("/Remark/new")
    hydrated(page)
    page.get_by_role("textbox", name="Label").fill("Another remark")
    page.get_by_role("button", name=re.compile("^Add")).first.click()
    # (no choice between two classes: the search for what to cite is there at once)
    expect(page.locator("[data-citation-picker]")).to_have_count(1)
    expect(page.get_by_role("menuitem", name=re.compile("basis", re.I))).to_have_count(0)
    picker = page.locator("[data-citation-picker]")
    picker.get_by_role("combobox").or_(picker.get_by_role("searchbox")).or_(
        picker.get_by_role("textbox")
    ).first.fill("Fellow apprentices")
    # (the words are also the start of the names of classes: the list that offers those is closed, to reach the result)
    expect(picker.get_by_text("Fellow apprentices").locator("visible=true").first).to_be_visible()
    page.keyboard.press("Escape")
    # (the result of the search: not the box's own copy of what was typed, which is not shown)
    picker.get_by_text("Fellow apprentices").locator("visible=true").first.click()
    # (the document itself can be cited here: a fellowship)
    picker.get_by_role("button", name="Cite “Fellow apprentices”").click()
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page).to_have_url(re.compile(r"/Remark/[0-9a-f-]{36}$"))
    hydrated(page)
    # (saved, it is the basis: what the derived fellowship rests on)
    basis = page.locator(f"main [data-cited-basis='{fellows.derived}']")
    expect(basis.locator("[data-citation]")).to_have_count(2)
