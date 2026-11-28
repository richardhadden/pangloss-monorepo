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
    # (`types` has forgotten the chronicles, towns and spaces of the last test's accounts)
    api = types.admin()
    people = {name: made(api, "Person", name, has_role=[]) for name in ("Anna Vos", "Anna Voss", "Pieter Claes", "Joos Damhouder", "Margriet Smet", "Lieven Baert")}  # fmt: skip
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
    # (step 7.5: a prohibition breached, a permission used; and a tale, whose statements are not compared)
    margriet, lieven, joos = people["Margriet Smet"], people["Lieven Baert"], people["Joos Damhouder"]
    forbade = account(
        "Joos's letter of April",
        letters,
        {
            "type": "Prohibition",
            "label": "Joos forbids Margriet to go to Ghent",
            "forbidder": ref("Person", joos),
            "forbidden": [ref("Person", margriet)],
            "when": julian(1500, 4, 1),
            "thing_forbidden": {"type": "Forbidden", "contents": [journey("Margriet is not to go to Ghent", margriet, towns["Ghent"], julian(1500, 5, 1))]},  # fmt: skip
        },
    )
    went = account("The annals, of Margriet", annals, journey("Margriet goes to Ghent", margriet, towns["Ghent"], julian(1500, 5, 1)))  # fmt: skip
    allowed = account(
        "Joos's letter of June",
        letters,
        {
            "type": "Permission",
            "label": "Joos allows Lieven to go to Bruges",
            "granter": ref("Person", joos),
            "permitted": [ref("Person", lieven)],
            "when": julian(1500, 6, 1),
            "thing_permitted": {"type": "Permitted", "contents": [journey("Lieven may go to Bruges", lieven, towns["Bruges"], julian(1500, 7, 1))]},  # fmt: skip
        },
    )
    used = account("The annals, of Lieven", annals, journey("Lieven goes to Bruges", lieven, towns["Bruges"], julian(1500, 7, 1)))  # fmt: skip
    tale = account(
        "A tale of Anna",
        bruges,
        {"type": "Fiction", "contents": [baptism("Anna is baptised by a fairy", anna, towns["Ghent"])]},
    )
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
        forbidden=told(api, forbade)[0]["thingForbidden"]["contents"][0]["id"],
        went=told(api, went)[0]["id"],
        permitted=told(api, allowed)[0]["thingPermitted"]["contents"][0]["id"],
        used=told(api, used)[0]["id"],
        fairy=told(api, tale)[0]["contents"][0]["id"],
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
        # (each ask is a search of the vectors: not too often)
        time.sleep(1.0)


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
    expect(section.locator(f"[id=\"{folded.get_attribute('aria-controls')}\"]")).to_be_hidden()
    folded.click()
    expect(folded).to_have_attribute("aria-expanded", "true")
    expect(rows).to_have_count(2)
    rumoured = rows.nth(1)
    expect(rumoured).to_have_attribute("data-other", accounts.rumoured)
    expect(rumoured.get_by_test_id("compare-relation")).to_have_text("Carried out")
    # (the interface's own mark of what is only reported)
    expect(rumoured.locator('[data-assertion="reported"]')).to_have_text("Reported")
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
    # (the pairs through near entities asked, and come: not only the line drawn before they are)
    expect(section).to_have_attribute("data-near-settled", "true")
    expect(section.get_by_test_id("compare-none")).to_have_text("Nothing found to compare it with")
    expect(rows_of(section)).to_have_count(0)


# ---------------------------------------------------------------------------
# The page of two side by side, and recording a judgement (step 7.5)
# ---------------------------------------------------------------------------


def pair_page(page: Page, type_: str, a: str, b: str) -> None:
    page.goto(f"/compare/{type_}/{a}/{b}")
    hydrated(page)
    expect(page.get_by_test_id("compare-page")).to_be_visible()


def offered(page: Page) -> list[str]:
    return [b.get_attribute("data-verdict") or "" for b in page.get_by_test_id("compare-judge").locator("[data-verdict]").all()]  # fmt: skip


def record(page: Page, verdict: str, note: str = "", fields: dict[str, bool] | None = None) -> None:
    """Choose the verdict, tick or untick fields by their labels, write the note, Record; then wait for the page to
    list it first"""
    judge = page.get_by_test_id("compare-judge")
    judge.locator(f'[data-verdict="{verdict}"]').click()
    expect(judge.locator(f'[data-verdict="{verdict}"]')).to_have_attribute("aria-checked", "true")
    for label, on in (fields or {}).items():
        box = judge.get_by_test_id("compare-judge-fields").get_by_label(label, exact=True)
        box.set_checked(on)
    if note:
        judge.get_by_test_id("compare-note").fill(note)
    judge.get_by_test_id("compare-record").click()
    expect(page.get_by_test_id("compare-judgement").first).to_have_attribute("data-verdict", verdict)
    if note:
        expect(page.get_by_test_id("compare-judgement").first.get_by_test_id("compare-judgement-note")).to_have_text(note)


def judged(api, type_: str, a: str, b: str) -> list[dict]:
    """The judgements of the pair as the route gives them, newest first"""
    answer = api.ok("GET", f"/api/compare/{type_}/{a}")
    (entry,) = [e for e in answer["pairs"] if e["other"]["id"] == b]
    return entry["judgements"]


def test_the_page_of_two_side_by_side_is_reached_from_a_row(page: Page, accounts):
    """The row's relation leads to the two side by side: each headed by its chip and "according to" its source, the
    fields of their class in rows, the town marked changed; above, the relation in the row's words, with the
    likelihood as a figure. Logged out: the judgements, and no controls"""
    page.goto(f"/Baptism/{accounts.baptism}")
    hydrated(page)
    row = compared_section(page).locator(f'[data-testid="compare-row"][data-other="{accounts.differs}"]')
    row.get_by_test_id("compare-relation").click()
    expect(page).to_have_url(re.compile(rf"/compare/Baptism/{accounts.baptism}/{accounts.differs}$"))
    hydrated(page)
    said = page.get_by_test_id("compare-said")
    expect(said.get_by_test_id("compare-relation")).to_have_text("Disagrees")
    expect(said.get_by_test_id("compare-fields")).to_have_text("on Town")
    expect(said.get_by_test_id("compare-likelihood")).to_have_text(re.compile(r"^Likelihood \d\.\d\d$"))
    columns = page.get_by_test_id("compare-column")
    expect(columns).to_have_count(2)
    expect(columns.nth(0)).to_have_attribute("data-statement", accounts.baptism)
    expect(columns.nth(0).get_by_test_id("compare-source")).to_contain_text("The annals of Ghent")
    expect(columns.nth(1).locator(f'a[href="/Baptism/{accounts.differs}"]')).to_contain_text("Anna is baptised at Bruges")
    expect(columns.nth(1).get_by_test_id("compare-source")).to_contain_text("The letters of Joos")
    # (the person both name, one row the same; the towns, one row, the second changed)
    expect(page.locator(f'[data-testid="compare-cell"][data-row=".baptised[{accounts.people["Anna Vos"]}]"]')).to_have_count(2)  # fmt: skip
    town = page.locator('[data-testid="compare-cell"][data-row=".town[@0]"]')
    expect(town.nth(1)).to_have_attribute("data-mark", "changed")
    expect(town.nth(1)).to_contain_text("Bruges")
    expect(page.get_by_test_id("compare-your-judgement")).to_have_count(0)
    expect(page.get_by_test_id("compare-judgements")).to_have_count(0)
    # (a judged pair: its judgement listed, by whom, and nothing to delete it with)
    pair_page(page, "Baptism", accounts.baptism, accounts.agrees)
    (judgement,) = page.get_by_test_id("compare-judgement").all()
    expect(judgement).to_have_attribute("data-verdict", "agree")
    expect(judgement).to_contain_text("by e2e")
    expect(judgement.get_by_test_id("compare-delete")).to_have_count(0)
    expect(page.get_by_test_id("compare-record")).to_have_count(0)


def test_two_reports_are_judged_agree_disagree_and_two_events(logged_in: Page, accounts):
    """The verdicts of two that describe; "disagree" with the fields the comparison found ticked, sent and shown; each
    then the pair's relation, newest first; the section shows the judged row, and the pair judged two events folded"""
    page = logged_in
    pair_page(page, "Baptism", accounts.baptism, accounts.differs)
    assert offered(page) == ["agree", "disagree", "two_events"]
    record(page, "agree", "the town aside")
    expect(page.get_by_test_id("compare-said").get_by_test_id("compare-relation")).to_have_text("Agrees")
    expect(page.get_by_test_id("compare-said").get_by_test_id("compare-worked-out")).to_have_text("Worked out: Disagrees")  # fmt: skip
    judge = page.get_by_test_id("compare-judge")
    judge.locator('[data-verdict="disagree"]').click()
    # (ticked as the comparison found them)
    expect(judge.get_by_test_id("compare-judge-fields").get_by_label("Town", exact=True)).to_be_checked()
    expect(judge.get_by_test_id("compare-judge-fields").get_by_label("Baptised", exact=True)).not_to_be_checked()
    record(page, "disagree", fields={"When": True})
    newest = page.get_by_test_id("compare-judgement").first
    expect(newest.get_by_test_id("compare-judgement-fields")).to_have_text("on Town, When")
    assert judged(accounts.api, "Baptism", accounts.baptism, accounts.differs)[0]["fields"] == ["town", "when"]
    expect(page.get_by_test_id("compare-judgement")).to_have_count(2)
    # (the section: the row judged, disagreeing)
    page.get_by_role("link", name="Back to the statement").click()
    hydrated(page)
    row = compared_section(page).locator(f'[data-testid="compare-row"][data-other="{accounts.differs}"]')
    expect(row).to_have_attribute("data-relation", "disagree")
    expect(row.get_by_test_id("compare-judged")).to_contain_text("by e2e")
    # Two events: out of the rows, folded by itself
    pair_page(page, "Baptism", accounts.baptism, accounts.differs)
    record(page, "two_events")
    page.goto(f"/Baptism/{accounts.baptism}")
    hydrated(page)
    section = compared_section(page)
    expect(section.locator(f'[data-testid="compare-row"][data-other="{accounts.differs}"]')).to_have_count(0)
    folded = section.get_by_test_id("compare-two-events")
    expect(folded).to_have_text("1 judged two events")
    expect(folded).to_have_attribute("aria-expanded", "false")
    folded.click()
    expect(section.locator(f'[data-testid="compare-row"][data-other="{accounts.differs}"]')).to_have_attribute("data-relation", "two")  # fmt: skip


def test_an_order_and_what_came_of_it_are_judged_each_way(logged_in: Page, accounts):
    """An order and what was done late: the targets met and missed; the five verdicts of an order, each recorded and
    then the pair's relation; "carried out otherwise" with the target the comparison found (When) ticked"""
    page = logged_in
    # (asked from what was done: the order is first all the same)
    pair_page(page, "Journey", accounts.done, accounts.ordered)
    expect(page.get_by_test_id("compare-column").nth(0)).to_have_attribute("data-statement", accounts.ordered)
    said = page.get_by_test_id("compare-said")
    expect(said.get_by_test_id("compare-relation")).to_have_text("Carried out otherwise")
    targets = said.get_by_test_id("compare-targets")
    expect(targets.locator('[data-target="when"]')).to_have_attribute("data-how", "late")
    expect(targets.locator('[data-target="when"]')).to_have_text("When: late")
    expect(targets.locator('[data-target="destination"]')).to_have_attribute("data-how", "met")
    assert offered(page) == ["carried_out", "carried_out_otherwise", "not_carried_out", "done_not_carried_out", "two_events"]  # fmt: skip
    for verdict, relation in [
        ("carried_out", "Carried out"),
        ("not_carried_out", "Not carried out"),
        ("done_not_carried_out", "Done, but not carried out"),
    ]:
        record(page, verdict)
        expect(said.get_by_test_id("compare-relation")).to_have_text(relation)
    judge = page.get_by_test_id("compare-judge")
    judge.locator('[data-verdict="carried_out_otherwise"]').click()
    expect(judge.get_by_test_id("compare-judge-fields").get_by_label("When", exact=True)).to_be_checked()
    record(page, "carried_out_otherwise", "a month and a half late")
    expect(page.get_by_test_id("compare-judgement").first.get_by_test_id("compare-judgement-fields")).to_have_text("on When")  # fmt: skip
    record(page, "two_events")
    expect(page.get_by_test_id("compare-judgement")).to_have_count(5)
    # (the prescription in `statement`, as the model asks)
    stored = accounts.api.ok("GET", f"/api/PairJudgement/{judged(accounts.api, 'Journey', accounts.ordered, accounts.done)[0]['id']}")  # fmt: skip
    assert (stored["statement"]["targetId"], stored["other"]["targetId"]) == (accounts.ordered, accounts.done)
    # (the order's section: the pair judged two events folded)
    page.goto(f"/Journey/{accounts.ordered}")
    hydrated(page)
    expect(compared_section(page).get_by_test_id("compare-two-events")).to_have_text("1 judged two events")


def test_a_prohibition_and_a_permission_are_judged(logged_in: Page, accounts):
    """A prohibition breached: breach, complied, two events offered; a permission used: permission used, two events"""
    page = logged_in
    pair_page(page, "Journey", accounts.forbidden, accounts.went)
    expect(page.get_by_test_id("compare-said").get_by_test_id("compare-relation")).to_have_text("Breached")
    assert offered(page) == ["breach", "complied", "two_events"]
    record(page, "complied", "she stayed at home")
    expect(page.get_by_test_id("compare-said").get_by_test_id("compare-relation")).to_have_text("Complied with")
    record(page, "breach")
    expect(page.get_by_test_id("compare-said").get_by_test_id("compare-relation")).to_have_text("Breached")
    pair_page(page, "Journey", accounts.permitted, accounts.used)
    expect(page.get_by_test_id("compare-said").get_by_test_id("compare-relation")).to_have_text("Permission used")
    assert offered(page) == ["permission_used", "two_events"]
    record(page, "permission_used")
    page.goto(f"/Journey/{accounts.permitted}")
    hydrated(page)
    row = compared_section(page).locator(f'[data-testid="compare-row"][data-other="{accounts.used}"]')
    expect(row.get_by_test_id("compare-judged")).to_contain_text("Judged")


def test_a_judgement_is_deleted_and_its_page_offers_no_edit(logged_in: Page, accounts):
    """Delete asks first (`/deletable`), then the judgement is gone from the page; a judgement's own page has Delete
    and no Edit, and its edit address says it is not changed once made"""
    page = logged_in
    pair_page(page, "Baptism", accounts.baptism, accounts.again)
    record(page, "agree", "to be taken back")
    (judgement,) = judged(accounts.api, "Baptism", accounts.baptism, accounts.again)
    page.goto(f"/PairJudgement/{judgement['id']}")
    hydrated(page)
    expect(page.get_by_role("heading", level=1)).to_contain_text("Agrees")
    expect(page.get_by_role("link", name="Edit")).to_have_count(0)
    expect(page.get_by_role("button", name="Delete")).to_be_visible()
    page.goto(f"/PairJudgement/{judgement['id']}/edit")
    expect(page.get_by_test_id("cannot-edit")).to_have_text(re.compile("not changed once made"))
    pair_page(page, "Baptism", accounts.baptism, accounts.again)
    page.get_by_test_id("compare-judgement").first.get_by_test_id("compare-delete").click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_role("button", name="Delete").click()
    expect(dialog).to_have_count(0)
    expect(page.get_by_test_id("compare-judgement")).to_have_count(0)
    assert judged(accounts.api, "Baptism", accounts.baptism, accounts.again) == []


def test_a_pair_the_comparison_does_not_find_is_still_shown_and_may_be_judged(logged_in: Page, accounts):
    """Two baptisms of two people (no pair by rule, none through near entities): side by side all the same, with the
    line that the comparison found no relation, and the verdicts of two that describe"""
    page = logged_in
    pair_page(page, "Baptism", accounts.lonely, accounts.baptism)
    expect(page.get_by_test_id("compare-no-relation")).to_have_text("The comparison found no relation between these two.")  # fmt: skip
    expect(page.get_by_test_id("compare-column")).to_have_count(2)
    assert offered(page) == ["agree", "disagree", "two_events"]
    record(page, "two_events", "two people")
    # (an unknown statement, a class that is not compared: the ordinary not-found)
    page.goto(f"/compare/Baptism/{accounts.lonely}/00000000-0000-0000-0000-000000000000")
    expect(page.get_by_role("heading", name="Page not found")).to_be_visible()
    page.goto(f"/compare/Account/{accounts.first}/{accounts.no_source}")
    expect(page.get_by_role("heading", name="Page not found")).to_be_visible()


def test_the_page_of_a_pair_through_near_entities_says_so(logged_in: Page, accounts):
    """From the near group's row: "If these are the same Person", the two as chips, the way to merging them"""
    page = logged_in
    until_near(accounts.api, "Baptism", accounts.baptism)
    page.goto(f"/Baptism/{accounts.baptism}")
    hydrated(page)
    group = compared_section(page).get_by_test_id("compare-near-group")
    group.get_by_test_id("compare-relation").click()
    expect(page).to_have_url(re.compile(rf"/compare/Baptism/{accounts.baptism}/{accounts.namesake}$"))
    hydrated(page)
    said = page.get_by_test_id("compare-said")
    expect(said.get_by_test_id("compare-if-same")).to_have_text(re.compile("If these are the same Person", re.I))
    expect(said.locator(f'a[href="/Person/{accounts.people["Anna Voss"]}"]')).to_be_visible()
    expect(said.get_by_test_id("compare-merge")).to_have_attribute(
        "href", f"/Person/{accounts.people['Anna Vos']}/merge/{accounts.people['Anna Voss']}"
    )
    assert offered(page) == ["agree", "disagree", "two_events"]


def test_whose_claim_an_account_is_is_not_drawn_twice(logged_in: Page, accounts):
    """The source said under the title ("According to") is not a row of the contents again; the form keeps it; an
    account of no one has its other rows and no source row"""
    page = logged_in
    page.goto(f"/Account/{accounts.first}")
    hydrated(page)
    expect(page.get_by_test_id("according-to")).to_be_visible()
    contents = page.locator("dl").first
    expect(contents.locator("dt", has_text=re.compile("^Source$"))).to_have_count(0)
    expect(contents.locator("dt", has_text=re.compile("^Told$"))).to_have_count(1)
    page.goto(f"/Account/{accounts.first}/edit")
    hydrated(page)
    expect(page.get_by_text("Source", exact=True).first).to_be_visible()


def test_a_statement_that_is_not_compared_has_no_section(page: Page, accounts):
    """A baptism told as a tale (`Fiction`, `compared=False`): the route has no comparison of it, so no section and
    no request for its near pairs"""
    asked: list[str] = []
    page.on("request", lambda request: asked.append(request.url) if "/api/compare/" in request.url else None)
    page.goto(f"/Baptism/{accounts.fairy}")
    hydrated(page)
    expect(page.get_by_test_id("similar-section")).to_be_visible()
    expect(compared_section(page)).to_have_count(0)
    assert not any("near=true" in url for url in asked), asked
