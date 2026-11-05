"""Changing the type of a document inside another (↧ narrow, ↥ widen), in the built interface against the API.

A narrowing is offered only where nothing filled in would be lost: a type below that has no room for what is chosen (a
creation of a painting, where the object is an artwork) is in the menu, greyed, saying what it would lose, and cannot be
chosen. A widening that would lose something asks first. Each is saved as the same node with its new type. The logic is
tested in Vitest (`retype.test.ts`, `Retype.test.tsx`, `TypeMenu.test.tsx`); this is the form, the save and the API.
"""

import re

from helpers import hydrated
from playwright.sync_api import Page, expect


def type_of(page: Page, step: str):
    """The type chip at the head of a document in the form"""
    return page.locator(f"[data-item-id='{step}'] [data-tint]").first


def narrow(page: Page):
    return page.get_by_role("button", name="Narrow Making it to a type below it")


def widen(page: Page):
    return page.get_by_role("button", name="Widen Making it to a type above it")


def edit(page: Page, id: str) -> None:
    page.goto(f"/Provenance/{id}/edit")
    hydrated(page)


def test_a_narrowing_that_would_lose_the_object_cannot_be_chosen_and_says_why(
    logged_in: Page, provenance
):
    page = logged_in
    edit(page, provenance.of_artwork)
    expect(type_of(page, provenance.artwork_step)).to_have_text(
        "Creation of physical object"
    )
    narrow(page).click()
    menu = page.get_by_role("menu")
    expect(menu.get_by_role("menuitem")).to_have_count(2)
    # (an artwork is not a painting: the creation of a painting is there, greyed, with why)
    unavailable = menu.locator("[data-unavailable]")
    expect(unavailable).to_have_count(1)
    expect(unavailable).to_have_attribute("aria-disabled", "true")
    expect(unavailable).to_contain_text("Creation of painting")
    expect(unavailable.locator("[data-reason]")).to_have_text(
        "Would lose: Object created"
    )
    # (Playwright will not click what says it is disabled: a person can, and)
    unavailable.click(force=True)
    # (nothing happens: the menu is still open, the type is as it was, no dialog)
    expect(menu).to_be_visible()
    expect(page.get_by_role("dialog")).to_have_count(0)
    expect(type_of(page, provenance.artwork_step)).to_have_text(
        "Creation of physical object"
    )
    # (the one that loses nothing is chosen at once, without a question)
    menu.get_by_role("menuitem", name="Creation of artwork").click()
    expect(page.get_by_role("dialog")).to_have_count(0)
    expect(type_of(page, provenance.artwork_step)).to_have_text("Creation of artwork")
    step = page.locator(f"[data-item-id='{provenance.artwork_step}']")
    expect(step.get_by_text("The thing", exact=True)).to_be_visible()
    # (below it now only the creation of a painting, which cannot be chosen: still a menu, saying why)
    narrow(page).click()
    expect(page.get_by_role("menu").locator("[data-reason]")).to_have_text(
        "Would lose: Artwork created"
    )
    page.keyboard.press("Escape")
    page.get_by_role("button", name="Save").click()
    page.wait_for_url(f"**/Provenance/{provenance.of_artwork}")
    saved = provenance.api.ok("GET", f"/api/Provenance/{provenance.of_artwork}")
    # (the same node, of its new type, with the artwork in the field that stands for the object)
    [kept] = saved["steps"]
    assert kept["type"] == "CreationOfArtwork"
    assert kept["id"] == provenance.artwork_step
    assert kept["artworkCreated"]["id"] == provenance.artwork


def test_a_painting_narrows_all_the_way_and_widening_back_asks_before_it_loses_a_field(
    logged_in: Page, provenance
):
    page = logged_in
    edit(page, provenance.of_painting)
    narrow(page).click()
    menu = page.get_by_role("menu")
    # (a painting can be the object of either: both can be chosen)
    expect(menu.locator("[data-unavailable]")).to_have_count(0)
    menu.get_by_role("menuitem", name="Creation of painting").click()
    expect(page.get_by_role("dialog")).to_have_count(0)
    expect(type_of(page, provenance.painting_step)).to_have_text("Creation of painting")
    # (the narrowest: nothing below it)
    expect(narrow(page)).to_have_count(0)
    step = page.locator(f"[data-item-id='{provenance.painting_step}']")
    step.get_by_label("Medium", exact=True).fill("Oil")
    page.get_by_role("button", name="Save").click()
    page.wait_for_url(f"**/Provenance/{provenance.of_painting}")
    [kept] = provenance.api.ok("GET", f"/api/Provenance/{provenance.of_painting}")[
        "steps"
    ]
    assert (
        kept["type"],
        kept["id"],
        kept["paintingCreated"]["id"],
        kept["medium"],
    ) == (
        "CreationOfPainting",
        provenance.painting_step,
        provenance.painting,
        "Oil",
    )

    # (widened back to the broadest, the medium would be lost: a dialog says so first)
    edit(page, provenance.of_painting)
    widen(page).click()
    page.get_by_role("menu").get_by_role(
        "menuitem", name="Creation of physical object"
    ).click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_contain_text("Change to Creation of physical object?")
    expect(dialog.locator("[data-lost] li")).to_have_text(["Medium"])
    dialog.get_by_role("button", name="Change the type").click()
    expect(type_of(page, provenance.painting_step)).to_have_text(
        "Creation of physical object"
    )
    page.get_by_role("button", name="Save").click()
    page.wait_for_url(f"**/Provenance/{provenance.of_painting}")
    [kept] = provenance.api.ok("GET", f"/api/Provenance/{provenance.of_painting}")[
        "steps"
    ]
    assert (kept["type"], kept["id"], kept["objectCreated"]["id"]) == (
        "CreationOfPhysicalObject",
        provenance.painting_step,
        provenance.painting,
    )
    assert "medium" not in kept


def test_the_subject_of_a_provenance_is_given_to_a_step_of_a_narrower_type_in_its_own_field(
    logged_in: Page, provenance
):
    """`Provenance.subject` is bound into `object_created` of each step: a creation of a painting has it as the
    painting created. Given in the form as it is chosen, and on the server, which is what is saved"""
    page = logged_in
    page.goto("/Provenance/new")
    hydrated(page)
    page.get_by_label("Label", exact=True).fill("Where the portrait came from")
    finder = page.locator("form").get_by_role("combobox").first
    finder.fill("portrait")
    page.get_by_role("option", name=re.compile("The portrait")).click()
    page.get_by_role("button", name="Add Steps").click()
    page.get_by_role("button", name="Creation of painting", exact=True).click()
    # (in the form at once: the painting created is the subject, a chip in the step as in the subject)
    expect(
        page.get_by_role("button", name="Remove The portrait", exact=True)
    ).to_have_count(2)
    expect(page.get_by_role("term").filter(has_text="Painting created")).to_be_visible()
    expect(page.get_by_role("term").filter(has_text="Object created")).to_have_count(0)
    page.get_by_label("Label", exact=True).last.fill("Painted")
    page.get_by_role("button", name="Save").click()
    page.wait_for_url(re.compile(r"/Provenance/[0-9a-f-]+$"))
    id = page.url.rsplit("/", 1)[1]
    [kept] = provenance.api.ok("GET", f"/api/Provenance/{id}")["steps"]
    assert (kept["type"], kept["paintingCreated"]["id"]) == (
        "CreationOfPainting",
        provenance.painting,
    )


def test_the_server_gives_the_subject_to_a_step_of_a_narrower_type(provenance):
    """Sent without the field (as a script would): the binding fills the painting created; and refuses an artwork
    there, which is not a painting"""
    id = provenance.api.ok(
        "POST",
        "/api/Provenance",
        {
            "label": "Sent",
            "subject": {"type": "Painting", "id": provenance.painting},
            "steps": [{"type": "CreationOfPainting", "label": "Painted"}],
        },
    )["id"]
    [kept] = provenance.api.ok("GET", f"/api/Provenance/{id}")["steps"]
    assert kept["paintingCreated"]["id"] == provenance.painting
    status, result = provenance.api.send(
        "POST",
        "/api/Provenance",
        {
            "label": "Sent",
            "subject": {"type": "Artwork", "id": provenance.artwork},
            "steps": [{"type": "CreationOfPainting", "label": "Painted"}],
        },
    )
    assert status == 422, result
    assert "painting_created" in str(result) or "paintingCreated" in str(result)


NOT_HELD = (
    "The thing is given to this from above, but cannot go here: choose one that can"
)


def test_a_step_that_cannot_hold_the_subject_says_so_at_its_field(
    logged_in: Page, provenance
):
    """The subject is an artwork, which a creation of a painting cannot have as its painting created: the field is
    left empty, and says why, until a painting is chosen there"""
    page = logged_in
    page.goto("/Provenance/new")
    hydrated(page)
    page.get_by_label("Label", exact=True).fill("Where the thing came from")
    page.locator("form").get_by_role("combobox").first.fill("thing")
    page.get_by_role("option", name=re.compile("The thing")).click()
    page.get_by_role("button", name="Add Steps").click()
    page.get_by_role("button", name="Creation of painting", exact=True).click()
    expect(page.get_by_text(NOT_HELD)).to_be_visible()
    # (the subject is not put there)
    expect(
        page.get_by_role("button", name="Remove The thing", exact=True)
    ).to_have_count(1)
    # (a painting chosen by hand: nothing to say)
    # (typed as a person does: a finder just drawn may miss a value set all at once)
    finder = page.get_by_label("Find Painting…", exact=True)
    finder.click()
    finder.press_sequentially("portrait")
    page.get_by_role("option", name=re.compile("The portrait")).click()
    expect(page.get_by_text(NOT_HELD)).to_have_count(0)
    # (a creation of an artwork can have it: given, nothing said)
    page.get_by_role("button", name="Add Steps").click()
    page.get_by_role("button", name="Creation of artwork", exact=True).click()
    expect(
        page.get_by_role("button", name="Remove The thing", exact=True)
    ).to_have_count(2)
    expect(page.get_by_text(NOT_HELD)).to_have_count(0)
