"""Comparison of statements (`pangloss_compare`): its interface module adds a section after the contents of the page of
a statement of a compared class (`itemSections.Compared`; "Carried out?" where the statement prescribes what it
holds), and the item page says under a head's title whose claim it holds ("According to", the field its ground names).

The e2e project's models: an `Account` is its `Chronicle`'s claim (`Ground(by="source")`), and tells of `Baptism`s (one
for each person), `Journey`s and `Command`s that a journey be made (`Commanded`, which prescribes); `PairJudgement` is
a person's judgement of two. The pairs by rule need nothing but the data; those through near entities need the
vectors of the people, which the worker in the server brings up to date after each write (the test waits for them by
asking the route)."""

import re
import time
from types import SimpleNamespace

import pytest
from conftest import Stack, forget, julian
from helpers import hydrated
from playwright.sync_api import Page, expect


def made(api, kind: str, label: str, **fields) -> str:
    return api.ok("POST", f"/api/{kind}", {"label": label, **fields})["id"]


def ref(kind: str, id_: str) -> dict:
    return {"type": kind, "id": id_}


def baptism(label: str, person: str, town: str | None = None) -> dict:
    return {
        "type": "Baptism",
        "label": label,
        "baptised": ref("Person", person),
        "town": ref("Town", town) if town else None,
        "when": julian(1500, 3, 1),
    }


def journey(label: str, person: str, town: str, when: dict) -> dict:
    return {"type": "Journey", "label": label, "traveller": ref("Person", person), "destination": ref("Town", town), "when": when}  # fmt: skip


def told(api, id_: str) -> list[dict]:
    """What an account tells, as the API gives it back (with the ids of the statements)"""
    return api.ok("GET", f"/api/Account/{id_}")["told"]


def compared_section(page: Page):
    return page.get_by_test_id("compare-section")


def rows_of(scope):
    return scope.get_by_test_id("compare-row")


@pytest.fixture
def accounts(types: Stack) -> SimpleNamespace:
    """Anna's baptism told four times (at Ghent by the annals and by the Bruges chronicle, which agree and which a
    person judged to agree; at Bruges by Joos's letters, which disagree on the town; again by the annals, with no
    town), and once of an Anna Voss, a near namesake; a command that Pieter go to Bruges by 1 February, the journey
    made on 15 March (late), and a report that it was made on time (superseded by what was done)"""
    forget("Chronicle", "Town")
    api = types.admin()
    people = {name: made(api, "Person", name, has_role=[]) for name in ("Anna Vos", "Anna Voss", "Pieter Claes", "Joos Damhouder")}  # fmt: skip
    chronicles = {name: made(api, "Chronicle", name) for name in ("The annals of Ghent", "The Bruges chronicle", "The letters of Joos")}  # fmt: skip
    towns = {name: made(api, "Town", name) for name in ("Ghent", "Bruges")}
    annals, bruges, letters = chronicles.values()

    def account(label: str, source: str | None, *statements: dict) -> str:
        return made(api, "Account", label, source=ref("Chronicle", source) if source else None, told=list(statements))

    anna = people["Anna Vos"]
    first = account("The annals, 1500", annals, baptism("Anna is baptised at Ghent", anna, towns["Ghent"]))
    agrees = account("The Bruges chronicle, 1500", bruges, baptism("Anna is baptised at Ghent, says Bruges", anna, towns["Ghent"]))  # fmt: skip
    differs = account("Joos's letter of March", letters, baptism("Anna is baptised at Bruges", anna, towns["Bruges"]))  # fmt: skip
    again = account("The annals, 1501", annals, baptism("Anna is baptised, the annals again", anna))
    namesake = account("The Bruges chronicle, 1502", bruges, baptism("Anna Voss is baptised at Ghent", people["Anna Voss"], towns["Ghent"]))  # fmt: skip
    pieter = people["Pieter Claes"]
    command = account(
        "Joos's letter of January",
        letters,
        {
            "type": "Command",
            "label": "Joos commands Pieter to go to Bruges",
            "commander": ref("Person", people["Joos Damhouder"]),
            "commanded": [ref("Person", pieter)],
            "when": julian(1500, 1, 10),
            "thing_commanded": {"type": "Commanded", "contents": [journey("Pieter is to go to Bruges", pieter, towns["Bruges"], julian(1500, 2, 1))]},  # fmt: skip
        },
    )
    done = account("The annals, of Pieter", annals, journey("Pieter goes to Bruges", pieter, towns["Bruges"], julian(1500, 3, 15)))  # fmt: skip
    rumour = account(
        "The Bruges chronicle, of Pieter",
        bruges,
        {"type": "Reported", "contents": [journey("Pieter went to Bruges, it is said", pieter, towns["Bruges"], julian(1500, 2, 1))]},  # fmt: skip
    )
    no_source = account("An account of no one", None, baptism("Pieter is baptised", pieter))
    ids = SimpleNamespace(
        api=api,
        people=people,
        chronicles=chronicles,
        towns=towns,
        first=first,
        no_source=no_source,
        baptism=told(api, first)[0]["id"],
        agrees=told(api, agrees)[0]["id"],
        differs=told(api, differs)[0]["id"],
        again=told(api, again)[0]["id"],
        namesake=told(api, namesake)[0]["id"],
        ordered=told(api, command)[0]["thingCommanded"]["contents"][0]["id"],
        done=told(api, done)[0]["id"],
        rumoured=told(api, rumour)[0]["contents"][0]["id"],
        lonely=told(api, no_source)[0]["id"],
    )
    api.ok(
        "POST",
        "/api/PairJudgement",
        {
            "type": "PairJudgement",
            "label": "The two agree",
            "verdict": "agree",
            "statement": ref("Baptism", ids.baptism),
            "other": ref("Baptism", ids.agrees),
        },
    )
    return ids


def until_near(api, type_: str, id_: str, seconds: float = 60) -> dict:
    """The pairs through near entities of a statement once the worker of the vectors has worked its people out"""
    deadline = time.monotonic() + seconds
    while True:
        answer = api.ok("GET", f"/api/compare/{type_}/{id_}?near=true")
        if answer["near"]["state"] == "ok" and answer["pairs"]:
            return answer
        assert time.monotonic() < deadline, f"no pairs through near entities of {type_} {id_}: {answer}"
        time.sleep(0.3)


def test_a_statement_s_page_says_how_the_others_stand_to_it(page: Page, accounts):
    """Each pair a row: the relation (a link to the two side by side), the other as a chip, whose claim it is, one
    source, the judgement and by whom; the likelihood in the title only. Read by anyone"""
    page.goto(f"/Baptism/{accounts.baptism}")
    hydrated(page)
    section = compared_section(page)
    expect(section.locator("h2")).to_have_text("Compared")
    rows = rows_of(section.get_by_test_id("compare-by-rule"))
    expect(rows).to_have_count(3)
    by_other = {row.get_attribute("data-other"): row for row in rows.all()}
    assert set(by_other) == {accounts.agrees, accounts.differs, accounts.again}
    agrees, differs, again = by_other[accounts.agrees], by_other[accounts.differs], by_other[accounts.again]

    relation = agrees.get_by_test_id("compare-relation")
    expect(relation).to_have_text("Agrees")
    expect(relation).to_have_attribute("href", f"/compare/Baptism/{accounts.baptism}/{accounts.agrees}")
    expect(agrees.locator(f'a[href="/Baptism/{accounts.agrees}"]')).to_contain_text("Anna is baptised at Ghent, says Bruges")
    expect(agrees.get_by_test_id("compare-source")).to_contain_text("The Bruges chronicle")
    expect(agrees.get_by_test_id("compare-judged")).to_contain_text("Judged")
    expect(agrees.get_by_test_id("compare-judged")).to_contain_text("by e2e")
    expect(agrees).to_have_attribute("title", re.compile(r"^Likelihood \d\.\d\d$"))
    expect(agrees).not_to_contain_text(re.compile(r"\d\.\d\d"))

    expect(differs.get_by_test_id("compare-relation")).to_have_text("Disagrees")
    expect(differs.get_by_test_id("compare-fields")).to_have_text("on Town")
    expect(differs.get_by_test_id("compare-source")).to_contain_text("The letters of Joos")

    # (told again by the same chronicle)
    expect(again.get_by_test_id("compare-within")).to_have_text("within the same source")
    expect(again.get_by_test_id("compare-judged")).to_have_count(0)

    # (the near namesake, by itself after the rest; to someone logged out with no way to merge)
    until_near(accounts.api, "Baptism", accounts.baptism)
    page.reload()
    hydrated(page)
    near = section.get_by_test_id("compare-near")
    expect(near.locator("h3")).to_have_text(re.compile("If these are the same Person", re.I))
    group = near.get_by_test_id("compare-near-group")
    expect(group).to_have_count(1)
    expect(group).to_have_attribute("data-near", accounts.people["Anna Voss"])
    expect(group.get_by_role("meter")).to_have_attribute("aria-label", re.compile(r"^Similarity \d\.\d\d$"))
    expect(group.get_by_test_id("compare-row")).to_have_attribute("data-other", accounts.namesake)
    expect(group.get_by_test_id("compare-merge")).to_have_count(0)


def test_someone_logged_in_is_offered_to_merge_two_near_entities(logged_in: Page, accounts):
    page = logged_in
    until_near(accounts.api, "Baptism", accounts.baptism)
    page.goto(f"/Baptism/{accounts.baptism}")
    hydrated(page)
    merge = compared_section(page).get_by_test_id("compare-merge")
    expect(merge).to_have_attribute(
        "href", f"/Person/{accounts.people['Anna Vos']}/merge/{accounts.people['Anna Voss']}"
    )


def test_a_prescription_s_page_asks_whether_it_was_carried_out(page: Page, accounts):
    """The journey commanded: done late (by its date), and reported done on time, which what was done supersedes:
    folded behind a button that says how many"""
    page.goto(f"/Journey/{accounts.ordered}")
    hydrated(page)
    section = compared_section(page)
    expect(section.locator("h2")).to_have_text("Carried out?")
    rows = rows_of(section.get_by_test_id("compare-by-rule"))
    expect(rows).to_have_count(1)
    expect(rows.first).to_have_attribute("data-other", accounts.done)
    expect(rows.first.get_by_test_id("compare-relation")).to_have_text("Carried out otherwise")
    expect(rows.first.get_by_test_id("compare-fields")).to_have_text("(When: late)")
    folded = section.get_by_test_id("compare-superseded")
    expect(folded).to_have_text("1 more, superseded")
    expect(folded).to_have_attribute("aria-expanded", "false")
    folded.click()
    expect(folded).to_have_attribute("aria-expanded", "true")
    expect(rows).to_have_count(2)
    rumoured = rows.nth(1)
    expect(rumoured).to_have_attribute("data-other", accounts.rumoured)
    expect(rumoured.get_by_test_id("compare-relation")).to_have_text("Carried out")
    expect(rumoured.get_by_test_id("compare-reported")).to_have_text("reported")
    # (what was done: "Compared", the command among its pairs)
    page.goto(f"/Journey/{accounts.done}")
    hydrated(page)
    expect(compared_section(page).locator("h2")).to_have_text("Compared")
    expect(rows_of(compared_section(page)).locator(f'a[href="/Journey/{accounts.ordered}"]')).to_have_count(1)


def test_a_head_says_whose_claim_it_holds_and_nothing_is_compared_of_what_is_not(page: Page, accounts):
    page.goto(f"/Account/{accounts.first}")
    hydrated(page)
    ground = page.get_by_test_id("head-ground")
    expect(ground.get_by_test_id("according-to")).to_have_text(re.compile("According to", re.I))
    chip = ground.locator(f'a[href="/Chronicle/{accounts.chronicles["The annals of Ghent"]}"]')
    expect(chip).to_contain_text("The annals of Ghent")
    # (under the title)
    title = page.get_by_role("heading", level=1).bounding_box()
    line = ground.bounding_box()
    assert title and line and line["y"] >= title["y"] + title["height"] - 1
    # (an account is not compared: no section)
    expect(page.get_by_test_id("similar-section")).to_be_visible()
    expect(compared_section(page)).to_have_count(0)
    # (one that names no source, and a person, whose relations are the record: nothing)
    page.goto(f"/Account/{accounts.no_source}")
    hydrated(page)
    expect(page.get_by_role("heading", level=1)).to_have_text("An account of no one")
    expect(page.get_by_test_id("head-ground")).to_have_count(0)
    page.goto(f"/Person/{accounts.people['Anna Vos']}")
    hydrated(page)
    expect(page.get_by_role("heading", level=1)).to_have_text("Anna Vos")
    expect(page.get_by_test_id("head-ground")).to_have_count(0)


def test_a_statement_with_nothing_to_compare_says_so(page: Page, accounts):
    """Pieter's baptism, told once, of a person with no namesake: a line, once the pairs through near entities have
    none either"""
    page.goto(f"/Baptism/{accounts.lonely}")
    hydrated(page)
    section = compared_section(page)
    expect(section.locator("h2")).to_have_text("Compared")
    expect(section.get_by_test_id("compare-none")).to_have_text("Nothing found to compare it with")
    expect(rows_of(section)).to_have_count(0)
