"""A statement compared with its pairs over the API, `GET /api/compare/{type}/{ref}`, and people's judgements of the
pairs (`pangloss_compare.compare`, `judgements`, `api`; implementation_docs/spaces-and-comparison-plan.md, step
6.5), on the backend under test, with `similar_models.declare(compared=True, ...)` and its `StatementJudgement`: the
relations of three kinds of pair, a judgement overriding, the newest winning, either order of the two, a statement
changed since it was cited, what the reader may see, the 404s, nothing written, the ordinary write refusing what is
no statement, and what one lookup costs."""

import asyncio
from typing import Any, no_type_check
from uuid import uuid4

import httpx2 as httpx
import pytest
from pangloss_api import create_app
from pangloss_testing.live import run
from pangloss_users import service

from test_compare_pairs_live import (
    activity,
    counts,
    entities,
    factoid,
    giving,
    order,
    ref,
    settled,
    stored,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

PASSWORD = "correct horse"


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    )


async def bearer(api, username: str) -> dict:
    await service.create_user(username, f"{username}@example.com", PASSWORD)
    response = await api.post(
        "/api/users/token", data={"username": username, "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def birth(label: str, person: str, place: str) -> dict:
    return {"type": "Birth", "label": label, "person": ref(person), "place": ref(place, "Place")}  # fmt: skip


@no_type_check
async def world(m) -> dict[str, str]:
    """A birth told twice, a gathering and its denial, an order and what was done: the ids by name, the people's and
    the statements'"""
    ids = await entities(m)
    ids["birth fac"] = await factoid(m, "a birth", birth("Ada is born", ids["ada"], ids["mill"]))  # fmt: skip
    ids["again fac"] = await factoid(m, "a birth again", birth("Ada is born, again", ids["ada"], ids["mill"]))  # fmt: skip
    await factoid(m, "a gathering", activity("Ada met Ben", ids["ada"], ids["ben"]))
    await factoid(
        m,
        "a denial",
        {
            "type": "Negative",
            "contents": [activity("Ada did not meet Ben", ids["ada"], ids["ben"])],
        },  # fmt: skip
    )
    await factoid(m, "an order", order(ids, "the order", giving("to give", ids["doer"], ids["receiver"])))  # fmt: skip
    await factoid(m, "what came of it", giving("gave", ids["doer"], ids["receiver"]))
    return ids


def by_label(answer: dict) -> dict[str, dict]:
    return {entry["other"]["label"]: entry for entry in answer["pairs"]}


async def judge(api, headers, statement: dict, other: dict, verdict: str, **more: Any):
    """A judgement written by the ordinary create route of its class"""
    response = await api.post(
        "/api/StatementJudgement",
        json={
            "type": "StatementJudgement",
            "label": f"{verdict}",
            "verdict": verdict,
            "statement": statement,
            "other": other,
            **more,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def cite(db_driver, label: str, kind: str) -> dict:
    return {"type": kind, "id": stored(db_driver, label)}


# ---------------------------------------------------------------------------
# The pairs and their relations
# ---------------------------------------------------------------------------


@no_type_check
async def test_the_route_gives_a_statement_s_pairs_with_their_relations(
    clear_database, db_driver
):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids = await world(m)

    async with client() as api:
        twice = await api.get(f"/api/compare/Birth/{stored(db_driver, 'Ada is born')}")
        denied = await api.get(
            f"/api/compare/Activity/{stored(db_driver, 'Ada met Ben')}"
        )
        ordered = await api.get(f"/api/compare/Transfer/{stored(db_driver, 'to give')}")
        done = await api.get(f"/api/compare/Transfer/{stored(db_driver, 'gave')}")
        # (at a class above the statement's own)
        above = await api.get(
            f"/api/compare/Statement/{stored(db_driver, 'Ada is born')}"
        )
    for response in (twice, denied, ordered, done, above):
        assert response.status_code == 200, response.text

    answer = twice.json()
    assert answer["statement"]["label"] == "Ada is born"
    assert answer["statement"]["head"]["type"] == "Factoid"
    assert answer["statement"]["head"]["label"] == "a birth"
    assert answer["more"] is False
    (entry,) = answer["pairs"]
    assert entry["other"]["label"] == "Ada is born, again"
    assert entry["other"]["type"] == "Birth"
    assert entry["other"]["head"] == {"id": stored(db_driver, "a birth again"), "type": "Factoid", "label": "a birth again"}  # fmt: skip
    assert entry["relation"] == "agree"
    assert entry["likelihood"] == 1.0
    assert entry["found"] == "rule"
    # (the entity both name as a chip: its id, class and label)
    assert entry["by"] == [{"field": "person", "entity": {"id": ids["ada"], "type": "Person", "label": "ada"}, "kind": "rule"}]  # fmt: skip
    assert entry["judged"] is None and entry["judgements"] == []
    assert entry["workedOut"] == {"relation": "agree", "fields": [], "how": {}, "reported": False}  # fmt: skip
    assert above.json() == answer

    assert (
        by_label(denied.json())["Ada did not meet Ben"]["relation"] == "contradiction"
    )

    # (an order and what was done: the prescription first, whichever of the two is asked)
    order_id, gave_id = stored(db_driver, "to give"), stored(db_driver, "gave")
    for asked in (ordered.json(), done.json()):
        (entry,) = [e for e in asked["pairs"] if e["relation"] == "carried_out"]
        assert (entry["first"], entry["second"]) == (order_id, gave_id)
        assert entry["reported"] is False and entry["superseded"] is False


@no_type_check
async def test_each_statement_says_whose_claim_it_is_and_whether_it_prescribes(
    clear_database, db_driver
):
    """The factoid's ground names its source (`Ground(by="source")`): each statement, the one asked about and each
    other, has it as a chip, or null where its factoid has none; and says whether it prescribes its contents"""
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids = await world(m)
    annals = str((await m.Source.Create(label="the annals").save()).id)
    await m.Factoid.Create(
        label="the annals' birth",
        source={"type": "Source", "id": annals},
        statements=[birth("Ada is born, say the annals", ids["ada"], ids["mill"])],
    ).save()

    async with client() as api:
        said = (await api.get(f"/api/compare/Birth/{stored(db_driver, 'Ada is born, say the annals')}")).json()  # fmt: skip
        plain = (await api.get(f"/api/compare/Birth/{stored(db_driver, 'Ada is born')}")).json()  # fmt: skip
        ordered = (await api.get(f"/api/compare/Transfer/{stored(db_driver, 'to give')}")).json()  # fmt: skip

    chip = {"id": annals, "type": "Source", "label": "the annals"}
    assert said["statement"]["sources"] == [chip]
    assert said["statement"]["prescribes"] is False
    assert said["statement"]["prescription"] is None
    assert {e["other"]["label"]: e["other"]["sources"] for e in said["pairs"]} == {
        "Ada is born": [],
        "Ada is born, again": [],
    }
    assert plain["statement"]["sources"] == []
    assert by_label(plain)["Ada is born, say the annals"]["other"]["sources"] == [chip]
    # (the order's contents are prescribed, an order; what was done is not)
    assert ordered["statement"]["prescribes"] is True
    assert ordered["statement"]["prescription"] == "order"
    assert by_label(ordered)["gave"]["other"]["prescribes"] is False
    assert by_label(ordered)["gave"]["other"]["prescription"] is None


@no_type_check
async def test_the_pairs_are_strongest_first_and_two_events_last(
    clear_database, db_driver
):
    """A gathering told again by its host with other guests (two events), and told again as it was (agree)"""
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids = await entities(m)
    await factoid(m, "one", activity("Ada met Ben", ids["ada"], ids["ben"]))
    await factoid(m, "two", activity("Ada met Ben too", ids["ada"], ids["ben"]))
    await factoid(m, "three", activity("Ada met Cy and Dee", ids["ada"], ids["cy"], ids["dee"]))  # fmt: skip

    async with client() as api:
        answer = (await api.get(f"/api/compare/Activity/{stored(db_driver, 'Ada met Ben')}")).json()  # fmt: skip

    assert [(e["other"]["label"], e["relation"]) for e in answer["pairs"]] == [
        ("Ada met Ben too", "agree"),
        ("Ada met Cy and Dee", "two"),
    ]


# ---------------------------------------------------------------------------
# A person's judgement
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_judgement_overrides_and_what_was_worked_out_is_kept(
    clear_database, db_driver
):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    await world(m)
    first = cite(db_driver, "Ada is born", "Birth")
    again = cite(db_driver, "Ada is born, again", "Birth")

    async with client() as api:
        ann = await bearer(api, "ann")
        made = await judge(api, ann, first, again, "two_events", note="two Adas")
        answer = (await api.get(f"/api/compare/Birth/{first['id']}")).json()

    (entry,) = answer["pairs"]
    assert entry["relation"] == "two"
    assert entry["fields"] == [] and entry["how"] == {} and entry["reported"] is False
    assert entry["judged"] == "two_events"
    assert entry["workedOut"]["relation"] == "agree"
    # (the rest is the maths' whatever a person said)
    assert entry["likelihood"] == 1.0 and entry["strength"] == 1.0
    (judgement,) = entry["judgements"]
    assert judgement["id"] == made["id"]
    assert judgement["type"] == "StatementJudgement"
    assert judgement["verdict"] == "two_events"
    assert judgement["note"] == "two Adas"
    assert judgement["fields"] == []
    assert [c["username"] for c in judgement["createdBy"]] == ["ann"]
    assert judgement["createdWhen"] is not None
    assert judgement["changedSinceCited"] is False


@no_type_check
async def test_the_newest_of_two_judgements_wins_both_are_listed_and_either_order_counts(
    clear_database, db_driver
):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    await world(m)
    first = cite(db_driver, "Ada is born", "Birth")
    again = cite(db_driver, "Ada is born, again", "Birth")

    async with client() as api:
        ann, bob = await bearer(api, "ann"), await bearer(api, "bob")
        older = await judge(api, ann, first, again, "agree")
        await asyncio.sleep(0.01)
        # (the two in the other order: a judgement is of the pair)
        newer = await judge(api, bob, again, first, "disagree", fields=["place"])
        asked_first = (await api.get(f"/api/compare/Birth/{first['id']}")).json()
        asked_again = (await api.get(f"/api/compare/Birth/{again['id']}")).json()

    for answer in (asked_first, asked_again):
        (entry,) = answer["pairs"]
        assert entry["relation"] == "disagree"
        assert entry["fields"] == ["place"]
        assert entry["judged"] == "disagree"
        assert entry["workedOut"]["relation"] == "agree"
        listed = [(j["id"], [c["username"] for c in j["createdBy"]]) for j in entry["judgements"]]  # fmt: skip
        assert listed == [(newer["id"], ["bob"]), (older["id"], ["ann"])]
        whens = [j["createdWhen"] for j in entry["judgements"]]
        assert whens == sorted(whens, reverse=True)


@no_type_check
async def test_a_judgement_of_a_statement_changed_since_it_was_cited_still_overrides_and_says_so(
    clear_database, db_driver
):
    from pangloss_models.exceptions import PanglossCitedError
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids = await world(m)
    first = cite(db_driver, "Ada is born", "Birth")
    again = cite(db_driver, "Ada is born, again", "Birth")
    async with client() as api:
        ann = await bearer(api, "ann")
        await judge(api, ann, first, again, "two_events")

    # (the second telling now says she was born elsewhere: refused unless the citations are acknowledged)
    town = str((await m.Place.Create(label="the town").save()).id)
    read = await m.Factoid.get(ids["again fac"])
    data = read.model_dump(mode="json", exclude={"meta"})
    data["statements"][0]["place"] = ref(town, "Place")
    with pytest.raises(PanglossCitedError):
        await m.Factoid.Update(**data).save()
    await m.Factoid.Update(**data).save(acknowledge_citations=True)

    async with client() as api:
        answer = (await api.get(f"/api/compare/Birth/{first['id']}")).json()

        # (and asked from the side of the statement that changed)
        own_side = (await api.get(f"/api/compare/Birth/{again['id']}")).json()

    for asked in (answer, own_side):
        (entry,) = asked["pairs"]
        assert entry["relation"] == "two" and entry["judged"] == "two_events"
        assert entry["workedOut"]["relation"] == "disagree"
        assert entry["workedOut"]["fields"] == ["place"]
        (judgement,) = entry["judgements"]
        assert judgement["changedSinceCited"] is True


@no_type_check
async def test_the_three_verdicts_added_are_recorded_and_shown(
    clear_database, db_driver
):
    """A prohibition complied with, a permission used, and an order done by another: a judgement of each, written
    by the ordinary create, is the entry's relation and is listed with the pair"""
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids = await entities(m)
    await factoid(m, "a prohibition", order(ids, "forbade", giving("not to give", ids["doer"], ids["receiver"]), space="Forbidden"))  # fmt: skip
    await factoid(m, "kept to it", giving("gave nothing", ids["doer"], ids["receiver"]))
    await factoid(m, "a permission", order(ids, "allowed", giving("may give to the guild", ids["doer"], ids["guild"], "Group"), space="Permitted"))  # fmt: skip
    await factoid(m, "used it", giving("gave to the guild", ids["doer"], ids["guild"], "Group"))  # fmt: skip
    await factoid(m, "an order", order(ids, "ordered", giving("to give to Gus", ids["doer"], ids["gus"])))  # fmt: skip
    await factoid(m, "by another", giving("Eve gave to Gus", ids["eve"], ids["gus"]))
    cases = [
        ("not to give", "gave nothing", "complied"),
        ("may give to the guild", "gave to the guild", "permission_used"),
        ("to give to Gus", "Eve gave to Gus", "done_not_carried_out"),
    ]
    async with client() as api:
        ann = await bearer(api, "ann")
        made = {}
        for asked, other, verdict in cases:
            made[verdict] = await judge(api, ann, cite(db_driver, asked, "Transfer"), cite(db_driver, other, "Transfer"), verdict)  # fmt: skip
        answers = {
            asked: (
                await api.get(f"/api/compare/Transfer/{stored(db_driver, asked)}")
            ).json()  # fmt: skip
            for asked, _, _ in cases
        }
    for asked, other, verdict in cases:
        (entry,) = [e for e in answers[asked]["pairs"] if e["other"]["label"] == other]
        assert entry["relation"] == entry["judged"] == verdict, entry
        assert entry["reported"] is False and entry["how"] == {}
        (judgement,) = entry["judgements"]
        assert (
            judgement["id"] == made[verdict]["id"] and judgement["verdict"] == verdict
        )
        assert judgement["label"] == made[verdict]["label"]
    # (what each prescription is, as the interface offers the verdicts that fit)
    assert answers["not to give"]["statement"]["prescription"] == "prohibition"
    assert answers["may give to the guild"]["statement"]["prescription"] == "permission"
    assert answers["to give to Gus"]["statement"]["prescription"] == "order"


@no_type_check
async def test_another_class_citing_the_same_statements_is_no_judgement(
    clear_database, db_driver
):
    """An inference whose evidence cites both statements of a pair (`Inference.evidence`, another `Cites` field of
    another class) is not taken for a judgement of the pair"""
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    await world(m)
    first = cite(db_driver, "Ada is born", "Birth")
    again = cite(db_driver, "Ada is born, again", "Birth")
    await factoid(m, "an inference", {"type": "Inference", "label": "so", "evidence": [first, again]})  # fmt: skip
    async with client() as api:
        answer = (await api.get(f"/api/compare/Birth/{first['id']}")).json()
    (entry,) = answer["pairs"]
    assert entry["judged"] is None and entry["judgements"] == []
    assert entry["relation"] == "agree"


# ---------------------------------------------------------------------------
# What a judgement may be: never edited, of two statements, of their fields
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_judgement_is_never_edited_and_may_be_deleted(
    clear_database, db_driver
):
    """The ordinary `PUT`, and an update by the models, are refused with why; nothing changes; a new judgement is
    how a person changes their mind; deleting is as for any document"""
    from pangloss_models import PanglossWriteRefused
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    await world(m)
    first = cite(db_driver, "Ada is born", "Birth")
    again = cite(db_driver, "Ada is born, again", "Birth")
    async with client() as api:
        ann = await bearer(api, "ann")
        made = await judge(api, ann, first, again, "agree", note="one Ada")
        read = await api.get(f"/api/StatementJudgement/{made['id']}", headers=ann)
        assert read.status_code == 200, read.text
        body = {**read.json(), "verdict": "two_events", "note": "two Adas after all"}
        before = await settled(db_driver)
        put = await api.put(
            f"/api/StatementJudgement/{made['id']}",
            json=body,
            headers={**ann, "If-Match": "*"},
        )
        assert put.status_code == 422, put.text
        assert "A judgement is not changed once made" in put.text
        assert counts(db_driver) == before
        data = (await m.StatementJudgement.get(made["id"])).model_dump(mode="json", exclude={"meta"})  # fmt: skip
        with pytest.raises(
            PanglossWriteRefused, match="make a new judgement of the pair"
        ):
            await m.StatementJudgement.Update(**{**data, "note": "changed"}).save()
        assert (await m.StatementJudgement.get(made["id"])).note == "one Ada"

        deleted = await api.delete(f"/api/StatementJudgement/{made['id']}", headers=ann)
        assert deleted.status_code in (200, 204), deleted.text
        answer = (await api.get(f"/api/compare/Birth/{first['id']}")).json()
    assert answer["pairs"][0]["judgements"] == []


@no_type_check
async def test_a_judgement_of_one_statement_twice_or_of_fields_neither_has_is_refused(
    clear_database, db_driver
):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    await world(m)
    first = cite(db_driver, "Ada is born", "Birth")
    again = cite(db_driver, "Ada is born, again", "Birth")
    gave = cite(db_driver, "gave", "Transfer")

    async def made(**more):
        return await api.post(
            "/api/StatementJudgement",
            json={
                "type": "StatementJudgement",
                "label": "j",
                "verdict": "disagree",
                "statement": first,
                "other": again,
                **more,
            },  # fmt: skip
            headers=ann,
        )

    async with client() as api:
        ann = await bearer(api, "ann")
        before = await settled(db_driver)
        twice = await made(other=first)
        unknown = await made(fields=["place", "colourOfEyes"])
        # (a field of the other's class, not of the statement's: of one of the two)
        neither = await made(other=gave, fields=["givenTo", "eyes", "ears"])
        assert counts(db_driver) == before
        either = await made(other=gave, fields=["givenTo", "person"])
        assert either.status_code == 201, either.text

    assert twice.status_code == 422
    assert twice.json()["detail"][0]["loc"] == ["body", "other"]
    assert "both cite" in twice.json()["detail"][0]["msg"]
    assert unknown.status_code == 422
    assert unknown.json()["detail"][0]["loc"] == ["body", "fields"]
    assert unknown.json()["detail"][0]["msg"].startswith(
        "'colourOfEyes' is not a field of Birth:"
    )
    assert neither.status_code == 422
    assert neither.json()["detail"][0]["msg"].startswith("'eyes', 'ears' are not fields of Birth or Transfer:")  # fmt: skip


@no_type_check
async def test_a_judgement_s_fields_are_taken_in_camel_case_stored_as_python_s_and_given_back_in_camel_case(
    clear_database, db_driver
):
    """What the route gives (`carriedOutBy`) is what a judgement says back; stored as Python's names; the ordinary
    read of the judgement gives them in camelCase too (`FieldName`'s JSON form); in Python, by the
    models, Python's; what the read gives, sent back, is stored as Python's again"""
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids = await entities(m)
    await factoid(m, "one", activity("Ada met Ben", ids["ada"], ids["ben"]))
    await factoid(m, "two", activity("Ada met Ben too", ids["ada"], ids["ben"]))
    first = cite(db_driver, "Ada met Ben", "Activity")
    other = cite(db_driver, "Ada met Ben too", "Activity")
    async with client() as api:
        ann = await bearer(api, "ann")
        made = await judge(api, ann, first, other, "disagree", fields=["carriedOutBy", "participants"])  # fmt: skip
        answer = (await api.get(f"/api/compare/Activity/{first['id']}")).json()
        read = (
            await api.get(f"/api/StatementJudgement/{made['id']}", headers=ann)
        ).json()
        listed = (await api.get("/api/StatementJudgement", headers=ann)).json()
        again = await judge(api, await bearer(api, "bob"), first, other, "disagree", fields=read["fields"])  # fmt: skip

    rows = run(db_driver, "MATCH (j:StatementJudgement) RETURN j.id AS id, j.fields AS fields")  # fmt: skip
    assert {r["id"]: list(r["fields"]) for r in rows} == {
        made["id"]: ["carried_out_by", "participants"],
        again["id"]: ["carried_out_by", "participants"],
    }
    (entry,) = answer["pairs"]
    assert entry["fields"] == ["carriedOutBy", "participants"]
    assert entry["judgements"][0]["fields"] == ["carriedOutBy", "participants"]
    assert entry["by"][0]["field"] == "carriedOutBy"
    assert read["fields"] == ["carriedOutBy", "participants"], (made, listed)
    # (a list's items, and what a create answers, are references: no `fields` to give)
    items = listed.get("items", listed.get("results", []))
    assert items and all("fields" not in item for item in items), listed
    assert (await m.StatementJudgement.get(made["id"])).fields == ["carried_out_by", "participants"]  # fmt: skip


@no_type_check
async def test_a_narrowed_field_is_stored_and_given_back_by_the_name_the_verdict_gives_it(
    clear_database, db_driver
):
    """A painting's `picture_made` narrows a making's `made`: given as either, stored as `made`, the name in
    `workedOut.fields`; a name whose camelCase is not as given (`field2` of a `field_2`) is the case of the pure
    tests, `test_compare_judgement_model.py`"""
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids = await entities(m)
    for label in ("painted", "painted again"):
        await factoid(m, f"fac {label}", {"type": "MakingOfPicture", "label": label, "made_by": ref(ids["maker"]), "picture_made": ref(ids["picture"], "Picture")})  # fmt: skip
    first, other = cite(db_driver, "painted", "MakingOfPicture"), cite(db_driver, "painted again", "MakingOfPicture")  # fmt: skip
    async with client() as api:
        ann = await bearer(api, "ann")
        await judge(api, ann, first, other, "disagree", fields=["pictureMade", "made", "madeBy"])  # fmt: skip
        answer = (await api.get(f"/api/compare/MakingOfPicture/{first['id']}")).json()
    (row,) = run(db_driver, "MATCH (j:StatementJudgement) RETURN j.fields AS fields")
    assert list(row["fields"]) == ["made", "made_by"]
    (entry,) = answer["pairs"]
    assert entry["fields"] == entry["judgements"][0]["fields"] == ["made", "madeBy"]
    assert entry["by"][0]["field"] in ("made", "madeBy")


# ---------------------------------------------------------------------------
# What the reader may see
# ---------------------------------------------------------------------------


@no_type_check
async def test_an_unpublished_factoid_s_statement_is_compared_only_for_a_reader_who_may_see_it(
    clear_database, db_driver
):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True, reviewed=True)
    ids = await entities(m)
    await factoid(m, "published", activity("Ada met Ben", ids["ada"], ids["ben"]), published=True)  # fmt: skip
    await factoid(m, "not published", activity("Cy met Ben", ids["cy"], ids["ben"]), published=False)  # fmt: skip
    shown, hidden = stored(db_driver, "Ada met Ben"), stored(db_driver, "Cy met Ben")

    async with client() as api:
        anyone_shown = await api.get(f"/api/compare/Activity/{shown}")
        anyone_hidden = await api.get(f"/api/compare/Activity/{hidden}")
        ann = await bearer(api, "ann")
        ann_shown = await api.get(f"/api/compare/Activity/{shown}", headers=ann)
        ann_hidden = await api.get(f"/api/compare/Activity/{hidden}", headers=ann)

    assert anyone_shown.status_code == 200 and anyone_shown.json()["pairs"] == []
    assert anyone_hidden.status_code == 404
    assert [e["other"]["label"] for e in ann_shown.json()["pairs"]] == ["Cy met Ben"]
    assert [e["other"]["label"] for e in ann_hidden.json()["pairs"]] == ["Ada met Ben"]


@no_type_check
async def test_a_judgement_the_reader_may_not_see_does_not_show(
    clear_database, db_driver
):
    """`StatementJudgement` is reviewed with `declare(reviewed=True)`: one saved unpublished is seen only by a reader
    who may see what is not published; a deleted one by no one"""
    from pangloss_testing.similar_models import declare

    m = declare(compared=True, reviewed=True)
    ids = await entities(m)
    await factoid(m, "a birth", birth("Ada is born", ids["ada"], ids["mill"]), published=True)  # fmt: skip
    await factoid(m, "a birth again", birth("Ada is born, again", ids["ada"], ids["mill"]), published=True)  # fmt: skip
    first = cite(db_driver, "Ada is born", "Birth")
    again = cite(db_driver, "Ada is born, again", "Birth")
    public = await m.StatementJudgement.Create(label="public", verdict="agree", statement=first, other=again).save(published=True)  # fmt: skip
    await asyncio.sleep(0.01)
    private = await m.StatementJudgement.Create(label="private", verdict="two_events", statement=first, other=again).save(published=False)  # fmt: skip
    await asyncio.sleep(0.01)
    gone = await m.StatementJudgement.Create(label="gone", verdict="disagree", statement=first, other=again).save(published=True)  # fmt: skip
    await m.StatementJudgement.delete(gone.id)

    async with client() as api:
        anyone = (await api.get(f"/api/compare/Birth/{first['id']}")).json()
        ann = await bearer(api, "ann")
        logged_in = (
            await api.get(f"/api/compare/Birth/{first['id']}", headers=ann)
        ).json()

    (entry,) = anyone["pairs"]
    assert [j["id"] for j in entry["judgements"]] == [str(public.id)]
    assert entry["relation"] == "agree" and entry["judged"] == "agree"
    (entry,) = logged_in["pairs"]
    assert [j["id"] for j in entry["judgements"]] == [str(private.id), str(public.id)]
    assert entry["relation"] == "two" and entry["judged"] == "two_events"


# ---------------------------------------------------------------------------
# What there is no comparison of
# ---------------------------------------------------------------------------


@no_type_check
async def test_what_there_is_no_comparison_of_is_a_404_the_same_for_each(
    clear_database, db_driver
):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True, reviewed=True)
    ids = await entities(m)
    hidden_fac = await factoid(m, "not published", activity("Cy met Ben", ids["cy"], ids["ben"]), published=False)  # fmt: skip
    hidden = stored(db_driver, "Cy met Ben")
    await factoid(m, "published", activity("Ada met Ben", ids["ada"], ids["ben"]), published=True)  # fmt: skip
    shown = stored(db_driver, "Ada met Ben")
    unknown = str(uuid4())

    async with client() as api:
        answers = {
            "an unknown id": await api.get(f"/api/compare/Activity/{unknown}"),
            "a class not compared": await api.get(f"/api/compare/Factoid/{hidden_fac}"),
            "an entity": await api.get(f"/api/compare/Person/{ids['ada']}"),
            "not the statement's class": await api.get(
                f"/api/compare/Transfer/{hidden}"
            ),
            # (one the reader may see, of another class, by itself)
            "another class, visible": await api.get(f"/api/compare/Transfer/{shown}"),
            "no such class": await api.get(f"/api/compare/Nothing/{hidden}"),
            "a statement not visible": await api.get(f"/api/compare/Activity/{hidden}"),
        }
        not_an_id = await api.get("/api/compare/Activity/not-an-id")

    for what, response in answers.items():
        assert response.status_code == 404, what
        assert response.json()["detail"].startswith("There is no comparison of a "), (
            what
        )
    assert not_an_id.status_code == 422


# ---------------------------------------------------------------------------
# Nothing written; the ordinary write; what a lookup costs
# ---------------------------------------------------------------------------


@no_type_check
async def test_nothing_is_written_by_a_lookup_on_the_error_paths_too(
    clear_database, db_driver
):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids = await world(m)
    first = cite(db_driver, "Ada is born", "Birth")
    again = cite(db_driver, "Ada is born, again", "Birth")
    async with client() as api:
        ann = await bearer(api, "ann")
        await judge(api, ann, first, again, "agree")
        before = await settled(db_driver)

        for label, kind in [("Ada is born", "Birth"), ("Ada met Ben", "Activity"), ("to give", "Transfer"), ("gave", "Transfer")]:  # fmt: skip
            response = await api.get(f"/api/compare/{kind}/{stored(db_driver, label)}", headers=ann)  # fmt: skip
            assert response.status_code == 200, label
        for path in [
            f"/api/compare/Activity/{uuid4()}",
            f"/api/compare/Factoid/{ids['birth fac']}",
            f"/api/compare/Nothing/{first['id']}",
            f"/api/compare/Transfer/{first['id']}",
            "/api/compare/Activity/not-an-id",
        ]:
            assert (await api.get(path)).status_code in (404, 422), path

    assert counts(db_driver) == before


@no_type_check
async def test_a_judgement_that_cites_what_is_no_statement_is_refused_by_the_ordinary_write(
    clear_database, db_driver
):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids = await world(m)
    first = cite(db_driver, "Ada is born", "Birth")
    async with client() as api:
        ann = await bearer(api, "ann")
        before = await settled(db_driver)
        refused = {
            what: await api.post(
                "/api/StatementJudgement",
                json={
                    "type": "StatementJudgement",
                    "label": "no",
                    "verdict": "agree",
                    "statement": first,
                    "other": other,
                },  # fmt: skip
                headers=ann,
            )
            for what, other in {
                "a factoid": {"type": "Factoid", "id": ids["birth fac"]},
                "an entity": {"type": "Person", "id": ids["ada"]},
                "nothing": {"type": "Birth", "id": str(uuid4())},
            }.items()
        }
        anonymous = await api.post(
            "/api/StatementJudgement",
            json={
                "type": "StatementJudgement",
                "label": "no",
                "verdict": "agree",
                "statement": first,
                "other": first,
            },  # fmt: skip
        )

    for what, response in refused.items():
        assert response.status_code == 422, (what, response.text)
    assert anonymous.status_code == 401
    assert counts(db_driver) == before


# What one lookup runs (measured 2026-11-27, the same on both backends): one read transaction; `pairs_in`'s
# statements (as `PAIRS_OF_BUDGET` of the pairs' tests), the fit in use (step 6.6: one), the judgements of the pairs,
# and the labels. A statement with no pairs: no judgements are asked for
COMPARE_BUDGET = {
    "to give": (1, 10),
    "gave": (1, 10),
    "Ada met Ben": (1, 9),
    "alone": (1, 6),
}


@no_type_check
async def test_a_lookup_runs_its_budget_of_transactions_and_statements(
    clear_database, db_driver
):
    from pangloss_compare.compare import compare
    from pangloss_testing.conformance.test_query_costs import recorded
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids = await world(m)
    await factoid(m, "by herself", activity("alone", ids["eve"], ids["fay"]))
    async with client() as api:
        ann = await bearer(api, "ann")
        await judge(api, ann, cite(db_driver, "to give", "Transfer"), cite(db_driver, "gave", "Transfer"), "carried_out")  # fmt: skip
    await settled(db_driver)

    took = {}
    for label in COMPARE_BUDGET:
        id = stored(db_driver, label)
        with recorded() as r:
            await compare(id, True)
        took[label] = (r.transactions, len(r.statements))

    assert took == COMPARE_BUDGET


@no_type_check
async def test_one_pair_is_given_whether_found_or_not(clear_database, db_driver):
    """`?other=ID` (the page of two side by side): the entry of the two whatever the rule finds (a birth and a
    gathering of other people, which it does not pair), with what the maths says and every judgement of them, `found`
    "asked" and no reasons; one the rule does find, the same as the comparison has it; none for itself, an id of
    nothing, or one the reader may not see; not with `near`; the same 404s; the budget"""
    from pangloss_compare.compare import compare_pair
    from pangloss_testing.conformance.test_query_costs import recorded
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids = await world(m)
    await factoid(m, "Ben's birth", birth("Ben is born", ids["ben"], ids["mill"]))
    birth_id = stored(db_driver, "Ada is born")
    again = stored(db_driver, "Ada is born, again")
    bens = stored(db_driver, "Ben is born")
    async with client() as api:
        ann = await bearer(api, "ann")
        await judge(api, ann, cite(db_driver, "Ada is born", "Birth"), cite(db_driver, "Ben is born", "Birth"), "two_events", note="two people")  # fmt: skip
        unpaired = (await api.get(f"/api/compare/Birth/{birth_id}?other={bens}")).json()
        paired = (await api.get(f"/api/compare/Birth/{birth_id}?other={again}")).json()
        whole = (await api.get(f"/api/compare/Birth/{birth_id}")).json()
        itself = (
            await api.get(f"/api/compare/Birth/{birth_id}?other={birth_id}")
        ).json()
        nothing = (await api.get(f"/api/compare/Birth/{birth_id}?other=01a21c66-0000-7000-8000-000000000000")).json()  # fmt: skip
        both = await api.get(f"/api/compare/Birth/{birth_id}?other={bens}&near=true")
        missing = await api.get(
            f"/api/compare/Birth/01a21c66-0000-7000-8000-000000000000?other={bens}"
        )

    assert [e["other"]["id"] for e in whole["pairs"]] == [again]
    (entry,) = unpaired["pairs"]
    assert (
        entry["other"]["id"] == bens and entry["found"] == "asked" and entry["by"] == []
    )
    assert entry["workedOut"]["relation"] in ("two", "nothing")
    assert entry["relation"] == "two" and entry["judged"] == "two_events"
    assert [j["note"] for j in entry["judgements"]] == ["two people"]
    assert unpaired["statement"]["id"] == birth_id
    (same,) = paired["pairs"]
    assert same["relation"] == whole["pairs"][0]["relation"] == "agree"
    assert itself["pairs"] == [] and nothing["pairs"] == []
    assert both.status_code == 422, both.text
    assert missing.status_code == 404, missing.text

    with recorded() as r:
        await compare_pair(birth_id, bens, True)
    assert r.transactions == 1 and len(r.statements) <= 7, r.statements
