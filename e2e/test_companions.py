"""Companion documents (implementation_docs/companion-documents.md): the dialog that makes a noble from a charter's form
offers a charter of its own, of the same archive, saying what the noble is called; made with the noble if it is
filled in, in one request, and not if it is not"""

import re

from helpers import hydrated
from playwright.sync_api import Page, expect


def charters(data) -> list[dict]:
    return data.api.ok("GET", "/api/Charter")["results"]


def open_dialog(page: Page, archive: str):
    page.goto("/Charter/new")
    hydrated(page)
    page.get_by_label("Archive", exact=True).fill(archive)
    page.get_by_role("button", name="Make a new one").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    return dialog


def test_a_noble_made_in_a_charter_is_made_with_a_charter_of_its_naming(logged_in: Page, data):
    page = logged_in
    before = len(charters(data))
    dialog = open_dialog(page, "Durham")
    companion = dialog.locator('[data-companion="naming"]')
    expect(companion).to_be_visible()
    # (the archive of the charter behind, and the new noble in the clause, as its name is typed)
    expect(companion.get_by_label("Archive", exact=True)).to_have_value("Durham")
    dialog.get_by_label("Label", exact=True).first.fill("Ralph Neville")
    expect(companion).to_contain_text("Ralph Neville")
    companion.get_by_label("First name", exact=True).fill("Ralph")
    expect(companion.get_by_label("Label", exact=True).nth(1)).to_have_value("Ralph Neville is called Ralph")
    dialog.get_by_role("button", name="Save").click()
    expect(dialog).to_be_hidden()

    # (the noble is chosen in the charter behind; the companion is a charter of its own)
    expect(page.get_by_text("Ralph Neville", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name=re.compile("Dismiss: Noble “Ralph Neville” created, with Charter"))).to_be_visible()
    made = [c for c in charters(data) if c["label"] == "Durham: Ralph Neville is called Ralph"]
    assert len(made) == 1
    assert len(charters(data)) == before + 1
    stored = data.api.ok("GET", f"/api/Charter/{made[0]['id']}")
    noble = stored["clauses"][0]["named"]
    assert noble["label"] == "Ralph Neville"
    assert data.api.ok("GET", f"/api/Noble/{noble['id']}")["label"] == "Ralph Neville"


def test_a_noble_with_nothing_filled_in_under_it_is_made_alone(logged_in: Page, data):
    page = logged_in
    before = len(charters(data))
    dialog = open_dialog(page, "York")
    dialog.get_by_label("Label", exact=True).first.fill("Joan Beaufort")
    dialog.get_by_role("button", name="Save").click()
    expect(dialog).to_be_hidden()
    expect(page.get_by_text("Joan Beaufort", exact=True)).to_be_visible()
    assert len(charters(data)) == before


def test_the_page_of_a_new_noble_offers_its_charter_with_the_archive_to_be_given(logged_in: Page, data):
    page = logged_in
    page.goto("/Noble/new")
    hydrated(page)
    companion = page.locator('[data-companion="naming"]')
    expect(companion).to_be_visible()
    expect(companion.get_by_label("Archive", exact=True)).to_have_value("")
    page.get_by_label("Label", exact=True).first.fill("Cecily Neville")
    companion.get_by_label("First name", exact=True).fill("Cecily")
    companion.get_by_label("Archive", exact=True).fill("Raby")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_role("heading", name="Cecily Neville")).to_be_visible()
    assert [c["label"] for c in charters(data) if c["label"].startswith("Raby")] == ["Raby: Cecily Neville is called Cecily"]
