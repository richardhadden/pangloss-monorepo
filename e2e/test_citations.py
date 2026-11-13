"""A document that cites parts of another (`Cites[T]`; implementation_docs/entity-identity.md, part 3): the citation as
chips, the search that makes one, who cites a document, and what a change to something cited asks."""

import re
from types import SimpleNamespace

import pytest
from conftest import forget
from helpers import hydrated
from playwright.sync_api import Page, expect


@pytest.fixture
def deed(data) -> SimpleNamespace:
    """A deed with two provisions, one of them denied, and a gloss that cites both"""
    forget("Gloss", "Deed", "Provision", "PGCitation")
    api = data.api
    made = api.ok(
        "POST",
        "/api/Deed?detail=true",
        {
            "label": "Deed of Ghent",
            "provisions": [
                {"type": "Provision", "label": "The mill is granted", "wording": "We grant the mill"},
                {"type": "Denied", "contents": [{"type": "Provision", "label": "The toll is owed", "wording": "No toll"}]},
            ],
        },
    )
    granted = made["provisions"][0]["id"]
    owed = made["provisions"][1]["contents"][0]["id"]
    gloss = api.ok(
        "POST",
        "/api/Gloss",
        {"label": "Gloss on Ghent", "cites": [{"type": "Provision", "id": granted}, {"type": "Provision", "id": owed}]},
    )["id"]
    return SimpleNamespace(**{**vars(data), "deed": made["id"], "granted": granted, "owed": owed, "gloss": gloss})


def citation(page_or_locator, target: str):
    return page_or_locator.locator(f"[data-citation='{target}']")


def test_a_citation_is_shown_as_what_it_cites_and_the_cited_says_by_what(page: Page, deed):
    page.goto(f"/Gloss/{deed.gloss}")
    hydrated(page)
    main = page.locator("main")
    # What is cited is a chip that goes to its place in its document, with that document as another chip
    first = citation(main, deed.granted)
    expect(first.get_by_role("link", name=re.compile("The mill is granted"))).to_have_attribute(
        "href", f"/Deed/{deed.deed}?show={deed.granted}"
    )
    expect(first.get_by_role("link", name=re.compile("Deed of Ghent"))).to_have_attribute("href", f"/Deed/{deed.deed}")
    # (one that is denied is in the band of its space, as it is in its own document)
    second = citation(main, deed.owed)
    expect(second).to_contain_text("The toll is owed")
    expect(second).to_contain_text("Denied")
    expect(main).not_to_contain_text("changed since cited")

    # The deed says which of it is cited, and by what
    page.goto(f"/Deed/{deed.deed}")
    notice = page.locator("[data-cited-by]")
    expect(notice).to_contain_text("Cited as evidence")
    expect(notice).to_contain_text("“The mill is granted”, by")
    expect(notice.get_by_role("link", name=re.compile("Gloss on Ghent")).first).to_have_attribute(
        "href", f"/Gloss/{deed.gloss}"
    )
    # ... and a document that nothing cites says nothing
    page.goto(f"/Gloss/{deed.gloss}")
    hydrated(page)
    expect(page.locator("[data-citation]").first).to_be_visible()
    expect(page.locator("[data-cited-by]")).to_have_count(0)


def test_a_citation_is_made_by_finding_the_document_and_choosing_a_part(logged_in: Page, deed):
    page = logged_in
    page.goto("/Gloss/new")
    hydrated(page)
    page.get_by_role("textbox", name="Label").fill("Another gloss")
    page.get_by_role("button", name=re.compile("^Add")).first.click()
    picker = page.locator("[data-citation-picker]")
    picker.get_by_role("combobox").or_(picker.get_by_role("searchbox")).or_(picker.get_by_role("textbox")).first.fill(
        "Deed of Ghent"
    )
    picker.get_by_text("Deed of Ghent").first.click()
    # The parts of it that can be cited here: both provisions, not the deed itself
    expect(picker.get_by_role("button", name=re.compile("^Cite “"))).to_have_count(2)
    picker.get_by_role("button", name="Cite “The toll is owed”").click()
    expect(page.locator("[data-citation-picker]")).to_have_count(0)
    expect(citation(page, deed.owed)).to_contain_text("The toll is owed")

    page.get_by_role("button", name="Save", exact=True).click()
    expect(page).to_have_url(re.compile(r"/Gloss/[0-9a-f-]{36}$"))
    made = citation(page.locator("main"), deed.owed)
    expect(made.get_by_role("link", name=re.compile("The toll is owed"))).to_have_attribute(
        "href", f"/Deed/{deed.deed}?show={deed.owed}"
    )


def test_a_change_to_what_is_cited_is_asked_about_and_marks_the_citation(logged_in: Page, deed):
    page = logged_in
    page.goto(f"/Deed/{deed.deed}/edit")
    hydrated(page)
    # The form says what of it is cited, before anything is changed
    expect(page.locator("[data-cited-by]")).to_contain_text("has to be confirmed when you save")
    wording = page.get_by_role("textbox", name="Wording").first
    expect(wording).to_have_value("We grant the mill")
    wording.fill("We grant the mill and its pond")
    page.get_by_role("button", name="Save", exact=True).click()

    dialog = page.locator("[data-cited-dialog]")
    expect(dialog).to_contain_text("This changes what other documents cite as evidence")
    expect(dialog.get_by_role("link", name=re.compile("Gloss on Ghent"))).to_have_attribute("href", f"/Gloss/{deed.gloss}")
    # (cancelled: nothing is saved, and the form is as it was)
    dialog.get_by_role("button", name="Cancel").click()
    expect(page.locator("[data-cited-dialog]")).to_have_count(0)
    assert deed.api.ok("GET", f"/api/Deed/{deed.deed}")["provisions"][0]["wording"] == "We grant the mill"

    page.get_by_role("button", name="Save", exact=True).click()
    page.locator("[data-cited-dialog]").get_by_role("button", name="Save anyway").click()
    expect(page).to_have_url(re.compile(rf"/Deed/{deed.deed}$"))
    assert deed.api.ok("GET", f"/api/Deed/{deed.deed}")["provisions"][0]["wording"] == "We grant the mill and its pond"
    expect(page.locator("[data-cited-by]")).to_contain_text("changed since cited")

    # The gloss says so at the citation; "Seen" in its form takes the mark off
    page.goto(f"/Gloss/{deed.gloss}")
    expect(citation(page.locator("main"), deed.granted)).to_contain_text("changed since cited")
    expect(citation(page.locator("main"), deed.owed)).not_to_contain_text("changed since cited")
    page.goto(f"/Gloss/{deed.gloss}/edit")
    hydrated(page)
    citation(page, deed.granted).get_by_role("button", name="Seen").click()
    expect(citation(page, deed.granted)).not_to_contain_text("changed since cited")
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page).to_have_url(re.compile(rf"/Gloss/{deed.gloss}$"))
    expect(citation(page.locator("main"), deed.granted)).to_be_visible()
    expect(page.locator("main")).not_to_contain_text("changed since cited")


def test_what_is_cited_cannot_be_removed_but_by_an_admin(logged_in: Page, deed):
    page = logged_in
    page.goto(f"/Deed/{deed.deed}/edit")
    hydrated(page)
    page.get_by_role("button", name=re.compile("Remove Provision")).first.click()
    page.get_by_role("button", name="Save", exact=True).click()
    dialog = page.locator("[data-cited-dialog]")
    expect(dialog).to_contain_text("This would remove what other documents cite as evidence")
    expect(dialog.get_by_role("button", name="Save anyway")).to_have_count(0)
    # (the one logged in is an admin, who may)
    dialog.get_by_role("button", name="Remove anyway (admin)").click()
    expect(page).to_have_url(re.compile(rf"/Deed/{deed.deed}$"))

    page.goto(f"/Gloss/{deed.gloss}")
    gone = citation(page.locator("main"), deed.granted)
    expect(gone).to_contain_text("removed since cited")
    expect(gone).to_contain_text("The mill is granted")
    expect(gone.get_by_role("link")).to_have_count(0)

    # Deleting a document that is cited: the dialog says why not
    page.goto(f"/Deed/{deed.deed}/edit")
    hydrated(page)
    page.get_by_role("button", name="Delete", exact=True).click()
    expect(page.get_by_role("dialog")).to_contain_text("cites this")
    expect(page.get_by_role("dialog").get_by_role("link", name=re.compile("Gloss on Ghent"))).to_be_visible()
