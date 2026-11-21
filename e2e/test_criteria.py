"""Descriptions in the interface (the module of `pangloss_criteria`): someone a source describes and does not name, in
the form of a `Sighting` ("+ Matches criteria" opens a dialog with the search form of a person and what it finds), and
on the sighting's page, where the card follows the worker until it has found the candidates, and "This is…" puts one
of them in its place; on a candidate's page, the sighting is marked "identified as candidate". The people are those of
the `data` fixture: Marie has an advisor's role, Maximilian a secretary's, Charles none. (The e2e project links at most
8 candidates: `CRITERIA_MAX_CANDIDATES`)"""

import re
import time
from contextlib import contextmanager

import neo4j
import pytest
from conftest import MEMGRAPH_AUTH, MEMGRAPH_URI, forget
from helpers import add_filter, hydrated, outside_similar
from playwright.sync_api import Page, expect


@pytest.fixture
def people(data):
    """The people, and no sighting or description of an earlier test"""
    forget("Sighting", "MatchesCriteria")
    return data


def dialog(page: Page):
    return page.get_by_test_id("criteria-dialog")


def test_a_description_is_written_in_a_dialog_shown_with_its_candidates_and_opened_again(
    logged_in: Page, people
):
    page = logged_in
    page.goto("/Sighting/new")
    hydrated(page)
    page.get_by_label("Label", exact=True).fill("Seen at Ghent")
    page.get_by_label("Place", exact=True).fill("Ghent")

    # (the field takes a person, or a description of one: its button opens the dialog at once, with the search form
    # of a person, the only class it can be of. The second such button is the field `company`'s)
    page.get_by_role("button", name="Add Matches criteria").first.click()
    expect(dialog(page)).to_be_visible()
    expect(dialog(page).get_by_test_id("criteria-need-condition")).to_be_visible()
    expect(dialog(page).get_by_role("button", name="Done")).to_be_disabled()
    dialog(page).get_by_label("What the source says").fill("N. N., an advisor")
    add_filter(dialog(page), "has role")
    dialog(page).get_by_role("combobox", name=re.compile("^Find Role")).fill("advisor")
    page.get_by_role("option", name=re.compile("Marie's advisor")).click()

    # (what the criteria find, a moment after the change)
    result = dialog(page).get_by_test_id("criteria-result")
    expect(result.get_by_test_id("criteria-count")).to_have_text("1 candidate found")
    expect(result.get_by_test_id("criteria-candidates").get_by_role("link")).to_have_text(
        [re.compile("Marie of Burgundy")]
    )
    expect(result.get_by_test_id("criteria-summary")).to_contain_text(re.compile("has role: Role ?Marie's advisor", re.I))
    dialog(page).get_by_role("button", name="Done").click()
    expect(dialog(page)).to_be_hidden()

    # (closed: the summary, with the role as a chip, the wording, and the preview, not saved yet)
    card = page.get_by_test_id("criteria-editor")
    expect(card.get_by_test_id("criteria-summary")).to_contain_text("Marie's advisor")
    expect(card.get_by_test_id("criteria-wording")).to_have_text("“N. N., an advisor”")
    expect(card.get_by_test_id("criteria-count")).to_have_text("1 candidate found · not saved yet")

    with page.expect_response(
        lambda response: response.request.method == "POST" and response.url.endswith("/api/Sighting")
    ) as answer:
        page.get_by_role("banner", name="Console").get_by_role("button", name="Save", exact=True).click()
    assert answer.value.ok, answer.value.text()
    sighting = answer.value.json()["id"]
    page.wait_for_url(re.compile(rf"/Sighting/{sighting}$"))

    # (on its page: the worker finds the candidates after the save, and the card shows them when it has, without a
    # reload; it may have been quick enough for the page to be read with them)
    shown = page.get_by_test_id("criteria-card")
    expect(shown.get_by_test_id("criteria-summary")).to_contain_text("Marie's advisor")
    expect(shown.get_by_test_id("criteria-wording")).to_have_text("“N. N., an advisor”")
    expect(shown.get_by_test_id("criteria-candidates").get_by_role("link")).to_have_text(
        [re.compile("Marie of Burgundy")], timeout=20_000
    )
    expect(shown.get_by_test_id("criteria-count")).to_have_text(re.compile(r"^1 candidate · updated "))
    expect(shown.get_by_test_id("criteria-finding")).to_have_count(0)

    # (edited again: the pencil opens the dialog with the condition, and the role by its label)
    page.goto(f"/Sighting/{sighting}/edit")
    hydrated(page)
    editor = page.get_by_test_id("criteria-editor")
    expect(editor.get_by_test_id("criteria-count")).to_have_text("1 candidate found")
    editor.get_by_role("button", name="Edit the criteria").click()
    expect(dialog(page)).to_be_visible()
    expect(dialog(page).get_by_label("What the source says")).to_have_value("N. N., an advisor")
    criteria = dialog(page).get_by_role("region", name="Criteria")
    expect(criteria.locator("dt:not(.sr-only)")).to_have_text([re.compile("has role", re.I)])
    expect(criteria.get_by_role("button", name="Remove Marie's advisor")).to_be_visible()
    expect(dialog(page).get_by_test_id("criteria-count")).to_have_text("1 candidate found")


# --- what the tests below share --------------------------------------------------------------------------------------


def sighting(api, label: str, criteria: dict, *, wording: str = "N. N.", field: str = "seen") -> tuple[str, str]:
    """A sighting of someone described by `criteria` (in `field`), made through the API: the ids of the sighting and of
    its description"""
    made = api.ok(
        "POST",
        "/api/Sighting",
        {
            "label": label,
            "place": "Ghent",
            "seen": [],
            "company": [],
            field: [{"type": "MatchesCriteria", "wording": wording, "criteria": criteria}],
        },
    )
    read = api.ok("GET", f"/api/Sighting/{made['id']}")
    return made["id"], read[field][0]["id"]


def evaluated(api, id: str, field: str = "seen") -> dict:
    """The sighting once the worker has given its description a result"""
    for _ in range(200):
        read = api.ok("GET", f"/api/Sighting/{id}")
        if read[field][0].get("evaluatedWhen") or read[field][0].get("broken"):
            return read
        time.sleep(0.1)
    raise AssertionError(f"the description of {id} was not evaluated")


def labelled(*labels: str) -> list[re.Pattern]:
    return [re.compile(re.escape(label)) for label in labels]


def people_called(api, *labels: str) -> list[str]:
    return [api.ok("POST", "/api/Person", {"label": label, "has_role": []})["id"] for label in labels]


@contextmanager
def worker_held():
    """The server's criteria worker kept from working: its lease taken in the database, as a second worker would hold it
    (`pangloss_criteria.worker`). A save is marked and waits, so that a page is drawn before the result. Given back
    after, and the worker takes it again when it next looks (within its idle time, 10 s)"""
    driver = neo4j.GraphDatabase.driver(MEMGRAPH_URI, auth=MEMGRAPH_AUTH)
    try:
        driver.execute_query(  # ty: ignore[no-matching-overload]
            "MERGE (w:PGCriteriaWorker {kind: 'criteria'}) SET w.holder = 'e2e', w.until = $until",
            until=time.time() + 120,
            database_="memgraph",
        )
        # (a batch the worker had begun before is finished: then it finds the lease gone)
        time.sleep(1)
        yield
    finally:
        driver.execute_query(  # ty: ignore[no-matching-overload]
            "MATCH (w:PGCriteriaWorker {kind: 'criteria', holder: 'e2e'}) REMOVE w.holder, w.until",
            database_="memgraph",
        )
        driver.close()


# --- the card on the page ----------------------------------------------------------------------------------------------


def test_the_card_shows_the_candidates_when_the_worker_has_found_them_without_a_reload(logged_in: Page, people):
    page = logged_in
    with worker_held():
        id, _ = sighting(people.api, "Seen at Bruges", {"type": "Person", "where": {"has_role": {"is": people.advisor_role}}})
        page.goto(f"/Sighting/{id}")
        hydrated(page)
        card = page.get_by_test_id("criteria-card")
        expect(card.get_by_test_id("criteria-finding")).to_have_text("Finding candidates…")
        expect(card.get_by_test_id("criteria-candidates")).to_have_count(0)
        # (a mark on the page: a reload would take it away)
        page.evaluate("window.__notReloaded = true")
    # (the feed of the card brings them when the worker has found them)
    expect(card.get_by_test_id("criteria-candidates").get_by_role("link")).to_have_text(
        labelled("Marie of Burgundy"), timeout=25_000
    )
    expect(card.get_by_test_id("criteria-finding")).to_have_count(0)
    expect(card.get_by_test_id("criteria-count")).to_have_text(re.compile(r"^1 candidate · updated "))
    assert page.evaluate("window.__notReloaded") is True


def test_five_candidates_then_and_n_more_which_lists_them_all(page: Page, people):
    people_called(people.api, *(f"Ogier {n}" for n in range(1, 8)))
    id, _ = sighting(people.api, "Seen at Lille", {"type": "Person", "where": {"label": {"contains": "Ogier"}}})
    evaluated(people.api, id)
    page.goto(f"/Sighting/{id}")
    hydrated(page)
    card = page.get_by_test_id("criteria-card")
    expect(card.get_by_test_id("criteria-candidates").get_by_role("link")).to_have_text(
        labelled(*(f"Ogier {n}" for n in range(1, 6)))
    )
    expect(card.get_by_test_id("criteria-count")).to_have_text(re.compile(r"^7 candidates · updated "))
    card.get_by_role("button", name="and 2 more").click()
    listed = page.get_by_test_id("criteria-all-candidates")
    expect(listed.get_by_role("link")).to_have_text(labelled(*(f"Ogier {n}" for n in range(1, 8))))


def test_criteria_that_find_more_than_are_linked_are_too_broad(page: Page, people):
    people_called(people.api, *(f"Ogier {n}" for n in range(1, 10)))
    id, _ = sighting(people.api, "Seen at Arras", {"type": "Person", "where": {"label": {"contains": "Ogier"}}})
    evaluated(people.api, id)
    page.goto(f"/Sighting/{id}")
    hydrated(page)
    card = page.get_by_test_id("criteria-card")
    expect(card.get_by_test_id("criteria-too-broad")).to_have_text("Too broad: 9 found")
    expect(card.get_by_test_id("criteria-candidates")).to_have_count(0)


def test_criteria_that_name_a_deleted_entity_say_so(page: Page, people):
    spare = people.api.ok("POST", "/api/Role", {"label": "Spare role", "has_type": []})["id"]
    id, _ = sighting(people.api, "Seen at Mons", {"type": "Person", "where": {"has_role": {"is": spare}}})
    evaluated(people.api, id)
    status, answer = people.api.send("DELETE", f"/api/Role/{spare}")
    assert status < 300, answer
    page.goto(f"/Sighting/{id}")
    hydrated(page)
    card = page.get_by_test_id("criteria-card")
    expect(card.get_by_test_id("criteria-names-deleted")).to_have_text("Names a deleted entity")
    expect(card.get_by_test_id("criteria-summary").get_by_test_id("criteria-deleted-entity")).to_have_text("deleted entity")


def test_a_reader_who_is_not_logged_in_sees_the_card_and_its_candidates_but_cannot_resolve_it(page: Page, people):
    id, _ = sighting(people.api, "Seen at Douai", {"type": "Person", "where": {"has_role": {"is": people.advisor_role}}})
    evaluated(people.api, id)
    page.goto(f"/Sighting/{id}")
    hydrated(page)
    card = page.get_by_test_id("criteria-card")
    expect(card.get_by_test_id("criteria-candidates").get_by_role("link")).to_have_text(labelled("Marie of Burgundy"))
    expect(card.get_by_test_id("criteria-this-is")).to_have_count(0)


# --- in the form ---------------------------------------------------------------------------------------------------------


def test_a_description_of_one_of_several_classes_asks_which_first(logged_in: Page, people):
    page = logged_in
    page.goto("/Sighting/new")
    hydrated(page)
    # (the second field, `company`, takes a description of a person or of a group)
    page.get_by_role("button", name="Add Matches criteria").nth(1).click()
    grid = dialog(page)
    expect(grid.get_by_text("What is described")).to_be_visible()
    expect(grid.locator("button[data-choice]")).to_have_text(["Group", "Person"])
    grid.locator("button[data-choice]", has_text="Group").click()
    expect(grid.get_by_text("Criteria: Group")).to_be_visible()
    # (Back: the classes again, and another chosen)
    grid.get_by_role("button", name="Back").click()
    grid.locator("button[data-choice]", has_text="Person").click()
    expect(grid.get_by_text("Criteria: Person")).to_be_visible()
    add_filter(grid, "has role")
    grid.get_by_role("combobox", name=re.compile("^Find Role")).fill("secretary")
    page.get_by_role("option", name=re.compile("Maximilian's secretary")).click()
    expect(grid.get_by_test_id("criteria-result").get_by_test_id("criteria-count")).to_have_text("1 candidate found")


def test_criteria_the_form_cannot_show_open_read_only(logged_in: Page, people):
    page = logged_in
    # (two conditions on one field: a stored pattern may have them, the form has one a field)
    id, _ = sighting(
        people.api, "Seen at Tournai", {"type": "Person", "where": {"label": {"contains": "Ma", "starts_with": "M"}}}
    )
    page.goto(f"/Sighting/{id}/edit")
    hydrated(page)
    page.get_by_test_id("criteria-editor").get_by_role("button", name="Edit the criteria").click()
    shown = dialog(page).get_by_test_id("criteria-read-only")
    expect(shown).to_contain_text("the form cannot show")
    expect(shown.locator("pre")).to_contain_text('"starts_with": "M"')
    # (no search form; the wording can still be changed)
    expect(dialog(page).get_by_role("combobox", name="Add a filter")).to_have_count(0)
    expect(dialog(page).get_by_label("What the source says")).to_be_editable()


# --- out of date ----------------------------------------------------------------------------------------------------------

MIGRATION = "e2e_app.0099_remove_has_role"
REASON = "where.has_role: the field 'has_role' of Person was removed"


def out_of_date(description: str, reason: str = REASON, since: str | None = MIGRATION) -> None:
    """A description made out of date as a migration that took away what its criteria name leaves it: its computed
    `broken` and `broken_since` set on its node, its candidates kept (the e2e project's models do not change under
    data, so there is no migration to run). The worker does not take it up again until its document is written"""
    driver = neo4j.GraphDatabase.driver(MEMGRAPH_URI, auth=MEMGRAPH_AUTH)
    try:
        driver.execute_query(  # ty: ignore[no-matching-overload]
            "MATCH (d:MatchesCriteria {id: $id}) SET d.broken = $reason, d.broken_since = $since",
            id=description,
            reason=reason,
            since=since,
            database_="memgraph",
        )
    finally:
        driver.close()


def test_a_description_out_of_date_keeps_its_last_candidates_and_is_listed_and_opened_in_its_form(
    logged_in: Page, people
):
    page = logged_in
    id, description = sighting(
        people.api, "Seen at Ypres", {"type": "Person", "where": {"has_role": {"is": people.advisor_role}}}, wording="N. N."
    )
    evaluated(people.api, id)
    out_of_date(description)

    # (on its page: since which migration, the reason, and the last candidates, said to be the last found)
    page.goto(f"/Sighting/{id}")
    hydrated(page)
    card = page.get_by_test_id("criteria-card")
    expect(card.get_by_test_id("criteria-broken")).to_contain_text(f"Out of date since migration {MIGRATION}")
    expect(card.get_by_test_id("criteria-broken-reason")).to_have_text(REASON)
    expect(card.get_by_test_id("criteria-candidates").get_by_role("link")).to_have_text(labelled("Marie of Burgundy"))
    expect(card.get_by_test_id("criteria-count")).to_have_text("1 candidate · the last found: no longer kept up to date")

    # (on the page of those out of date, linked from /admin: the sighting as a chip, the wording, why, and its form)
    page.goto("/admin")
    hydrated(page)
    section = page.get_by_test_id("admin-criteria-broken")
    expect(section.get_by_test_id("admin-criteria-broken-count")).to_have_text("1 description is out of date.")
    section.get_by_role("link", name="List them").click()
    page.wait_for_url(re.compile(r"/criteria/broken$"))
    rows = page.get_by_test_id("criteria-broken-row")
    expect(rows).to_have_count(1)
    expect(rows.get_by_role("link", name=re.compile("Seen at Ypres"))).to_have_attribute("href", f"/Sighting/{id}")
    expect(rows.get_by_test_id("criteria-wording")).to_have_text("“N. N.”")
    expect(rows.get_by_test_id("criteria-summary")).to_contain_text("Marie's advisor")
    expect(rows.get_by_test_id("criteria-broken-since")).to_have_text(f"since migration {MIGRATION}")
    expect(rows.get_by_test_id("criteria-broken-reason")).to_have_text(REASON)
    rows.get_by_test_id("criteria-broken-open").click()
    page.wait_for_url(re.compile(rf"/Sighting/{id}/edit\?show={description}$"))
    hydrated(page)

    # (in the form: the same, and the dialog with the notice in red, and the row of the field that failed red)
    editor = page.get_by_test_id("criteria-editor")
    expect(editor.get_by_test_id("criteria-broken")).to_contain_text(f"Out of date since migration {MIGRATION}")
    editor.get_by_role("button", name="Edit the criteria").click()
    expect(dialog(page).get_by_test_id("criteria-broken-notice")).to_contain_text(REASON)
    criteria = dialog(page).get_by_role("region", name="Criteria")
    expect(criteria.locator("[data-invalid] dt")).to_have_text([re.compile("has role", re.I)])
    expect(dialog(page).get_by_role("button", name="Done")).to_be_disabled()


def test_the_page_of_descriptions_out_of_date_says_when_there_are_none(logged_in: Page, people):
    logged_in.goto("/criteria/broken")
    hydrated(logged_in)
    expect(logged_in.get_by_test_id("criteria-broken-none")).to_have_text("No description is out of date.")


def test_the_page_of_descriptions_out_of_date_asks_a_reader_to_log_in(page: Page, people):
    page.goto("/criteria/broken")
    hydrated(page)
    expect(page.get_by_role("dialog")).to_be_visible()
    expect(page.get_by_test_id("criteria-broken-page")).to_have_count(0)


# --- resolving, and the candidate's page ------------------------------------------------------------------------------


def test_a_candidate_s_page_marks_the_sighting_and_this_is_puts_the_candidate_in_its_place(logged_in: Page, people):
    page = logged_in
    id, _ = sighting(
        people.api,
        "Seen at Namur",
        {"type": "Person", "where": {"has_role": {"is_any": [people.advisor_role, people.secretary_role]}}},
        wording="N. N., of the court",
    )
    evaluated(people.api, id)

    # (on the page of a candidate: the sighting, and in it the mark and what the criteria are, not the other candidates)
    page.goto(f"/Person/{people.marie}")
    hydrated(page)
    marked = page.get_by_test_id("criteria-as-candidate")
    expect(marked.get_by_test_id("criteria-candidate-mark")).to_have_text("identified as candidate")
    expect(marked.get_by_test_id("criteria-summary")).to_contain_text("Marie's advisor")
    expect(page.get_by_test_id("incoming-by-field").get_by_role("link", name=re.compile("Seen at Namur"))).to_be_visible()
    expect(page.get_by_test_id("incoming-by-field").get_by_role("link", name=re.compile("Maximilian$"))).to_have_count(0)
    expect(page.get_by_test_id("criteria-this-is")).to_have_count(0)

    # (on the sighting's page: "This is…" lists the candidates; the one chosen is asked about once, then put in its place)
    page.goto(f"/Sighting/{id}")
    hydrated(page)
    page.get_by_test_id("criteria-card").get_by_test_id("criteria-this-is").click()
    chooser = page.get_by_test_id("criteria-resolve-dialog")
    rows = chooser.get_by_test_id("criteria-candidate-row")
    expect(rows.get_by_role("link")).to_have_text(labelled("Marie of Burgundy", "Maximilian"))
    rows.filter(has_text="Maximilian").get_by_role("button", name="This is the one").click()
    expect(chooser.get_by_test_id("criteria-resolve-confirm")).to_contain_text("Maximilian")
    with page.expect_response(lambda response: response.url.endswith("/resolve")) as answer:
        chooser.get_by_test_id("criteria-resolve-submit").click()
    assert answer.value.ok, answer.value.text()
    expect(page.get_by_role("status", name="Notifications")).to_contain_text(
        "Maximilian is now in the place of the description"
    )
    expect(chooser).to_have_count(0)
    # (the page reads the sighting again: the person where the card was)
    expect(page.get_by_test_id("criteria-card")).to_have_count(0)
    # (the section "Similar" after the contents lists other items too)
    expect(outside_similar(page.locator("main").get_by_role("link", name=re.compile("Maximilian")))).to_be_visible()
    read = people.api.ok("GET", f"/api/Sighting/{id}")
    assert [(each["type"], each["id"]) for each in read["seen"]] == [("Person", people.maximilian)]
    assert read["meta"]["version"] == 2

    # (and the other candidate's page no longer lists it)
    page.goto(f"/Person/{people.marie}")
    hydrated(page)
    expect(page.get_by_test_id("criteria-as-candidate")).to_have_count(0)


# --- the same one in several places of a document (`same_one`) ----------------------------------------------------------


def test_the_same_one_in_two_places_of_a_sighting_has_the_same_candidates_and_this_is_fills_both(logged_in: Page, people):
    page = logged_in
    page.goto("/Sighting/new")
    hydrated(page)
    page.get_by_label("Label", exact=True).fill("Seen twice at Ghent")
    page.get_by_label("Place", exact=True).fill("Ghent")

    # (a description of someone seen, with its criteria)
    page.get_by_role("button", name="Add Matches criteria").first.click()
    dialog(page).get_by_label("What the source says").fill("N. N., an advisor")
    add_filter(dialog(page), "has role")
    dialog(page).get_by_role("combobox", name=re.compile("^Find Role")).fill("advisor")
    page.get_by_role("option", name=re.compile("Marie's advisor")).click()
    expect(dialog(page).get_by_test_id("criteria-result").get_by_test_id("criteria-count")).to_have_text(
        "1 candidate found"
    )
    dialog(page).get_by_role("button", name="Done").click()
    expect(dialog(page)).to_be_hidden()

    # (the one seen again: "The same one as" offers that description, by its summary and wording, under its field)
    page.get_by_role("button", name="Add Matches criteria").nth(2).click()
    same = dialog(page).get_by_test_id("criteria-same-one")
    expect(same).to_be_visible()
    menu = same.get_by_role("combobox", name="The same one as")
    menu.click()
    choices = page.locator(f"[id='{menu.get_attribute('aria-controls')}']")
    expect(choices.get_by_role("option")).to_have_text(
        [re.compile(r"^Person · has role: \[Marie's advisor\] · “N\. N\., an advisor”$", re.I)]
    )
    expect(choices.locator("li[role=presentation]")).to_have_text([re.compile("^seen$", re.I)])
    choices.get_by_role("option").first.click()
    expect(dialog(page)).to_be_hidden()

    # (its card: "the same one as" and the summary of the other's criteria, and a wording of its own)
    editors = page.get_by_test_id("criteria-editor")
    expect(editors).to_have_count(2)
    bare = editors.filter(has=page.get_by_test_id("criteria-same-one-mark"))
    expect(bare.get_by_test_id("criteria-same-one-mark")).to_have_text("The same one as")
    expect(bare.get_by_test_id("criteria-summary")).to_contain_text("Marie's advisor")
    bare.get_by_label("Wording", exact=True).fill("the same man, later")

    with page.expect_response(
        lambda response: response.request.method == "POST" and response.url.endswith("/api/Sighting")
    ) as answer:
        page.get_by_role("banner", name="Console").get_by_role("button", name="Save", exact=True).click()
    assert answer.value.ok, answer.value.text()
    id = answer.value.json()["id"]
    page.wait_for_url(re.compile(rf"/Sighting/{id}$"))
    saved = people.api.ok("GET", f"/api/Sighting/{id}")
    holder, again = saved["seen"][0], saved["seenAgain"]
    assert holder["sameOne"] and holder["sameOne"] == again["sameOne"]
    assert again["criteria"] is None and again["wording"] == "the same man, later"
    assert holder["criteria"]["type"] == "Person"

    # (on its page both places have the same candidates when the worker has found them; the second says it is the
    # same one, with the criteria the route gives; both that they are two places)
    cards = page.get_by_test_id("criteria-card")
    expect(cards).to_have_count(2)
    for card in (cards.nth(0), cards.nth(1)):
        expect(card.get_by_test_id("criteria-candidates").get_by_role("link")).to_have_text(
            labelled("Marie of Burgundy"), timeout=20_000
        )
        expect(card.get_by_test_id("criteria-places")).to_have_text("in 2 places of this document")
    shown = cards.filter(has=page.get_by_test_id("criteria-same-one-mark"))
    expect(shown).to_have_count(1)
    expect(shown.get_by_test_id("criteria-summary")).to_contain_text("Marie's advisor")
    expect(shown.get_by_test_id("criteria-wording")).to_have_text("“the same man, later”")

    # (on the candidate's page, both rows: the second says it is the same one as another description)
    page.goto(f"/Person/{people.marie}")
    hydrated(page)
    marked = page.get_by_test_id("criteria-as-candidate")
    expect(marked).to_have_count(2)
    expect(marked.get_by_test_id("criteria-summary")).to_contain_text(["Marie's advisor"])
    expect(page.get_by_test_id("criteria-same-one-as-another")).to_have_text(
        "the same one as another description of this document"
    )
    expect(
        page.get_by_test_id("incoming-by-field").get_by_role("link", name=re.compile("Seen twice at Ghent"))
    ).to_have_count(2)

    # ("This is…" on the second place: it says that the person goes in both, and puts them there)
    page.goto(f"/Sighting/{id}")
    hydrated(page)
    shown.get_by_test_id("criteria-this-is").click()
    chooser = page.get_by_test_id("criteria-resolve-dialog")
    expect(chooser.get_by_test_id("criteria-resolve-places")).to_have_text(
        "It is put in all 2 places of this document that are the same one."
    )
    chooser.get_by_role("button", name="This is the one").click()
    with page.expect_response(lambda response: response.url.endswith("/resolve")) as answer:
        chooser.get_by_test_id("criteria-resolve-submit").click()
    assert answer.value.ok, answer.value.text()
    expect(page.get_by_role("status", name="Notifications")).to_contain_text(
        "Marie of Burgundy is now in the 2 places of the description"
    )
    expect(page.get_by_test_id("criteria-card")).to_have_count(0)
    read = people.api.ok("GET", f"/api/Sighting/{id}")
    assert [(each["type"], each["id"]) for each in read["seen"]] == [("Person", people.marie)]
    assert (read["seenAgain"]["type"], read["seenAgain"]["id"]) == ("Person", people.marie)


def test_removing_the_place_that_holds_the_criteria_gives_them_to_the_other(logged_in: Page, people):
    page = logged_in
    mark = "00000000-0000-4000-8000-0000000000aa"
    made = people.api.ok(
        "POST",
        "/api/Sighting",
        {
            "label": "Seen at Lier",
            "place": "Lier",
            "seen": [
                {
                    "type": "MatchesCriteria",
                    "wording": "N. N.",
                    "criteria": {"type": "Person", "where": {"has_role": {"is": people.advisor_role}}},
                    "same_one": mark,
                }
            ],
            "company": [],
            "seen_again": {"type": "MatchesCriteria", "wording": "him again", "criteria": None, "same_one": mark},
        },
    )
    page.goto(f"/Sighting/{made['id']}/edit")
    hydrated(page)
    editors = page.get_by_test_id("criteria-editor")
    expect(editors).to_have_count(2)
    holder = editors.filter(has_not=page.get_by_test_id("criteria-same-one-mark"))
    holder.get_by_role("button", name="Remove Matches criteria").click()
    expect(editors).to_have_count(1)
    # (the other place holds them now: a description of its own)
    expect(editors.get_by_test_id("criteria-same-one-mark")).to_have_count(0)
    expect(editors.get_by_test_id("criteria-summary")).to_contain_text("Marie's advisor")
    with page.expect_response(
        lambda response: response.request.method in ("PUT", "PATCH") and f"/api/Sighting/{made['id']}" in response.url
    ) as answer:
        page.get_by_role("banner", name="Console").get_by_role("button", name="Save", exact=True).click()
    assert answer.value.ok, answer.value.text()
    read = people.api.ok("GET", f"/api/Sighting/{made['id']}")
    assert read["seen"] == []
    assert read["seenAgain"]["criteria"]["type"] == "Person"
    assert read["seenAgain"]["wording"] == "him again"


# --- shared descriptions (`Description`, cited by a mention) -----------------------------------------------------------


@pytest.fixture
def shared_people(people):
    """The people, and no shared description of an earlier test"""
    forget("Description")
    return people


def shared_description(api, label: str, criteria: dict) -> str:
    """A shared description made through the API: its id"""
    return api.ok("POST", "/api/Description", {"label": label, "criteria": criteria})["id"]


def citing_sighting(api, label: str, description: str, own: dict | None = None, *, wording: str = "N. N.") -> str:
    """A sighting whose description cites the shared one, with conditions of its own or none: its id"""
    return api.ok(
        "POST",
        "/api/Sighting",
        {
            "label": label,
            "place": "Ghent",
            "seen": [
                {
                    "type": "MatchesCriteria",
                    "wording": wording,
                    "criteria": own,
                    "description": {"type": "Description", "id": description},
                }
            ],
            "company": [],
        },
    )["id"]


def test_a_shared_description_is_used_in_the_dialog_narrowed_and_shown_with_its_chip(logged_in: Page, shared_people):
    page = logged_in
    people = shared_people
    court = shared_description(
        people.api,
        "Someone of the court",
        {"type": "Person", "where": {"has_role": {"is_any": [people.advisor_role, people.secretary_role]}}},
    )
    page.goto("/Sighting/new")
    hydrated(page)
    page.get_by_label("Label", exact=True).fill("Seen at Courtrai")
    page.get_by_label("Place", exact=True).fill("Courtrai")
    page.get_by_role("button", name="Add Matches criteria").first.click()

    # (Start from: the shared description, how many use it, Use and Copy)
    start = dialog(page).get_by_test_id("criteria-start-from")
    row = start.get_by_test_id("criteria-start-from-row").filter(has_text="Someone of the court")
    expect(row.get_by_test_id("criteria-shared-mentions")).to_have_text("0 mentions")
    row.get_by_role("button", name="Use").click()

    # (cited: its criteria at the top, read only; what both find)
    head = dialog(page).get_by_test_id("criteria-shared-head")
    expect(head.get_by_role("link", name=re.compile("Someone of the court"))).to_have_attribute("href", f"/Description/{court}")
    result = dialog(page).get_by_test_id("criteria-result")
    expect(result.get_by_test_id("criteria-count")).to_have_text("2 candidates found")
    expect(dialog(page).get_by_role("button", name="Done")).to_be_enabled()

    # (narrowed: a condition of its own, and both hold)
    add_filter(dialog(page), "has role")
    dialog(page).get_by_role("combobox", name=re.compile("^Find Role")).fill("advisor")
    page.get_by_role("option", name=re.compile("Marie's advisor")).click()
    expect(result.get_by_test_id("criteria-count")).to_have_text("1 candidate found")
    expect(result.get_by_test_id("criteria-shared-summary")).to_contain_text("Someone of the court")
    dialog(page).get_by_role("button", name="Done").click()

    card = page.get_by_test_id("criteria-editor")
    expect(card.get_by_test_id("criteria-shared")).to_contain_text("Someone of the court")
    expect(card.get_by_test_id("criteria-shared-summary").get_by_test_id("criteria-summary")).to_contain_text("Marie's advisor")
    with page.expect_response(
        lambda response: response.request.method == "POST" and response.url.endswith("/api/Sighting")
    ) as answer:
        page.get_by_role("banner", name="Console").get_by_role("button", name="Save", exact=True).click()
    assert answer.value.ok, answer.value.text()
    id = answer.value.json()["id"]
    read = people.api.ok("GET", f"/api/Sighting/{id}")
    assert read["seen"][0]["description"]["targetId"] == court

    # (on its page: the chip, + its own condition, and the candidates of both)
    page.wait_for_url(re.compile(rf"/Sighting/{id}$"))
    shown = page.get_by_test_id("criteria-card")
    expect(shown.get_by_test_id("criteria-shared").get_by_role("link", name=re.compile("Someone of the court"))).to_be_visible()
    expect(shown.get_by_test_id("criteria-candidates").get_by_role("link")).to_have_text(
        labelled("Marie of Burgundy"), timeout=20_000
    )


def test_the_page_of_a_shared_description_says_what_it_is_its_candidates_and_its_mentions(logged_in: Page, shared_people):
    page = logged_in
    people = shared_people
    court = shared_description(
        people.api,
        "Someone of the court",
        {"type": "Person", "where": {"has_role": {"is_any": [people.advisor_role, people.secretary_role]}}},
    )
    first = citing_sighting(people.api, "Seen at Ghent", court, wording="N. N., of the court")
    citing_sighting(people.api, "Seen at Bruges", court, {"type": "Person", "where": {"has_role": {"is": people.advisor_role}}})
    page.goto(f"/Description/{court}")
    hydrated(page)
    expect(page.get_by_test_id("description-used-by")).to_have_text(
        "A description used by 2 mentions. It does not say that they are one and the same."
    )
    expect(page.get_by_test_id("description-intro").get_by_test_id("criteria-summary")).to_contain_text("Marie's advisor")
    expect(page.get_by_test_id("description-candidates").get_by_test_id("criteria-count")).to_have_text("2 candidates found")
    mentions = page.get_by_test_id("description-mention")
    expect(mentions).to_have_count(2)
    ghent = mentions.filter(has_text="Seen at Ghent")
    expect(ghent.get_by_role("link", name=re.compile("Seen at Ghent"))).to_have_attribute(
        "href", re.compile(rf"^/Sighting/{first}\?show=")
    )
    expect(ghent.get_by_test_id("criteria-wording")).to_have_text("“N. N., of the court”")
    expect(mentions.filter(has_text="Seen at Bruges").get_by_test_id("criteria-summary")).to_contain_text("Marie's advisor")


def test_identical_criteria_in_two_other_documents_are_offered_to_be_shared_and_shared(logged_in: Page, shared_people):
    page = logged_in
    people = shared_people
    # (as the form writes them: identical criteria are those written the same)
    criteria = {"type": "Person", "where": {"has_role": {"is_any": [people.advisor_role]}}}
    one, _ = sighting(people.api, "Seen at Ghent", criteria)
    two, _ = sighting(people.api, "Seen at Bruges", criteria)

    page.goto("/Sighting/new")
    hydrated(page)
    page.get_by_label("Label", exact=True).fill("Seen at Lille")
    page.get_by_label("Place", exact=True).fill("Lille")
    page.get_by_role("button", name="Add Matches criteria").first.click()
    add_filter(dialog(page), "has role")
    dialog(page).get_by_role("combobox", name=re.compile("^Find Role")).fill("advisor")
    page.get_by_role("option", name=re.compile("Marie's advisor")).click()

    # (the offer, with the two others as chips; nothing changes until it is confirmed)
    offer = dialog(page).get_by_test_id("criteria-similar")
    expect(offer.get_by_test_id("criteria-similar-count")).to_have_text("The same criteria are used in 2 other documents")
    expect(offer.get_by_test_id("criteria-similar-documents").get_by_role("link")).to_have_count(2)
    offer.get_by_role("button", name="Make them one shared description…").click()
    confirm = offer.get_by_test_id("criteria-share-confirm")
    expect(confirm).to_contain_text("changes 2 other documents, which may be other people's")
    offer.get_by_label("Label of the shared description").fill("Marie's advisor, N. N.")
    with page.expect_response(lambda response: response.url.endswith("/api/criteria/share")) as answer:
        offer.get_by_role("button", name="Change 2 documents and share").click()
    assert answer.value.ok, answer.value.text()
    made = answer.value.json()["description"]["id"]

    # (the dialog cites it now; the two others do, each in a new version)
    expect(dialog(page).get_by_test_id("criteria-shared-head")).to_contain_text("Marie's advisor, N. N.")
    expect(dialog(page).get_by_test_id("criteria-share-outcome")).to_contain_text("2 other documents now cite it.")
    for other in (one, two):
        read = people.api.ok("GET", f"/api/Sighting/{other}")
        assert read["seen"][0]["description"]["targetId"] == made
        assert read["meta"]["version"] == 2
    dialog(page).get_by_role("button", name="Done").click()
    with page.expect_response(
        lambda response: response.request.method == "POST" and response.url.endswith("/api/Sighting")
    ) as saved:
        page.get_by_role("banner", name="Console").get_by_role("button", name="Save", exact=True).click()
    assert saved.value.ok, saved.value.text()
    assert people.api.ok("GET", f"/api/Sighting/{saved.value.json()['id']}")["seen"][0]["description"]["targetId"] == made


def test_editing_a_cited_shared_description_asks_and_marks_its_mentions_changed_since_cited(logged_in: Page, shared_people):
    page = logged_in
    people = shared_people
    court = shared_description(people.api, "Someone of the court", {"type": "Person", "where": {"has_role": {"is": people.advisor_role}}})
    id = citing_sighting(people.api, "Seen at Ghent", court)

    page.goto(f"/Description/{court}/edit")
    hydrated(page)
    # (its criteria in the search form of its class)
    criteria = page.get_by_test_id("description-criteria")
    expect(criteria.get_by_role("button", name="Remove Marie's advisor")).to_be_visible()
    criteria.get_by_role("combobox", name=re.compile("^Find Role")).last.fill("secretary")
    page.get_by_role("option", name=re.compile("Maximilian's secretary")).click()
    page.get_by_role("button", name="Save", exact=True).click()

    # (the core's refusal: it is cited; Save anyway)
    refusal = page.locator("[data-cited-dialog]")
    expect(refusal).to_contain_text("This changes what other documents cite as evidence")
    expect(refusal.get_by_role("link", name=re.compile("Seen at Ghent"))).to_be_visible()
    refusal.get_by_role("button", name="Save anyway").click()
    expect(page).to_have_url(re.compile(rf"/Description/{court}$"))

    # (the mention says the shared description changed since it was cited; Seen in its form takes that off)
    page.goto(f"/Sighting/{id}")
    hydrated(page)
    expect(page.get_by_test_id("criteria-card").get_by_test_id("criteria-shared-marks")).to_contain_text("changed since cited")
    page.goto(f"/Sighting/{id}/edit")
    hydrated(page)
    editor = page.get_by_test_id("criteria-editor")
    editor.get_by_test_id("criteria-shared-marks").get_by_role("button", name="Seen").click()
    expect(editor.get_by_test_id("criteria-shared-marks")).to_have_count(0)
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page).to_have_url(re.compile(rf"/Sighting/{id}$"))
    expect(page.get_by_test_id("criteria-shared-marks")).to_have_count(0)
