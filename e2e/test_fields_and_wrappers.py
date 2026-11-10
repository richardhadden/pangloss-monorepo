"""The kinds of field and of wrapper that only the `Dossier` of the e2e project has (conftest.py): enums (pills for a
few values, a dropdown for many), a list of annotated values, a reified relation with its head, one shown without
(`headless`), a semantic space; and a search that finds more than `SEARCH_HIT_LIMIT` (40 in the e2e project)."""

import re
from types import SimpleNamespace

import pytest
from conftest import forget
from helpers import hydrated
from playwright.sync_api import Page, expect


@pytest.fixture
def dossier(data) -> SimpleNamespace:
    forget("Dossier", "Group")
    api = data.api
    chronicle = api.ok("POST", "/api/Group", {"label": "The chronicle"})["id"]
    made = api.ok(
        "POST",
        "/api/Dossier",
        {
            "label": "The dossier",
            "grade": "probable",
            "planet": "mars",
            "names": [{"value": "Karolus", "certainty": 5}, {"value": "Carl", "certainty": 2}],
            "witnesses": [
                {"type": "InRole", "role": "scribe", "target": [{"type": "Person", "id": data.marie}]}
            ],
            "source": {"type": "AtPage", "page": "f. 12", "target": [{"type": "Group", "id": chronicle}]},
            "claims": [
                {"type": "Claim", "label": "Plain claim", "text": "It was so"},
                {"type": "Denied", "contents": [{"type": "Claim", "label": "Denied claim", "text": "It was not so"}]},
            ],
        },
    )
    return SimpleNamespace(id=made["id"], chronicle=chronicle, api=api, marie=data.marie)


def field(page: Page, name: str):
    """The value of a field of the item (the `dd` after its `dt`), at the top level"""
    return page.locator("main > div dl > div, main dl > div").filter(
        has=page.locator("> dt", has_text=re.compile(f"^{name}$", re.I))
    ).first.locator("> dd")


def test_the_page_of_an_item_with_every_kind_of_wrapper(page: Page, dossier):
    page.goto(f"/Dossier/{dossier.id}")
    hydrated(page)
    main = page.locator("main")
    expect(main.get_by_role("heading", level=1, name="The dossier")).to_be_visible()

    # (the members of an enum by their names, as the form has them, not as they are stored: "probable", "mars")
    expect(field(page, "Grade")).to_have_text("Probable")
    expect(field(page, "Planet")).to_have_text("Mars")

    # (a list of annotated values: each value, with what is said of it)
    names = field(page, "Names")
    expect(names).to_have_text(re.compile(r"Karolus\s*Certainty\s*5\s*Carl\s*Certainty\s*2"))

    # (a reified relation: its head, what it points at as a chip, and its own fields; no "target" is said)
    witnesses = field(page, "Witnesses")
    expect(witnesses).to_contain_text("In role")
    expect(witnesses.get_by_role("link", name="Person Marie of Burgundy")).to_have_attribute(
        "href", f"/Person/{dossier.marie}"
    )
    expect(witnesses).to_have_text(re.compile(r"Role\s*scribe"))
    expect(main).not_to_contain_text(re.compile("target", re.I))

    # (headless: the only type its field can hold, one and required, so no head: what it holds, then its page)
    source = field(page, "Source")
    expect(source).not_to_contain_text("At page")
    expect(source.get_by_role("link", name="Group The chronicle")).to_have_attribute(
        "href", f"/Group/{dossier.chronicle}"
    )
    expect(source).to_have_text(re.compile(r"The chronicle\s*Page\s*f\. 12"))

    # (a document as it is, and one in a semantic space: the space is named, round what it holds)
    claims = field(page, "Claims")
    expect(claims.get_by_role("link", name="Claim Plain claim")).to_be_visible()
    expect(claims).to_contain_text("Denied")
    expect(claims.get_by_role("link", name="Claim Denied claim")).to_be_visible()
    expect(claims).to_have_text(re.compile(r"Plain claim.*It was so.*Denied.*Denied claim.*It was not so", re.S))


def test_an_entity_reached_through_a_reified_relation_shows_the_field_in_the_document(page: Page, dossier):
    page.goto(f"/Person/{dossier.marie}")
    hydrated(page)
    refers = page.get_by_test_id("incoming-by-field")
    expect(refers).to_contain_text("Witnesses reverse")
    expect(refers.get_by_role("link", name="Dossier The dossier")).to_have_attribute("href", f"/Dossier/{dossier.id}")
    # (under the dossier, the field she is in, with the role she has there)
    expect(refers).to_contain_text(re.compile(r"The dossier\s*Witnesses\s*In role\s*Person\s*Marie of Burgundy\s*Role\s*scribe"))


def test_the_page_of_a_document_in_a_semantic_space_shows_the_space_round_it(page: Page, dossier):
    claims = dossier.api.ok("GET", f"/api/Dossier/{dossier.id}")["claims"]
    denied = next(claim for claim in claims if claim["type"] == "Denied")["contents"][0]["id"]
    page.goto(f"/Claim/{denied}")
    hydrated(page)
    main = page.locator("main")
    expect(main.get_by_role("heading", level=1, name="Denied claim")).to_be_visible()
    # (what it is contained in, and that it is denied there)
    expect(main).to_contain_text("Contained in")
    expect(main.get_by_role("link", name="Dossier The dossier")).to_have_attribute(
        "href", f"/Dossier/{dossier.id}?show={denied}"
    )
    expect(main).to_contain_text("Denied")
    expect(main).to_contain_text("It was not so")


def test_enums_are_pills_or_a_dropdown_and_annotated_values_a_list_in_the_form(logged_in: Page, dossier):
    page = logged_in
    page.goto("/Dossier/new")
    hydrated(page)
    page.get_by_label("Label", exact=True).fill("A new dossier")

    # (three values: pills, one of them or none; the chosen one again takes it away)
    grade = page.get_by_role("radiogroup", name="Grade")
    expect(grade.get_by_role("radio")).to_have_text(["Certain", "Probable", "Doubtful"])
    grade.get_by_role("radio", name="Doubtful").click()
    expect(grade.get_by_role("radio", name="Doubtful")).to_be_checked()
    grade.get_by_role("radio", name="Doubtful").click()
    expect(grade.get_by_role("radio", name="Doubtful")).not_to_be_checked()

    # (nine values: a dropdown, with nothing chosen to start with, as the field may be left out)
    planet = page.get_by_role("combobox", name="Planet")
    expect(planet).to_have_value("")
    expect(planet.locator("option")).to_have_count(10)
    planet.select_option(label="Saturn")

    # (the headless source: the search and its own field, with no head and no button to add it)
    page.get_by_label("Find Group…").fill("chronicle")
    page.get_by_role("option", name="The chronicle").click()
    page.get_by_label("Page", exact=True).fill("f. 3")

    # (grade is required: not sent without it, and said at the field)
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page).to_have_url(re.compile(r"/Dossier/new$"))
    expect(page.locator("main dt", has_text="Grade")).to_contain_text("Required")
    grade.get_by_role("radio", name="Certain").click()

    # (annotated values: added one at a time, each with its own fields, and taken away)
    add = page.get_by_role("button", name="Add to Names")
    add.click()
    add.click()
    values = page.get_by_label(re.compile(r"^Names( \d+)?( value)?$", re.I))
    expect(values).to_have_count(2)
    values.nth(0).fill("Karolus")
    values.nth(1).fill("Carl")
    certainties = page.get_by_role("spinbutton", name=re.compile("Certainty"))
    expect(certainties).to_have_count(2)
    certainties.nth(0).fill("5")
    certainties.nth(1).fill("2")

    with page.expect_response(
        lambda response: response.request.method == "POST" and response.url.endswith("/api/Dossier")
    ) as answer:
        page.get_by_role("button", name="Save", exact=True).click()
    assert answer.value.ok, answer.value.text()
    saved = dossier.api.ok("GET", f"/api/Dossier/{answer.value.json()['id']}")
    assert (saved["grade"], saved["planet"]) == ("certain", "saturn"), saved
    assert [(name["value"], name["certainty"]) for name in saved["names"]] == [("Karolus", 5), ("Carl", 2)]
    assert (saved["source"]["page"], saved["source"]["target"][0]["label"]) == ("f. 3", "The chronicle")
    assert saved["witnesses"] == [] and saved["claims"] == []


def test_a_search_that_finds_more_than_the_limit_says_so(page: Page, dossier):
    for n in range(45):
        dossier.api.ok("POST", "/api/Group", {"label": f"Crowd {n:02}"})
    try:
        page.goto("/Group?q=Crowd")
        hydrated(page)
        console = page.get_by_role("banner", name="Console")
        # (40 were counted, and there are more: the count says so, and why)
        expect(console).to_contain_text("40+")
        expect(console.get_by_title("Found, and more: narrow the search")).to_be_visible()
        # (a word that few have is counted exactly)
        page.goto("/Group?q=07")
        hydrated(page)
        expect(page.locator("main").get_by_role("link", name="Group Crowd 07")).to_be_visible()
        expect(console).to_contain_text(re.compile(r"Groups\s*1(?!\+)"))
        # (a second word beside one that too many have does not make the count exact: the limit is on what the words
        # find, before both are asked of each. See the findings in COVERAGE.md)
        page.goto("/Group?q=Crowd+07")
        hydrated(page)
        expect(page.locator("main").get_by_role("link", name="Group Crowd 07")).to_be_visible()
        expect(console).to_contain_text("1+")
    finally:
        forget("Group")
