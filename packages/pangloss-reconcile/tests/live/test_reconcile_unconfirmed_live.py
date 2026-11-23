"""A guess no person has confirmed is no evidence, in reconciliation (step 10.5c of
implementation_docs/similarity-build-plan.md; the user's answer to row 16), on the backend under test, with
`pangloss_testing.similar_models` declared with `stand_in=True` and `suggested=True` (a participant may be a
toolchain's suggestion, and an `InRole` may hold one), the graph, name and class parts, and the profile `who`.

Three people named Jon Smyth (`a`, `b`, `c`), each met someone else elsewhere; a factoid of Ada's meeting with Ben
(`gathering`); and a stored factoid in which Ada met Ben and Jon Smyth, who is not identified, at the mill (`asked`).
A suggestion that Jon Smyth at Ada's gathering is `a`, `b` or `c` is added to the gathering (as a participant, or in
a role: a `WeightedAlternative` in the suggestion in an `InRole`), every part it had keeping its id. The candidates
of the asked mention before and after, the vectors refreshed: the same ids, scores and `shared`. Once the
suggestion is confirmed (an `Identification` of the same id), `a`, `b` and `c` are named with Ada and Ben, in
`shared` and so in the score. What the document asked about suggests itself is not among its entities either."""

from typing import Any, no_type_check

import pytest
from pangloss_models import hooks
from pangloss_testing.parts import drop_vector_indexes, one_turn
from pangloss_testing.parts.writes import (
    confirmed,
    in_role,
    participants_added,
    suggestion,
)
from pangloss_testing.similar_models import declare, mention_stand_in

pytestmark = pytest.mark.asyncio(loop_scope="session")

NAME = "Jon Smyth"
MENTION = {"type": "Mention", "label": NAME, "mentioned_type": "Person"}
NAMESAKES = ("a", "b", "c")


@pytest.fixture
def database(db_driver, clear_database):
    """(the database emptied, and the vector indexes the tests made dropped, before and after; `Mention` a stand-in
    for the whole test)"""
    drop_vector_indexes(db_driver)
    stand_in = mention_stand_in()
    hooks.stand_ins.append(stand_in)
    yield db_driver
    hooks.stand_ins.remove(stand_in)
    drop_vector_indexes(db_driver)


def ref(id: str, kind: str = "Person") -> dict[str, str]:
    return {"type": kind, "id": str(id)}


def meeting(by: str, *guests: dict[str, Any], at: str | None = None) -> dict:
    activity: dict[str, Any] = {
        "type": "Activity",
        "label": "a meeting",
        "carried_out_by": ref(by),
        "participants": [{"type": "InRole", "role": "guest", "target": list(guests)}],
    }
    if at is not None:
        activity["participants"][0]["at"] = ref(at, "Place")
    return activity


@no_type_check
async def world(m, database) -> dict[str, str]:
    """The people, the mill, the three Jon Smyths each with a meeting of their own, the gathering, and the stored
    factoid asked about (`mention`: its stand-in): every part rebuilt, the marks worked off"""
    from pangloss_vectors.rebuild import rebuild

    ids: dict[str, str] = {}
    for name in ["Ada", "Ben", "Cy", "Dee", "Eve"]:
        ids[name] = str((await m.Person.Create(label=name).save()).id)
    for name in NAMESAKES:
        ids[name] = str((await m.Person.Create(label=NAME).save()).id)
    ids["mill"] = str((await m.Place.Create(label="the mill").save()).id)
    for name, other in zip(NAMESAKES, ["Cy", "Dee", "Eve"], strict=True):
        await m.Factoid.Create(
            label=f"{name} met {other}",
            statements=[meeting(ids[name], ref(ids[other]))],
        ).save()
    gathering = await m.Factoid.Create(
        label="gathering", statements=[meeting(ids["Ada"], ref(ids["Ben"]))]
    ).save()
    ids["gathering"] = str(gathering.id)
    asked = await m.Factoid.Create(
        label="Ada met Ben and Jon",
        statements=[meeting(ids["Ada"], ref(ids["Ben"]), MENTION, at=ids["mill"])],
    ).save(detail=True)
    (mention,) = [
        str(t.id)
        for t in asked.statements[0].participants[0].target
        if t.type == "Mention"
    ]
    ids["mention"] = mention
    await rebuild()
    await one_turn(database)
    return ids


async def asked_of(ids: dict[str, str]) -> dict[str, tuple[float, dict, tuple]]:
    """The candidates of the stored mention, by id: score, scores, shared"""
    from pangloss_reconcile import candidates_of
    from pangloss_reconcile.stored import stored_plan

    plan = await stored_plan(ids["mention"])
    (found,) = await candidates_of(
        plan, see_unpublished=True, limit=10, only=[ids["mention"]]
    )
    return {c.id: (c.score, c.scores, c.shared) for c in found.candidates}


def assert_same(before: dict, after: dict) -> None:
    assert list(after) == list(before)
    for id, (score, scores, shared) in before.items():
        now_score, now_scores, now_shared = after[id]
        assert now_score == pytest.approx(score, abs=1e-6), id
        assert now_scores == pytest.approx(scores, abs=1e-6), id
        assert now_shared == shared, id


def suggested(ids: dict[str, str], where: str) -> dict:
    """A suggestion that Jon Smyth is `a`, `b` or `c`, as a participant or in a role"""
    held = suggestion(ids, ("a", 50), ("b", 30), ("c", 20))
    return held if where == "a participant" else in_role("guest", held)


@pytest.mark.parametrize("where", ["a participant", "in a role"])
@no_type_check
async def test_a_stored_suggestion_changes_no_candidate_s_score_nor_what_it_shares_and_once_confirmed_it_counts(
    database, where
):
    m = declare(stand_in=True, suggested=True)
    ids = await world(m, database)
    before = await asked_of(ids)
    assert {ids[n] for n in NAMESAKES} <= set(before)
    assert all(before[ids[n]][2] == () for n in NAMESAKES)

    await participants_added(m, ids["gathering"], suggested(ids, where))
    assert await one_turn(database) > 0
    assert_same(before, await asked_of(ids))

    await confirmed(m, ids["gathering"])
    assert await one_turn(database) > 0
    after = await asked_of(ids)
    for name in NAMESAKES:
        id = ids[name]
        assert dict(after[id][2]) == {ids["Ada"]: 1, ids["Ben"]: 1}, name
        assert after[id][0] > before[id][0], name


@no_type_check
async def test_with_the_hook_empty_what_a_suggestion_names_would_be_shared(
    database, monkeypatch
):
    """(that the test above is not empty: without `hooks.unconfirmed`, as before step 10.5c, the suggestion stored
    would count in `shared`)"""
    from pangloss_reconcile.reasons import shared
    from pangloss_reconcile.stored import stored_plan

    m = declare(stand_in=True, suggested=True)
    ids = await world(m, database)
    await participants_added(m, ids["gathering"], suggested(ids, "in a role"))
    plan = await stored_plan(ids["mention"])
    namesakes = [ids[n] for n in NAMESAKES]
    assert await shared(plan, namesakes, True) == {}
    monkeypatch.setattr(hooks, "unconfirmed", [])
    found = await shared(plan, namesakes, True)
    assert {id: dict(pairs) for id, pairs in found.items()} == {
        id: {ids["Ada"]: 1, ids["Ben"]: 1} for id in namesakes
    }


@no_type_check
async def test_what_the_document_asked_about_suggests_is_not_among_its_entities_until_confirmed(
    database,
):
    """A payload in which Ada met Jon Smyth and someone suggested to be Cy: `a`, who met Cy elsewhere, shares
    nothing with it; with the same written as an identification, `a` shares Cy"""
    from pangloss_cypher.write_functions import checked_create
    from pangloss_reconcile.reasons import shared

    m = declare(stand_in=True, suggested=True)
    ids = await world(m, database)

    def payload(kind: str) -> dict:
        guessed = {**suggestion(ids, ("Cy", 100)), "type": kind}
        if kind == "Identification":
            guessed["identified_by"] = "a-person"
        activity = meeting(ids["Ada"], MENTION)
        activity["participants"].append(guessed)
        return {"type": "Factoid", "label": "Ada met Jon", "statements": [activity]}

    _, plan, _ = await checked_create(
        m.Factoid.Create(**payload("IdentificationByToolchain"))
    )
    assert await shared(plan, [ids["a"]], True) == {}
    _, plan, _ = await checked_create(m.Factoid.Create(**payload("Identification")))
    assert await shared(plan, [ids["a"]], True) == {ids["a"]: [(ids["Cy"], 1)]}
