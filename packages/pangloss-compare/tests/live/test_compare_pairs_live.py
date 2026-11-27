"""The statements a statement is compared with, by rule (`pangloss_compare.pairs`;
implementation_docs/spaces-and-comparison-plan.md, step 6.3), on the backend under test, with
`similar_models.declare(compared=True, ...)`: each part of the rule by name, what is never a reason (a stand-in, a
guess not confirmed, a wrapper's own relation), what the reader may see, merged entities both ways, the cut, that
nothing is written, and what it costs."""

from typing import Any, no_type_check
from uuid import uuid4

import pytest
from pangloss_compare.pairs import Pairs, by_rule, pairs_of
from pangloss_models import hooks
from pangloss_testing.live import run

pytestmark = pytest.mark.asyncio(loop_scope="session")

PEOPLE = ["ada", "ben", "cy", "dee", "eve", "fay", "gus", "maker", "orderer", "doer", "receiver"]  # fmt: skip


def ref(id: str, kind: str = "Person") -> dict[str, str]:
    return {"type": kind, "id": id}


def role(*people: str, at: str | None = None) -> dict[str, Any]:
    held: dict[str, Any] = {"type": "InRole", "role": "guest", "target": [ref(p) for p in people]}  # fmt: skip
    if at is not None:
        held["at"] = ref(at, "Place")
    return held


def activity(label: str, by: str, *participants: Any) -> dict[str, Any]:
    return {
        "type": "Activity",
        "label": label,
        "carried_out_by": ref(by),
        "participants": [p if isinstance(p, dict) else role(p) for p in participants],
    }


@no_type_check
async def entities(m) -> dict[str, str]:
    ids = {name: str((await m.Person.Create(label=name).save()).id) for name in PEOPLE}
    ids["mill"] = str((await m.Place.Create(label="the mill").save()).id)
    ids["guild"] = str((await m.Group.Create(label="the guild").save()).id)
    ids["picture"] = str((await m.Picture.Create(label="a picture").save()).id)
    return ids


@no_type_check
async def factoid(m, label: str, *statements: dict, **saved: Any) -> str:
    """A factoid of these statements: its id"""
    return str((await m.Factoid.Create(label=label, statements=list(statements)).save(**saved)).id)  # fmt: skip


def stored(db_driver, label: str) -> str:
    """The id of the document of this label"""
    (row,) = run(
        db_driver,
        "MATCH (n:PGIndexableNode {label: $label}) WHERE n:Document RETURN n.id AS id",
        label=label,
    )
    return row["id"]


async def pairs(db_driver, label: str, see_unpublished: bool = True, most: int = 200) -> Pairs:  # fmt: skip
    """The pairs by rule of the statement of this label, in a read transaction"""
    from pangloss_core import backend

    id = stored(db_driver, label)
    database = backend.current().database()

    @database.read_transaction
    async def go(tx):
        return await by_rule(tx, id, see_unpublished=see_unpublished, most=most)

    return await go()


def found(db_driver, result: Pairs) -> dict[str, set[tuple[str, str, str]]]:
    """The pairs by the labels of the statements found, each with its reasons"""
    labels = {
        r["id"]: r["label"]
        for r in run(
            db_driver,
            "UNWIND $ids AS id MATCH (n:PGIndexableNode {id: id}) RETURN n.id AS id, n.label AS label",
            ids=[p.id for p in result.found],
        )
    }
    return {labels[p.id]: set(p.by) for p in result.found}


def counts(db_driver) -> tuple[int, int, int]:
    """The nodes, the edges and the `PGPending` marks"""
    return (
        run(db_driver, "MATCH (n) RETURN count(n) AS n")[0]["n"],
        run(db_driver, "MATCH ()-[r]->() RETURN count(r) AS n")[0]["n"],
        run(db_driver, "MATCH (p:PGPending) RETURN count(p) AS n")[0]["n"],
    )


async def settled(db_driver) -> tuple[int, int, int]:
    """The counts once the workers have done with the writes made so far (a mark of a write is a node a worker takes
    away a moment later): the same three times running, a quarter of a second apart (as reconcile's tests wait)"""
    import asyncio

    seen = [counts(db_driver)]
    for _ in range(80):
        await asyncio.sleep(0.25)
        seen.append(counts(db_driver))
        if len(seen) >= 3 and seen[-1] == seen[-2] == seen[-3]:
            break
    return seen[-1]


# ---------------------------------------------------------------------------
# The rule, part by part
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_statement_pairs_with_another_that_names_an_entity_in_the_same_field_and_not_in_another(
    clear_database, db_driver
):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids = await entities(m)
    await factoid(m, "one", activity("Ada met Ben", ids["ada"], ids["ben"]))
    await factoid(m, "two", activity("Cy met Ben", ids["cy"], ids["ben"]))
    # (Ben in another field: he met Dee)
    await factoid(m, "three", activity("Ben met Dee", ids["ben"], ids["dee"]))

    assert found(db_driver, await pairs(db_driver, "Ada met Ben")) == {
        "Cy met Ben": {("participants", ids["ben"], "rule")}
    }
    assert found(db_driver, await pairs(db_driver, "Ben met Dee")) == {}


@no_type_check
async def test_related_classes_pair_and_unrelated_ones_do_not(
    clear_database, db_driver
):
    """A making and the painting of a picture (`picture_made` narrows `made`); a birth of the maker is of a class
    neither above nor below"""
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids = await entities(m)
    await factoid(m, "a making", {"type": "Making", "label": "made", "made_by": ref(ids["maker"]), "made": ref(ids["picture"], "Picture")})  # fmt: skip
    await factoid(m, "a painting", {"type": "MakingOfPicture", "label": "painted", "made_by": ref(ids["maker"]), "picture_made": ref(ids["picture"], "Picture")})  # fmt: skip
    await factoid(m, "a birth", {"type": "Birth", "label": "born", "person": ref(ids["maker"])})  # fmt: skip

    both = {("made", ids["picture"], "rule"), ("made_by", ids["maker"], "rule")}
    assert found(db_driver, await pairs(db_driver, "made")) == {"painted": both}
    assert found(db_driver, await pairs(db_driver, "painted")) == {"made": both}
    assert found(db_driver, await pairs(db_driver, "born")) == {}


@no_type_check
async def test_two_statements_of_one_factoid_pair(clear_database, db_driver):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids = await entities(m)
    await factoid(
        m,
        "told twice",
        activity("Ada met Ben", ids["ada"], ids["ben"]),
        activity("Ada met Ben again", ids["ada"], ids["ben"]),
    )

    assert found(db_driver, await pairs(db_driver, "Ada met Ben")) == {
        "Ada met Ben again": {
            ("carried_out_by", ids["ada"], "rule"),
            ("participants", ids["ben"], "rule"),
        }
    }


@no_type_check
async def test_a_wrapper_s_own_relation_pairs_nothing(clear_database, db_driver):
    """Two gatherings at the mill (`InRole.at`) of other people: the place of a role is not a participant"""
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids = await entities(m)
    await factoid(m, "one", activity("Ada met Ben at the mill", ids["ada"], role(ids["ben"], at=ids["mill"])))  # fmt: skip
    await factoid(m, "two", activity("Cy met Dee at the mill", ids["cy"], role(ids["dee"], at=ids["mill"])))  # fmt: skip

    assert found(db_driver, await pairs(db_driver, "Ada met Ben at the mill")) == {}


def order(ids, label: str, thing: dict, space: str = "Ordered") -> dict:
    return {
        "type": "Order",
        "label": label,
        "ordered_by": ref(ids["orderer"]),
        "ordered_to": [ref(ids["doer"])],
        "thing_ordered": {"type": space, "contents": [thing]},
    }


def giving(label: str, by: str, to: str, kind: str = "Person") -> dict:
    return {"type": "Transfer", "label": label, "given_by": ref(by), "given_to": ref(to, kind)}  # fmt: skip


@no_type_check
async def test_what_is_prescribed_also_pairs_with_what_names_whom_it_is_prescribed_to_in_any_identifying_field(
    clear_database, db_driver
):
    """The doer is ordered to give to the receiver: what the doer did pairs by the rule and as the addressee's; a
    gift to the doer (the addressee in another field) as the addressee's only; the doer at an assembly is of a class
    that is not related"""
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids = await entities(m)
    await factoid(m, "an order", order(ids, "the order", giving("to give", ids["doer"], ids["receiver"])))  # fmt: skip
    await factoid(m, "what came of it", giving("gave", ids["doer"], ids["receiver"]))
    await factoid(m, "a gift to the doer", giving("given to the doer", ids["eve"], ids["doer"]))  # fmt: skip
    await factoid(m, "a gift by another", giving("another gave", ids["fay"], ids["gus"]))  # fmt: skip
    await factoid(m, "an assembly", {"type": "Attendance", "label": "at the assembly", "attended_by": ref(ids["doer"]), "assembly_of": ref(ids["guild"], "Group")})  # fmt: skip

    assert found(db_driver, await pairs(db_driver, "to give")) == {
        "gave": {
            ("given_by", ids["doer"], "rule"),
            ("given_to", ids["receiver"], "rule"),
            ("given_by", ids["doer"], "addressee"),
        },
        "given to the doer": {("given_to", ids["doer"], "addressee")},
    }
    # (what is not prescribed has no addressee: the gift to the doer is no pair of what the doer did)
    assert found(db_driver, await pairs(db_driver, "gave")) == {
        "to give": {
            ("given_by", ids["doer"], "rule"),
            ("given_to", ids["receiver"], "rule"),
        }
    }


@no_type_check
async def test_at_most_so_many_pairs_those_of_the_most_reasons_first_then_by_id(
    clear_database, db_driver
):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids = await entities(m)
    await factoid(m, "asked", activity("Ada met Ben", ids["ada"], ids["ben"]))
    # (one with two reasons, and four with one)
    await factoid(m, "both", activity("Ada met Ben once more", ids["ada"], ids["ben"]))  # fmt: skip
    for n, host in enumerate(["cy", "dee", "eve", "fay"]):
        await factoid(m, f"other {n}", activity(f"{host} met Ben", ids[host], ids["ben"]))  # fmt: skip

    every = await pairs(db_driver, "Ada met Ben")
    assert len(every.found) == 5 and not every.more
    assert every.found[0].id == stored(db_driver, "Ada met Ben once more")
    assert [p.id for p in every.found[1:]] == sorted(p.id for p in every.found[1:])

    cut = await pairs(db_driver, "Ada met Ben", most=3)
    assert cut == Pairs(every.found[:3], more=True)
    assert (await pairs(db_driver, "Ada met Ben", most=5)).more is False


@no_type_check
async def test_a_statement_that_is_not_compared_or_not_there_gives_no_pairs(
    clear_database, db_driver
):
    """A statement of a class with no rules, an id of nothing, an entity, and a statement inside a space that is
    `CompareMeta(compared=False)`: an empty answer, as for what the reader may not see"""
    from pangloss_compare import CompareMeta
    from pangloss_core import backend
    from pangloss_models import ModelRegistry
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids = await entities(m)
    await factoid(m, "a member", {"type": "MemberOf", "label": "Ada is a member", "member": ref(ids["ada"]), "group": ref(ids["guild"], "Group")})  # fmt: skip
    await factoid(m, "met", activity("Ada met Ben", ids["ada"], ids["ben"]))
    await factoid(m, "denied", {"type": "Negative", "contents": [activity("Ada did not meet Ben", ids["ada"], ids["ben"])]})  # fmt: skip
    database = backend.current().database()

    @database.read_transaction
    async def asked(tx, id):
        return await by_rule(tx, id, see_unpublished=True, most=10)

    for id in [stored(db_driver, "Ada is a member"), str(uuid4()), ids["ada"]]:
        assert await asked(id) == Pairs()
    assert len((await pairs(db_driver, "Ada met Ben")).found) == 1

    ModelRegistry._model_dict["Negative"]._compare_meta = CompareMeta(compared=False)
    try:
        assert await asked(stored(db_driver, "Ada did not meet Ben")) == Pairs()
        # (nor is what is inside it found)
        assert await pairs(db_driver, "Ada met Ben") == Pairs()
    finally:
        del ModelRegistry._model_dict["Negative"]._compare_meta
    # (and `pairs_of` gives no statement)
    assert await pairs_of(str(uuid4()), True) == (None, {}, Pairs())


# ---------------------------------------------------------------------------
# Real entities only
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_stand_in_never_pairs(clear_database, db_driver):
    """A mention not identified (`Mention`, a stand-in document) is no entity; nor is what the criteria of a
    `MatchesCriteria` compute (the candidates its worker finds, a relation the server computes)"""
    from pangloss_criteria import run_pending
    from pangloss_testing.similar_models import declare, mention_stand_in

    stand_in = mention_stand_in()
    hooks.stand_ins.append(stand_in)
    try:
        m = declare(compared=True, stand_in=True)
        ids = await entities(m)
        mention = {"type": "Mention", "label": "someone", "mentioned_type": "Person"}
        await factoid(m, "one", activity("Ada met someone", ids["ada"], {"type": "InRole", "role": "guest", "target": [mention]}))  # fmt: skip
        await factoid(m, "two", activity("Cy met someone", ids["cy"], {"type": "InRole", "role": "guest", "target": [{**mention, "label": "someone else"}]}))  # fmt: skip
        await factoid(m, "members", {"type": "MemberOf", "label": "Ben is a member", "member": ref(ids["ben"]), "group": ref(ids["guild"], "Group")})  # fmt: skip

        def described(label: str, to: str) -> dict:
            return {
                "type": "Transfer",
                "label": label,
                "given_by": {
                    "type": "MatchesCriteria",
                    "wording": "a member of the guild",
                    "criteria": {
                        "type": "Person",
                        "where": {
                            "$incoming": [
                                {
                                    "type": "MemberOf",
                                    "field": "member",
                                    "where": {"group": {"is": ids["guild"]}},
                                }
                            ]
                        },
                    },  # fmt: skip
                },
                "given_to": ref(to),
            }

        await factoid(m, "a member gave", described("a member gave to Dee", ids["dee"]))
        await factoid(m, "a member gave again", described("a member gave to Eve", ids["eve"]))  # fmt: skip
        await factoid(m, "Ben gave", giving("Ben gave to Fay", ids["ben"], ids["fay"]))
        await run_pending()
        # (the criteria found Ben)
        assert run(
            db_driver,
            "MATCH (:MatchesCriteria)-[e:target]->(p:Person) WHERE NOT coalesce(e.reverse, false) RETURN p.id AS id",
        ) == [{"id": ids["ben"]}, {"id": ids["ben"]}]

        assert found(db_driver, await pairs(db_driver, "Ada met someone")) == {}
        for label in [
            "a member gave to Dee",
            "a member gave to Eve",
            "Ben gave to Fay",
        ]:
            assert found(db_driver, await pairs(db_driver, label)) == {}, label
    finally:
        hooks.stand_ins.remove(stand_in)


@no_type_check
async def test_a_suggestion_not_confirmed_never_pairs_and_does_once_confirmed(
    clear_database, db_driver
):
    """A toolchain's suggestion that a participant is Ben (a `WeightedAlternative` in an
    `IdentificationByToolchain`), as a participant and in a role; once confirmed (an `Identification`), Ben is"""
    from pangloss_testing.parts.writes import confirmed, in_role, suggestion
    from pangloss_testing.similar_models import declare

    m = declare(compared=True, suggested=True)
    ids = await entities(m)
    guessed = await factoid(
        m,
        "guessed",
        activity(
            "Ada met someone", ids["ada"], suggestion(ids, ("ben", 60), ("cy", 40))
        ),  # fmt: skip
    )
    in_a_role = await factoid(
        m,
        "guessed in a role",
        activity(
            "Dee met someone",
            ids["dee"],
            in_role("guest", suggestion(ids, ("ben", 100))),
        ),  # fmt: skip
    )
    await factoid(m, "known", activity("Eve met Ben", ids["eve"], ids["ben"]))

    assert found(db_driver, await pairs(db_driver, "Eve met Ben")) == {}
    assert found(db_driver, await pairs(db_driver, "Ada met someone")) == {}

    await confirmed(m, guessed)
    await confirmed(m, in_a_role)

    ben = ("participants", ids["ben"], "rule")
    assert found(db_driver, await pairs(db_driver, "Eve met Ben")) == {
        "Ada met someone": {ben},
        "Dee met someone": {ben},
    }
    assert found(db_driver, await pairs(db_driver, "Ada met someone")) == {
        "Eve met Ben": {ben},
        "Dee met someone": {ben},
    }


@no_type_check
async def test_other_entities_are_never_found_below_a_suggestion_not_confirmed_nor_in_a_space_not_compared(
    clear_database, db_driver
):
    """`naming`, the rule for entities near the statement's (step 6.4), as the rule's own: of the statements naming
    Ben's namesake, not one where he is only suggested (until confirmed), nor one inside a space that is
    `CompareMeta(compared=False)`"""
    from pangloss_compare import CompareMeta
    from pangloss_compare.pairs import naming
    from pangloss_compare.reading import read
    from pangloss_core import backend
    from pangloss_models import ModelRegistry
    from pangloss_testing.parts.writes import confirmed, suggestion
    from pangloss_testing.similar_models import declare

    m = declare(compared=True, suggested=True)
    ids = await entities(m)
    ids["ben2"] = str((await m.Person.Create(label="ben").save()).id)
    await factoid(m, "asked", activity("Ada met Ben", ids["ada"], ids["ben"]))
    guessed = await factoid(m, "guessed", activity("Gus met someone", ids["gus"], suggestion(ids, ("ben2", 100))))  # fmt: skip
    await factoid(m, "named", activity("Fay met Ben too", ids["fay"], ids["ben2"]))
    await factoid(m, "denied", {"type": "Negative", "contents": [activity("Eve did not meet Ben", ids["eve"], ids["ben2"])]})  # fmt: skip
    database = backend.current().database()
    asked = stored(db_driver, "Ada met Ben")

    @database.read_transaction
    async def named(tx):
        told = (await read(tx, [asked], see_unpublished=True))[asked]
        found = await naming(tx, told, {"participants": [ids["ben2"]]}, see_unpublished=True)  # fmt: skip
        return {id: set(by) for id, by in found.named.items()}

    ben2 = {("participants", ids["ben2"])}
    labels = {stored(db_driver, label): label for label in ("Fay met Ben too", "Eve did not meet Ben", "Gus met someone")}  # fmt: skip
    assert {labels[id]: by for id, by in (await named()).items()} == {
        "Fay met Ben too": ben2,
        "Eve did not meet Ben": ben2,
    }
    ModelRegistry._model_dict["Negative"]._compare_meta = CompareMeta(compared=False)
    try:
        assert {labels[id] for id in await named()} == {"Fay met Ben too"}
    finally:
        del ModelRegistry._model_dict["Negative"]._compare_meta
    await confirmed(m, guessed)
    assert {labels[id] for id in await named()} == {
        "Fay met Ben too",
        "Eve did not meet Ben",
        "Gus met someone",
    }


@no_type_check
async def test_an_entity_merged_into_another_pairs_as_the_one_kept_both_ways(
    clear_database, db_driver
):
    """Ada's gathering names Ben, Cy's names Ben's double: once the double is merged into Ben, the merge has moved
    the reference, and each pairs with the other by Ben. A reference a merge has not moved (a field it keeps, or one
    written before its second pass), marked here by hand as a merge leaves it, pairs the same way, in both
    directions"""
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids = await entities(m)
    double = str((await m.Person.Create(label="Ben's double").save()).id)
    await factoid(m, "one", activity("Ada met Ben", ids["ada"], ids["ben"]))
    await factoid(m, "two", activity("Cy met the double", ids["cy"], double))
    assert found(db_driver, await pairs(db_driver, "Ada met Ben")) == {}

    await m.Person.merge(absorb=double, into=ids["ben"])
    ben = ("participants", ids["ben"], "rule")
    assert found(db_driver, await pairs(db_driver, "Ada met Ben")) == {"Cy met the double": {ben}}  # fmt: skip
    assert found(db_driver, await pairs(db_driver, "Cy met the double")) == {"Ada met Ben": {ben}}  # fmt: skip

    # (a reference left with the one absorbed: Dee's gathering names Eve, merged into Fay as a merge marks it)
    await factoid(m, "three", activity("Dee met Eve", ids["dee"], ids["eve"]))
    await factoid(m, "four", activity("Gus met Fay", ids["gus"], ids["fay"]))
    run(
        db_driver,
        "MATCH (e:PGIndexableNode {id: $eve}) SET e.merged_into = $fay "
        "CREATE (:PGMerge {id: $merge, survivor: $fay, absorbed: $eve, state: 'done'})",
        eve=ids["eve"],
        fay=ids["fay"],
        merge=str(uuid4()),
    )
    fay = ("participants", ids["fay"], "rule")
    assert found(db_driver, await pairs(db_driver, "Dee met Eve")) == {"Gus met Fay": {fay}}  # fmt: skip
    assert found(db_driver, await pairs(db_driver, "Gus met Fay")) == {"Dee met Eve": {fay}}  # fmt: skip
    # (and the reading has the one kept)
    statement, others, _ = await pairs_of(stored(db_driver, "Dee met Eve"), True)
    assert statement.fields["participants"] == {ids["fay"]}
    assert [told.fields["participants"] for told in others.values()] == [{ids["fay"]}]


# ---------------------------------------------------------------------------
# What the reader may see
# ---------------------------------------------------------------------------


@no_type_check
async def test_an_unpublished_factoid_is_paired_only_for_a_reader_who_may_see_it(
    clear_database, db_driver
):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True, reviewed=True)
    ids = await entities(m)
    await factoid(m, "published", activity("Ada met Ben", ids["ada"], ids["ben"]), published=True)  # fmt: skip
    await factoid(m, "not published", activity("Cy met Ben", ids["cy"], ids["ben"]), published=False)  # fmt: skip
    ben = ("participants", ids["ben"], "rule")

    assert found(db_driver, await pairs(db_driver, "Ada met Ben", see_unpublished=False)) == {}  # fmt: skip
    assert found(db_driver, await pairs(db_driver, "Ada met Ben", see_unpublished=True)) == {"Cy met Ben": {ben}}  # fmt: skip
    # (nor does a reader not logged in see what an unpublished statement pairs with)
    assert await pairs(db_driver, "Cy met Ben", see_unpublished=False) == Pairs()
    assert found(db_driver, await pairs(db_driver, "Cy met Ben", see_unpublished=True)) == {"Ada met Ben": {ben}}  # fmt: skip
    hidden = stored(db_driver, "Cy met Ben")
    assert await pairs_of(hidden, False) == (None, {}, Pairs())
    statement, others, found_ = await pairs_of(hidden, True)
    assert statement.id == hidden and set(others) == {p.id for p in found_.found}


# ---------------------------------------------------------------------------
# Nothing written, and what it costs
# ---------------------------------------------------------------------------


@no_type_check
async def world(m) -> dict[str, str]:
    """An order and what came of it, a gathering told twice, a making and a painting"""
    ids = await entities(m)
    await factoid(m, "an order", order(ids, "the order", giving("to give", ids["doer"], ids["receiver"])))  # fmt: skip
    await factoid(m, "what came of it", giving("gave", ids["doer"], ids["receiver"]))
    await factoid(m, "one", activity("Ada met Ben", ids["ada"], role(ids["ben"], at=ids["mill"]), ids["cy"]))  # fmt: skip
    await factoid(m, "two", activity("Ada met Ben again", ids["ada"], ids["ben"]))
    await factoid(m, "a making", {"type": "Making", "label": "made", "made_by": ref(ids["maker"]), "made": ref(ids["picture"], "Picture")})  # fmt: skip
    await factoid(m, "a painting", {"type": "MakingOfPicture", "label": "painted", "made_by": ref(ids["maker"]), "picture_made": ref(ids["picture"], "Picture")})  # fmt: skip
    return ids


ASKED = ["to give", "gave", "Ada met Ben", "made", "painted"]


@no_type_check
async def test_nothing_is_written(clear_database, db_driver):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    await world(m)
    before = await settled(db_driver)

    for label in ASKED:
        assert (await pairs(db_driver, label)).found, label
        statement, others, found_ = await pairs_of(stored(db_driver, label), True)
        assert statement is not None and len(others) == len(found_.found)
    await pairs_of(str(uuid4()), False)

    assert counts(db_driver) == before


# What `pairs_of` runs (measured 2026-11-27, the same on both backends): one read transaction; the statement read
# (its node and the entities of its fields; the node that prescribes it, of what is prescribed), the ids absorbed into
# its entities, the others that name them, and the others read (their nodes, their entities, and the nodes that
# prescribe them where one is). A change that adds a round trip fails here
PAIRS_OF_BUDGET = {
    "to give": (1, 7),
    "gave": (1, 7),
    "Ada met Ben": (1, 6),
}


@no_type_check
async def test_pairs_of_runs_its_budget_of_transactions_and_statements(
    clear_database, db_driver
):
    from pangloss_testing.conformance.test_query_costs import recorded
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    await world(m)
    await settled(db_driver)
    took = {}
    for label in PAIRS_OF_BUDGET:
        id = stored(db_driver, label)
        with recorded() as r:
            await pairs_of(id, True)
        took[label] = (r.transactions, len(r.statements))

    assert took == PAIRS_OF_BUDGET


@no_type_check
async def test_finding_the_pairs_does_no_more_work_when_the_database_has_more_in_it(
    clear_database, db_driver
):
    """The work of `pairs_of` for each statement alone, and again with two hundred other gatherings, transfers and
    makings of other people: a query that starts from the entities and walks does the same work; one that scans a
    class does more. Measured with fresh plans, and on Memgraph with the plans made before the others were there"""
    from pangloss_testing.backends import under_test
    from pangloss_testing.conformance.test_query_costs import (
        SLACK,
        forget_statistics,
        recorded,
        replan,
        work,
    )
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    await world(m)
    asked = {label: stored(db_driver, label) for label in ASKED}

    async def work_of_each() -> dict[str, int]:
        # (the workers done with what was written: their statements would be counted too)
        await settled(db_driver)
        done = {}
        for label, id in asked.items():
            with recorded() as r:
                await pairs_of(id, True)
            done[label] = work(db_driver, r.reads())
        return done

    replan(db_driver)
    alone = await work_of_each()
    for n in range(70):
        one = str((await m.Person.Create(label=f"someone {n}").save()).id)
        two = str((await m.Person.Create(label=f"someone else {n}").save()).id)
        thing = str((await m.Picture.Create(label=f"thing {n}").save()).id)
        await factoid(
            m,
            f"others {n}",
            activity(f"{n}: one met two", one, role(two)),
            giving(f"{n}: one gave to two", one, two),
            {
                "type": "MakingOfPicture",
                "label": f"{n}: painted",
                "made_by": ref(one),
                "picture_made": ref(thing, "Picture"),
            },  # fmt: skip
        )
    rounds = {}
    if under_test().name == "memgraph":
        rounds["among the others, planned when it was alone"] = await work_of_each()
    replan(db_driver)
    rounds["among the others"] = await work_of_each()
    try:
        grew = {
            f"{label}, {round}": (alone[label], crowded[label])
            for round, crowded in rounds.items()
            for label in asked
            if crowded[label] > alone[label] + SLACK
        }
        assert not grew, f"(work alone, work then): {grew}"
    finally:
        forget_statistics(db_driver)
