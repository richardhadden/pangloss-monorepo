"""Tasks of review that are parts of documents, in the interface (the module of `pangloss_review`): an unreconciled
mention is a chip with a spanner, reconciled in a dialog (from the item's page and from the form) or on the page of
reconciliations; an identification that a toolchain suggested is confirmed with a button; the Review page has a tab
for each kind of task and shows the tasks of one person. The e2e project's `Witness` may be left unreconciled, a
`Testimony` names witnesses (perhaps as a toolchain identified them), and a `Hearing` (reviewed) holds testimonies.
Hearings are made by `ann`, or by the admin in her name and a toolchain's."""

import re
import urllib.parse
import time
from types import SimpleNamespace

import pytest
from conftest import (
    AUTHOR_PASSWORD,
    AUTHOR_USERNAME,
    OTHER_PASSWORD,
    OTHER_USERNAME,
    TOOLCHAIN,
    USERNAME,
    Stack,
    forget,
)
from helpers import hydrated, pick
from playwright.sync_api import Page, expect


def mention(label: str, **more) -> dict:
    return {
        "type": "Unreconciled",
        "unreconciledType": "Witness",
        "label": label,
        **more,
    }


def suggested(*shares: tuple[str, int], **more) -> dict:
    """An identification by the toolchain: which witnesses it could be, each with how likely"""
    return {
        "type": "IdentificationByToolchain",
        "target": [
            {
                "type": "WeightedAlternative",
                "alternatives": [
                    {
                        "type": "Witness",
                        "id": id,
                        "edgeProperties": {"percent": percent},
                    }
                    for id, percent in shares
                ],
            }
        ],
        **more,
    }


def hearing(client, label: str, given_by=(), names=(), query: str = "") -> dict:
    """A Hearing with one testimony, as the API gives it back"""
    return client.ok(
        "POST",
        f"/api/Hearing?detail=true{query}",
        {
            "label": label,
            "testimonies": [
                {
                    "type": "Testimony",
                    "label": f"{label}: testimony",
                    "givenBy": list(given_by),
                    "names": list(names),
                }
            ],
        },
    )


@pytest.fixture
def court(types: Stack) -> SimpleNamespace:
    """Nothing of the hearings of an earlier test; clients for the project's admin (whose page the tests use), for ann,
    who makes the hearings, and for bob"""
    forget(
        "Hearing",
        "Testimony",
        "Unreconciled",
        "Witness",
        "IdentificationByToolchain",
        # (where the URIs of the parts above are found by)
        "PGUriClaim",
        # (the other documents of the review queue, which the tests of `test_review.py` leave)
        "Report",
        "ReportSection",
    )
    admin = types.admin()
    return SimpleNamespace(
        stack=types,
        admin=admin,
        ann=types.client(AUTHOR_USERNAME, AUTHOR_PASSWORD),
        bob=types.client(OTHER_USERNAME, OTHER_PASSWORD),
        witness=lambda label, **more: admin.ok(
            "POST", "/api/Witness", {"label": label, **more}
        )["id"],
    )


def until(check, seconds: float = 10.0):
    """What `check` gives once it is true (what the server does in the background)"""
    deadline = time.monotonic() + seconds
    while True:
        found = check()
        if found or time.monotonic() > deadline:
            return found
        time.sleep(0.2)


def save_form(page: Page, type: str, id: str) -> None:
    """Save the form of an item, and wait for its page"""
    page.get_by_role("banner", name="Console").get_by_role(
        "button", name="Save", exact=True
    ).click()
    page.wait_for_url(re.compile(rf"/{type}/{id}$"))


def toasts(page: Page):
    return page.get_by_role("status", name="Notifications")


def unreconciled(page: Page, label: str):
    return page.get_by_test_id("unreconciled").filter(has_text=label)


def find_witness(scope, words: str, label: str) -> None:
    scope.get_by_label("Find Witness, or + to make one").fill(words)
    scope.page.get_by_role("option", name=label).click()


def test_a_mention_is_a_chip_listed_as_outstanding_and_reconciled_in_the_form(
    logged_in: Page, court
):
    page = logged_in
    john = court.witness("John Smith (b. 1570)")
    one = hearing(
        court.ann,
        "First hearing",
        given_by=[mention("John Smith", uris=["http://example.org/john"])],
    )
    two = hearing(court.ann, "Second hearing", given_by=[mention("john  smith.")])
    three = hearing(court.ann, "Third hearing", given_by=[mention("Jon Smith")])
    page.goto(f"/Hearing/{one['id']}")
    hydrated(page)
    chip = unreconciled(page, "John Smith")
    # (its chip, "Unreconciled" and then what it would be; on a page that is read there is nothing to reconcile it by)
    expect(chip.get_by_test_id("mention-chip")).to_have_text(
        re.compile(r"^Unreconciled\s*Witness\s*John Smith")
    )
    expect(page.get_by_test_id("reconcile-button")).to_have_count(0)
    # the review flag counts it as outstanding, and the panel lists it: its chip there leads to where it is
    flag = page.get_by_role("banner", name="Console").get_by_test_id("review-button")
    expect(flag.get_by_test_id("review-count")).to_have_text("1")
    flag.click()
    outstanding = page.get_by_test_id("review-outstanding")
    expect(outstanding).to_contain_text("Outstanding unreconcileds")
    listed = outstanding.get_by_test_id("review-outstanding-mention")
    expect(listed).to_have_count(1)
    expect(listed).to_have_text(re.compile(r"^Unreconciled\s*Witness\s*John Smith"))
    listed.click()
    expect(chip).to_be_in_viewport()
    page.keyboard.press("Escape")

    # it is reconciled in the form of its document
    page.goto(f"/Hearing/{one['id']}/edit")
    hydrated(page)
    editor = page.get_by_test_id("unreconciled-editor")
    editor.get_by_role("button", name="Reconcile John Smith").click()
    dialog = page.get_by_role("dialog", name="Reconcile")
    expect(dialog.get_by_test_id("reconcile-uris")).to_contain_text(
        "http://example.org/john"
    )
    # the others like it, each where it is: the same label ticked, the near one not
    rows = dialog.get_by_test_id("reconcile-similar-row")
    expect(rows).to_have_count(2)
    same = rows.filter(has_text="Second hearing")
    near = rows.filter(has_text="Third hearing")
    expect(same).to_contain_text("john smith.")
    expect(same.get_by_role("checkbox")).to_be_checked()
    expect(near.get_by_role("checkbox")).not_to_be_checked()
    expect(near).to_contain_text("%")
    # (nothing to reconcile with yet)
    expect(dialog.get_by_test_id("reconcile-submit")).to_be_disabled()
    find_witness(dialog, "John", "John Smith (b. 1570)")
    expect(dialog.get_by_test_id("reconcile-chosen")).to_contain_text(
        "John Smith (b. 1570)"
    )
    dialog.get_by_test_id("reconcile-submit").click()
    expect(toasts(page)).to_contain_text(
        "Reconciled with John Smith (b. 1570): it is saved with the document"
    )
    expect(toasts(page)).to_contain_text("1 more are being reconciled")
    # the witness is in its place in the form, and in the document once the form is saved
    expect(page.get_by_test_id("unreconciled-editor")).to_have_count(0)
    expect(page.get_by_role("main")).to_contain_text("John Smith (b. 1570)")
    unsaved = court.admin.ok("GET", f"/api/Hearing/{one['id']}")
    assert unsaved["testimonies"][0]["givenBy"][0]["type"] == "Unreconciled"
    save_form(page, "Hearing", one["id"])
    saved = court.admin.ok("GET", f"/api/Hearing/{one['id']}")
    assert saved["testimonies"][0]["givenBy"][0]["id"] == john

    # the one that was ticked was done in the background, as an update by whoever asked; the other was left
    def second():
        read = court.admin.ok("GET", f"/api/Hearing/{two['id']}")
        return (
            read if read["testimonies"][0]["givenBy"][0]["type"] == "Witness" else None
        )

    read = until(second)
    assert read and read["meta"]["updatedBy"] == USERNAME
    left = court.admin.ok("GET", f"/api/Hearing/{three['id']}")
    assert left["testimonies"][0]["givenBy"][0]["type"] == "Unreconciled"
    # (and the witness has the mention's URI)
    assert court.admin.ok("GET", f"/api/Witness/{john}")["urls"] == [
        "http://example.org/john"
    ]


def test_someone_not_logged_in_sees_the_chip_and_nothing_to_do_with_it(page: Page, court):
    made = hearing(court.ann, "Open hearing", given_by=[mention("Mary Jones")])
    court.bob.ok("POST", f"/api/review/{made['id']}/status", {"status": "published"})
    page.goto(f"/Hearing/{made['id']}")
    hydrated(page)
    expect(unreconciled(page, "Mary Jones")).to_be_visible()
    expect(page.get_by_test_id("reconcile-button")).to_have_count(0)


def test_a_mention_is_written_in_a_form_and_reconciled_there_with_a_new_entity(
    logged_in: Page, court
):
    page = logged_in
    made = hearing(court.ann, "Hearing at Ghent")
    page.goto(f"/Hearing/{made['id']}/edit")
    hydrated(page)
    # (where a witness goes: found by searching, or left unreconciled)
    page.get_by_role("button", name="Add Unreconciled").first.click()
    editor = page.get_by_test_id("unreconciled-editor")
    editor.get_by_label("What the source calls it").fill("Anne of Ghent")
    # (one that is not saved yet has no spanner: what is reconciled is the saved document)
    expect(editor.get_by_test_id("reconcile-button")).to_have_count(0)
    # (its one button, which takes it out again, is as wide as its bar is tall)
    box = editor.get_by_role("button", name="Remove Unreconciled").bounding_box()
    assert box is not None and abs(box["width"] - box["height"]) < 1.5, box
    page.get_by_role("banner", name="Console").get_by_role(
        "button", name="Save", exact=True
    ).click()
    page.wait_for_url(re.compile(rf"/Hearing/{made['id']}$"))
    expect(unreconciled(page, "Anne of Ghent")).to_be_visible()
    expect(
        unreconciled(page, "Anne of Ghent").get_by_test_id("mention-chip")
    ).to_have_text(re.compile(r"^Unreconciled\s*Witness\s*Anne of Ghent"))
    saved = court.admin.ok("GET", f"/api/Hearing/{made['id']}")
    held = saved["testimonies"][0]["givenBy"][0]
    assert (held["type"], held["unreconciledType"]) == ("Unreconciled", "Witness")

    # in the form of the saved document it has one
    page.goto(f"/Hearing/{made['id']}/edit")
    hydrated(page)
    editor = page.get_by_test_id("unreconciled-editor")
    # (once saved it is not rewritten: its chip, "Unreconciled" and then what it would be, as on the item's page)
    expect(editor.get_by_test_id("mention-chip")).to_have_text(
        re.compile(r"^Unreconciled\s*Witness\s*Anne of Ghent")
    )
    expect(editor.get_by_role("textbox")).to_have_count(0)
    # (the two chips are one: no rounded corners where they touch, nor where the buttons follow)
    radii = editor.get_by_test_id("mention-chip").evaluate(
        """chip => [...chip.querySelectorAll('[data-type-info]')].map(part => {
            const style = getComputedStyle(part);
            return [style.borderTopLeftRadius, style.borderTopRightRadius];
        })"""
    )
    assert radii[0][1] == "0px" and radii[1] == ["0px", "0px"], radii
    expect(editor.get_by_role("button", name=re.compile("^Add"))).to_have_count(0)
    # (its two buttons are as wide as the chip is tall)
    for name in ("Reconcile Anne of Ghent", "Remove Unreconciled"):
        box = editor.get_by_role("button", name=name).bounding_box()
        assert box is not None and abs(box["width"] - box["height"]) < 1.5, (name, box)
    # someone working through the document has changed something else: the spanner opens the dialog all the same,
    # where a new witness is made
    label = page.get_by_label("Label", exact=True).first
    label.fill("Hearing at Gent")
    editor.get_by_test_id("reconcile-button").click()
    dialog = page.get_by_role("dialog", name="Reconcile")
    expect(dialog.get_by_test_id("reconcile-no-similar")).to_be_visible()
    dialog.get_by_role("button", name="Make a new one").click()
    new = page.get_by_role("dialog", name="New Witness")
    # (it starts with what the source calls them)
    expect(new.get_by_role("textbox").first).to_have_value("Anne of Ghent")
    new.get_by_role("textbox").first.fill("Anne van Gent (d. 1502)")
    new.get_by_role("button", name="Save", exact=True).click()
    expect(dialog.get_by_test_id("reconcile-chosen")).to_contain_text(
        "Anne van Gent (d. 1502)"
    )
    dialog.get_by_test_id("reconcile-submit").click()
    expect(toasts(page)).to_contain_text("Reconciled with Anne van Gent (d. 1502)")
    # (the witness is in the mention's place in the form, with what else was changed, and both are saved together)
    expect(page.get_by_test_id("unreconciled-editor")).to_have_count(0)
    expect(page.get_by_role("main")).to_contain_text("Anne van Gent (d. 1502)")
    expect(label).to_have_value("Hearing at Gent")
    save_form(page, "Hearing", made["id"])
    read = court.admin.ok("GET", f"/api/Hearing/{made['id']}")
    assert read["testimonies"][0]["givenBy"][0]["label"] == "Anne van Gent (d. 1502)"
    assert read["label"] == "Hearing at Gent"


def test_the_page_of_reconciliations_does_them_one_after_another(
    logged_in: Page, court
):
    page = logged_in
    mary = court.witness("Mary Jones (1580-1640)")
    first = hearing(court.ann, "First hearing", given_by=[mention("Mary Jones")])
    hearing(court.ann, "Second hearing", given_by=[mention("mary jones")])
    hearing(court.ann, "Third hearing", given_by=[mention("Peter Brown")])
    page.goto("/review")
    hydrated(page)
    # (the kinds of task are links in the console)
    tabs = page.get_by_role("banner", name="Console")
    expect(tabs.get_by_test_id("review-count-documents")).to_have_text("3")
    expect(tabs.get_by_test_id("review-count-reconciliations")).to_have_text("3")
    tabs.get_by_role("link", name="Reconciliations").click()
    expect(page.get_by_role("heading", name="Mentions to reconcile")).to_be_visible()
    # (the one that is shown is marked)
    expect(tabs.get_by_role("link", name="Reconciliations")).to_have_attribute(
        "aria-current", "page"
    )
    expect(tabs.get_by_role("link", name="Documents")).not_to_have_attribute(
        "aria-current", "page"
    )
    rows = page.get_by_test_id("reconciliations-row")
    expect(rows).to_have_count(3)
    # (each where it is: its chip, in the testimony's)
    expect(rows.first).to_contain_text("Mary Jones")
    expect(rows.first).to_contain_text("First hearing: testimony")
    # a search of the labels
    # (as it is typed: there is no button)
    page.get_by_test_id("reconciliations-search").fill("brown")
    expect(rows).to_have_count(1)
    expect(page).to_have_url(re.compile(r"q=brown"))
    page.get_by_test_id("reconciliations-search").fill("")
    expect(rows).to_have_count(3)

    # the table is as wide as the page: the one chosen is reconciled in a dialog over it, as anywhere
    table = page.locator("table").bounding_box()
    frame = page.get_by_role("heading", name="Mentions to reconcile").bounding_box()
    assert table is not None and frame is not None
    assert abs(table["width"] - frame["width"]) < 2, (table, frame)
    rows.filter(has_text="First hearing").get_by_test_id(
        "reconciliations-choose"
    ).click()
    panel = page.get_by_role("dialog", name="Reconcile").get_by_test_id(
        "reconcile-panel"
    )
    expect(panel.get_by_test_id("reconcile-similar-row")).to_have_count(1)
    find_witness(panel, "Mary", "Mary Jones (1580-1640)")
    panel.get_by_test_id("reconcile-submit").click()
    expect(toasts(page)).to_contain_text("Reconciled with Mary Jones (1580-1640)")
    # (the table is read again, and once more for what was done in the background)
    expect(rows).to_have_count(1, timeout=15_000)
    expect(rows.first).to_contain_text("Peter Brown")
    expect(tabs.get_by_test_id("review-count-reconciliations")).to_have_text("1")
    read = court.admin.ok("GET", f"/api/Hearing/{first['id']}")
    assert read["testimonies"][0]["givenBy"][0]["id"] == mary


def test_tasks_are_given_to_someone_and_taken_over(logged_in: Page, court):
    page = logged_in
    # (an admin's upload says who is to review it)
    mine = hearing(
        court.admin,
        "For me",
        given_by=[mention("Mine")],
        query=f"&review_assigned_to={USERNAME}&created_by={AUTHOR_USERNAME}",
    )
    hearing(
        court.admin,
        "For bob",
        given_by=[mention("Bob's")],
        query=f"&review_assigned_to={OTHER_USERNAME}&created_by={AUTHOR_USERNAME}",
    )
    hearing(court.ann, "For no one", given_by=[mention("No one's")])
    page.goto("/review")
    hydrated(page)
    rows = page.get_by_test_id("review-queue-row")
    expect(rows).to_have_count(3)
    expect(
        rows.filter(has_text="For bob").get_by_test_id("review-queue-assigned")
    ).to_contain_text(OTHER_USERNAME)
    whose = page.get_by_role("combobox", name="Tasks of")
    # (an admin may see anyone's)
    whose.click()
    expect(
        page.get_by_role("listbox", name="Tasks of").get_by_role("option")
    ).to_contain_text(["Everyone", "Me", "No one", AUTHOR_USERNAME, OTHER_USERNAME])
    whose.press("Escape")
    pick(whose, "me")
    expect(page).to_have_url(re.compile(r"assigned=me"))
    expect(rows).to_have_count(1)
    expect(rows.first).to_contain_text("For me")
    # (the kinds of task are links in the console)
    tabs = page.get_by_role("banner", name="Console")
    expect(tabs.get_by_test_id("review-count-documents")).to_have_text("1")
    # (the choice goes with the reader from tab to tab: the mentions of my documents)
    tabs.get_by_role("link", name="Reconciliations").click()
    expect(page).to_have_url(re.compile(r"/review/reconciliations\?assigned=me"))
    mentions = page.get_by_test_id("reconciliations-row")
    expect(mentions).to_have_count(1)
    expect(mentions.first).to_contain_text("Mine")
    tabs.get_by_role("link", name="Documents").click()

    # anyone may take a task, whoever has it
    pick(whose, OTHER_USERNAME)
    expect(rows).to_have_count(1)
    rows.first.get_by_test_id("review-take").click()
    expect(rows).to_have_count(0)
    pick(whose, "me")
    expect(rows).to_have_count(2)
    pick(whose, "none")
    expect(rows).to_have_count(1)
    expect(rows.first).to_contain_text("For no one")
    detail = court.admin.ok("GET", f"/api/review/{mine['id']}")
    assert (detail["assignedTo"], detail["assignedBy"]) == (USERNAME, USERNAME)


def test_what_a_toolchain_made_names_its_makers_and_its_identifications_are_confirmed(
    logged_in: Page, court
):
    page = logged_in
    john = court.witness("John Smith (b. 1570)")
    jack = court.witness("Jack Smith (b. 1575)")
    upload = (
        f"&created_by={AUTHOR_USERNAME}&toolchain={TOOLCHAIN}&toolchain_version=1.2"
        "&toolchain_date=2026-11-01"
    )
    mine = hearing(
        court.admin,
        "Uploaded hearing",
        names=[suggested((john, 70), (jack, 30))],
        query=upload,
    )
    other = hearing(
        court.admin,
        "Another upload",
        names=[suggested((john, 65), (jack, 35))],
        query=upload,
    )
    hearing(
        court.admin,
        "Not alike",
        names=[suggested((john, 20), (jack, 80))],
        query=upload,
    )
    page.goto(f"/Hearing/{mine['id']}")
    hydrated(page)
    # those who made it: the person, then the toolchain with its version; each a link to their page
    people = page.get_by_test_id("console-person")
    expect(people).to_have_count(2)
    expect(people.nth(0)).to_contain_text(AUTHOR_USERNAME)
    expect(people.nth(1)).to_contain_text(f"{TOOLCHAIN} 1.2")
    expect(people.nth(1)).to_have_attribute("data-kind", "toolchain")
    expect(people.nth(1).get_by_role("link")).to_have_attribute(
        "href", f"/users/{TOOLCHAIN}"
    )

    main = page.get_by_role("main")
    expect(main).to_contain_text("John Smith (b. 1570)")
    expect(main).to_contain_text(TOOLCHAIN)
    # (nothing is confirmed from a page that is read; the review flag counts what is to be confirmed)
    expect(page.get_by_test_id("confirm-button")).to_have_count(0)
    expect(page.get_by_test_id("review-button").get_by_test_id("review-count")).to_have_text("1")
    page.goto(f"/Hearing/{mine['id']}/edit")
    hydrated(page)
    page.get_by_test_id("confirm-button").click()
    dialog = page.get_by_role("dialog", name="Confirm an identification")
    expect(dialog.get_by_test_id("confirm-panel")).to_contain_text(
        f"Suggested by {TOOLCHAIN} 1.2"
    )
    # (the others that say the same: the one about as likely, not the one that says otherwise)
    rows = dialog.get_by_test_id("confirm-similar-row")
    expect(rows).to_have_count(1)
    expect(rows.first).to_contain_text("Another upload: testimony")
    expect(rows.first).to_contain_text("65%")
    rows.first.get_by_role("checkbox").check()
    dialog.get_by_test_id("confirm-submit").click()
    expect(toasts(page)).to_contain_text("Confirmed: it is saved with the document")
    expect(toasts(page)).to_contain_text("1 more are being given the same")
    # it is an identification in the form now, with nothing to confirm, and is the reader's once the form is saved
    expect(page.get_by_test_id("confirm-button")).to_have_count(0)
    unsaved = court.admin.ok("GET", f"/api/Hearing/{mine['id']}")
    assert unsaved["testimonies"][0]["names"][0]["type"] == "IdentificationByToolchain"
    save_form(page, "Hearing", mine["id"])
    read = court.admin.ok("GET", f"/api/Hearing/{mine['id']}")
    held = read["testimonies"][0]["names"][0]
    assert (held["type"], held["identifiedBy"]) == ("Identification", USERNAME)

    def others():
        read = court.admin.ok("GET", f"/api/Hearing/{other['id']}")
        held = read["testimonies"][0]["names"][0]
        return held if held["type"] == "Identification" else None

    done = until(others)
    assert done and done["identifiedBy"] == USERNAME
    # (given what was confirmed: the same candidates, as likely as there)
    assert [
        a["edgeProperties"]["percent"] for a in done["target"][0]["alternatives"]
    ] == [70, 30]

    # the one left is on the page of identifications
    page.goto("/review/identifications")
    hydrated(page)
    expect(
        page.get_by_role("heading", name="Identifications to confirm")
    ).to_be_visible()
    rows = page.get_by_test_id("identifications-row")
    expect(rows).to_have_count(1)
    expect(rows.first).to_contain_text("Not alike: testimony")
    expect(rows.first).to_contain_text(f"{TOOLCHAIN} 1.2")
    expect(rows.first.get_by_test_id("suggestion-candidates")).to_contain_text("80%")
    # nothing is confirmed from the table, unseen: a row leads to the form of its document, at the suggestion
    expect(rows.first.get_by_test_id("confirm-button")).to_have_count(0)
    rows.first.get_by_role("link", name="Check it in the form").click()
    page.wait_for_url(re.compile(r"/Hearing/[^/]+/edit\?show="))
    hydrated(page)
    shown = urllib.parse.parse_qs(urllib.parse.urlparse(page.url).query)["show"][0]
    block = page.locator(f'[data-item-id="{shown}"]')
    expect(block).to_be_in_viewport()

    def shown_head(page: Page) -> str:
        return urllib.parse.urlparse(page.url).path.split("/")[2]

    expect(block).to_contain_text("Identification by toolchain")
    # (nothing to ask there: no other says the same, and it gives no URIs to anyone, so it is confirmed at once)
    block.get_by_test_id("confirm-button").click()
    expect(toasts(page)).to_contain_text("Confirmed")
    expect(page.get_by_role("dialog")).to_have_count(0)
    expect(page.get_by_test_id("confirm-button")).to_have_count(0)
    expect(block).to_contain_text("Identification")
    expect(block).not_to_contain_text("Identification by toolchain")
    save_form(page, "Hearing", shown_head(page))
    assert court.admin.ok("GET", "/api/review/identifications")["count"] == 0


def test_a_projects_own_kind_of_suggestion_is_confirmed_as_the_class_it_names(
    logged_in: Page, court
):
    """(`SuggestedReading`, a subclass of `IdentificationByToolchain`, which becomes a `Reading`)"""
    page = logged_in
    john = court.witness("John Smith (b. 1570)")
    mary = court.witness("Mary Jones")
    made = hearing(
        court.admin,
        "Read by machine",
        names=[
            {
                **suggested((john, 60), (mary, 40)),
                "type": "SuggestedReading",
                "note": "the hand is unclear",
            }
        ],
        query=f"&created_by={AUTHOR_USERNAME}&toolchain={TOOLCHAIN}",
    )
    listed = court.admin.ok("GET", "/api/review/identifications")
    assert [each["type"] for each in listed["results"]] == ["SuggestedReading"]
    page.goto(f"/Hearing/{made['id']}/edit")
    hydrated(page)
    # (it has the button as the library's own class does)
    page.get_by_test_id("confirm-button").click()
    expect(toasts(page)).to_contain_text("Confirmed")
    expect(page.get_by_test_id("confirm-button")).to_have_count(0)
    save_form(page, "Hearing", made["id"])
    read = court.admin.ok("GET", f"/api/Hearing/{made['id']}")
    held = read["testimonies"][0]["names"][0]
    assert (held["type"], held["identifiedBy"], held["note"]) == (
        "Reading",
        USERNAME,
        "the hand is unclear",
    )


def test_an_identification_is_confirmed_in_a_form_that_has_other_changes(
    logged_in: Page, court
):
    page = logged_in
    john = court.witness("John Smith (b. 1570)")
    made = hearing(
        court.admin,
        "Uploaded hearing",
        names=[suggested((john, 100), uris=["http://example.org/john-confirmed"])],
        query=f"&created_by={AUTHOR_USERNAME}&toolchain={TOOLCHAIN}",
    )
    page.goto(f"/Hearing/{made['id']}/edit")
    hydrated(page)
    confirm = page.get_by_test_id("confirm-button")
    expect(confirm).to_be_visible()
    # (a yellow button that says what it does, first in the identification's bar after its type: as tall as the
    # bar, and at the other end from the buttons that cut, copy and remove it)
    expect(confirm).to_have_text("Confirm identification")
    expect(confirm).to_have_class(re.compile("bg-yellow-300"))
    block = page.locator("[data-item-id]").filter(has=confirm).last
    remove = block.get_by_role("button", name="Remove Identification by toolchain").first
    box, far = confirm.bounding_box(), remove.bounding_box()
    assert box is not None and far is not None
    assert abs(box["y"] - far["y"]) <= 2 and abs(box["height"] - far["height"]) <= 2
    assert far["x"] - (box["x"] + box["width"]) > 200, (box, far)
    # (its URIs are the toolchain's: shown in its form, as links, and not to be changed)
    shown = block.get_by_test_id("suggestion-uris")
    expect(shown.get_by_role("link")).to_have_text("http://example.org/john-confirmed")
    expect(block.get_by_role("textbox", name=re.compile("URI", re.I))).to_have_count(0)
    # someone working through the document has changed something else: it is confirmed all the same, as one more
    # change of the form
    page.get_by_role("textbox").first.fill("Uploaded hearing, read")
    confirm.click()
    dialog = page.get_by_role("dialog", name="Confirm an identification")
    # (one candidate, and URIs, which would go to them: asked about first, with who it is and the URIs)
    warning = dialog.get_by_test_id("confirm-uris-warning")
    expect(warning).to_contain_text("Confirming gives these URIs to this one")
    expect(warning).to_contain_text("John Smith (b. 1570)")
    expect(warning.get_by_test_id("confirm-uris")).to_have_text(
        "http://example.org/john-confirmed"
    )
    assert court.admin.ok("GET", f"/api/Witness/{john}")["urls"] == []
    dialog.get_by_test_id("confirm-submit").click()
    expect(toasts(page)).to_contain_text("Confirmed: it is saved with the document")
    expect(page.get_by_test_id("confirm-button")).to_have_count(0)
    # (what was typed is still there, and nothing is done to the saved document or to John until the form is saved)
    expect(page.get_by_role("textbox").first).to_have_value("Uploaded hearing, read")
    assert court.admin.ok("GET", f"/api/Witness/{john}")["urls"] == []
    assert court.admin.ok("GET", "/api/review/identifications")["count"] == 1
    save_form(page, "Hearing", made["id"])
    # (the URIs are given once the save is made, after it)
    assert until(
        lambda: court.admin.ok("GET", f"/api/Witness/{john}")["urls"]
    ) == ["http://example.org/john-confirmed"]
    read = court.admin.ok("GET", f"/api/Hearing/{made['id']}")
    held = read["testimonies"][0]["names"][0]
    assert (held["type"], held["identifiedBy"]) == ("Identification", USERNAME)
    assert read["label"] == "Uploaded hearing, read"


def test_an_identification_confirmed_with_several_candidates_keeps_the_uris(
    logged_in: Page, court
):
    """The URIs are for whoever it is: while that is one of several, nobody is given them, and the identification
    that the suggestion becomes keeps them (shown, not to be changed) until it is of one"""
    page = logged_in
    uri = "http://example.org/one-of-two"
    john = court.witness("John Smith (b. 1570)")
    jack = court.witness("Jack Smith")
    made = hearing(
        court.admin,
        "Hearing of two Smiths",
        names=[suggested((john, 60), (jack, 40), uris=[uri])],
        query=f"&created_by={AUTHOR_USERNAME}&toolchain={TOOLCHAIN}",
    )
    page.goto(f"/Hearing/{made['id']}/edit")
    hydrated(page)
    page.get_by_test_id("confirm-button").click()
    expect(toasts(page)).to_contain_text("Confirmed: it is saved with the document")
    expect(page.get_by_test_id("confirm-button")).to_have_count(0)
    # (the identification it is now, in the form: with the URIs still)
    expect(page.get_by_test_id("suggestion-uris").get_by_role("link")).to_have_text(uri)
    save_form(page, "Hearing", made["id"])
    held = court.admin.ok("GET", f"/api/Hearing/{made['id']}")["testimonies"][0]["names"][0]
    assert (held["type"], held["identifiedBy"], held["uris"]) == (
        "Identification",
        USERNAME,
        [uri],
    )
    assert court.admin.ok("GET", f"/api/Witness/{john}")["urls"] == []
    assert court.admin.ok("GET", f"/api/Witness/{jack}")["urls"] == []
    # (and when the form is opened again)
    page.goto(f"/Hearing/{made['id']}/edit")
    hydrated(page)
    expect(page.get_by_test_id("suggestion-uris").get_by_role("link")).to_have_text(uri)
    expect(page.get_by_role("textbox", name=re.compile("URI", re.I))).to_have_count(0)


def test_parts_that_name_one_uri_are_done_with_the_one_that_is_confirmed(
    logged_in: Page, court
):
    """A URI in common says they are of the same person: offered first and ticked, whoever their candidates are; those
    of this document are changed in the form with it, those of other documents by the server"""
    page = logged_in
    uri = "http://example.org/same-person/confirmed"
    john = court.witness("John Smith (b. 1570)")
    jack = court.witness("Jack Smith (b. 1575)")
    upload = f"&created_by={AUTHOR_USERNAME}&toolchain={TOOLCHAIN}"
    mine = hearing(
        court.admin,
        "First upload",
        given_by=[mention("Iohannes Faber", uris=[uri])],
        names=[suggested((john, 100), uris=[uri]), suggested((jack, 100), uris=[uri])],
        query=upload,
    )
    other = hearing(
        court.admin,
        "Second upload",
        given_by=[mention("J. Smith", uris=[uri])],
        names=[suggested((jack, 60), (john, 40), uris=[uri])],
        query=upload,
    )
    page.goto(f"/Hearing/{mine['id']}/edit")
    hydrated(page)
    expect(page.get_by_test_id("confirm-button")).to_have_count(2)
    first = mine["testimonies"][0]["names"][0]["id"]
    page.locator(f'[data-item-id="{first}"]').get_by_test_id("confirm-button").click()
    dialog = page.get_by_role("dialog", name="Confirm an identification")
    # the suggestions of the same URI, ticked, though each says someone else: one in this document, one in another
    rows = dialog.get_by_test_id("confirm-similar-row")
    expect(rows).to_have_count(2)
    expect(rows.get_by_test_id("same-uri")).to_have_count(2)
    expect(rows.get_by_test_id("in-this-document")).to_have_count(1)
    for index in range(2):
        expect(rows.nth(index).get_by_role("checkbox")).to_be_checked()
    # and the mentions of it, to be reconciled with the one candidate
    mentions = dialog.get_by_test_id("confirm-mentions-row")
    expect(mentions).to_have_count(2)
    expect(dialog.get_by_test_id("confirm-panel")).to_contain_text(
        "Those ticked are reconciled with John Smith (b. 1570)"
    )
    for index in range(2):
        expect(mentions.nth(index).get_by_role("checkbox")).to_be_checked()
    dialog.get_by_test_id("confirm-submit").click()
    expect(toasts(page)).to_contain_text("2 more in this document are done with it")
    expect(toasts(page)).to_contain_text("2 more are being given the same")
    # in the form: nothing left to confirm or to reconcile, and nothing of this document written yet
    expect(page.get_by_test_id("confirm-button")).to_have_count(0)
    expect(page.get_by_test_id("unreconciled-editor")).to_have_count(0)
    unsaved = court.admin.ok("GET", f"/api/Hearing/{mine['id']}")
    assert unsaved["meta"]["version"] == 1
    save_form(page, "Hearing", mine["id"])
    read = court.admin.ok("GET", f"/api/Hearing/{mine['id']}")["testimonies"][0]
    assert read["givenBy"][0]["id"] == john
    for held in read["names"]:
        assert (held["type"], held["identifiedBy"]) == ("Identification", USERNAME)
        assert [a["id"] for a in held["target"][0]["alternatives"]] == [john]

    # the other document, by the server
    def done():
        there = court.admin.ok("GET", f"/api/Hearing/{other['id']}")["testimonies"][0]
        ready = (
            there["givenBy"][0]["type"] == "Witness"
            and there["names"][0]["type"] == "Identification"
        )
        return there if ready else None

    there = until(done)
    assert there and there["givenBy"][0]["id"] == john
    assert [a["id"] for a in there["names"][0]["target"][0]["alternatives"]] == [john]
    assert until(lambda: court.admin.ok("GET", f"/api/Witness/{john}")["urls"]) == [uri]


def test_a_mention_is_reconciled_with_who_has_its_uri_and_the_suggestions_of_it(
    logged_in: Page, court
):
    page = logged_in
    uri = "http://example.org/same-person/reconciled"
    anne = court.witness("Anne van Gent (d. 1502)", urls=[uri])
    other = court.witness("Agnes of Bruges")
    mine = hearing(
        court.admin,
        "Hearing at Ghent",
        given_by=[mention("Anna", uris=[uri]), mention("Annekin", uris=[uri])],
        names=[suggested((other, 100), uris=[uri])],
        query=f"&created_by={AUTHOR_USERNAME}&toolchain={TOOLCHAIN}",
    )
    page.goto(f"/Hearing/{mine['id']}/edit")
    hydrated(page)
    page.get_by_role("button", name="Reconcile Anna", exact=True).click()
    dialog = page.get_by_role("dialog", name="Reconcile")
    # who has the URI already is put forward
    chosen = dialog.get_by_test_id("reconcile-chosen")
    expect(chosen).to_contain_text("Anne van Gent (d. 1502)")
    expect(chosen.get_by_test_id("reconcile-known")).to_have_text("has this URI already")
    # the other mention of the URI, unlike in its label, and the suggestion of it: in this document, ticked
    similar = dialog.get_by_test_id("reconcile-similar-row")
    expect(similar).to_have_count(1)
    expect(similar.get_by_test_id("same-uri")).to_be_visible()
    expect(similar.get_by_role("checkbox")).to_be_checked()
    suggestions = dialog.get_by_test_id("reconcile-suggestions-row")
    expect(suggestions).to_have_count(1)
    expect(suggestions.get_by_test_id("in-this-document")).to_be_visible()
    expect(suggestions.get_by_role("checkbox")).to_be_checked()
    dialog.get_by_test_id("reconcile-submit").click()
    expect(toasts(page)).to_contain_text("2 more in this document are done with it")
    expect(page.get_by_test_id("unreconciled-editor")).to_have_count(0)
    expect(page.get_by_test_id("confirm-button")).to_have_count(0)
    save_form(page, "Hearing", mine["id"])
    read = court.admin.ok("GET", f"/api/Hearing/{mine['id']}")["testimonies"][0]
    assert [held["id"] for held in read["givenBy"]] == [anne, anne]
    held = read["names"][0]
    assert (held["type"], held["identifiedBy"]) == ("Identification", USERNAME)
    # (confirmed as her and no other, though the toolchain said someone else)
    assert [
        (a["id"], a["edgeProperties"]["percent"]) for a in held["target"][0]["alternatives"]
    ] == [(anne, 100)]


def test_an_admin_makes_a_toolchain_which_is_listed_as_one(logged_in: Page, court):
    page = logged_in
    forget_toolchain = "second-chain"
    page.goto("/admin")
    hydrated(page)
    section = page.get_by_test_id("admin-users")
    existing = section.get_by_test_id("users-admin-row").filter(has_text=TOOLCHAIN)
    expect(existing).to_have_attribute("data-kind", "toolchain")
    expect(existing).to_contain_text("Toolchain")
    # (it cannot log in: nothing to do with passwords, sessions or tokens)
    expect(existing.get_by_role("button", name="Password")).to_have_count(0)
    section.get_by_test_id("users-admin-new-toolchain").click()
    dialog = page.get_by_role("dialog", name="New toolchain")
    dialog.get_by_label("Name", exact=True).fill(forget_toolchain)
    dialog.get_by_label("Full name").fill("A second toolchain")
    dialog.get_by_role("button", name="Create").click()
    made = section.get_by_test_id("users-admin-row").filter(has_text=forget_toolchain)
    expect(made).to_have_attribute("data-kind", "toolchain")
    page.goto("/users")
    hydrated(page)
    expect(
        page.get_by_test_id("users-row")
        .filter(has_text=forget_toolchain)
        .get_by_test_id("users-toolchain")
    ).to_be_visible()
