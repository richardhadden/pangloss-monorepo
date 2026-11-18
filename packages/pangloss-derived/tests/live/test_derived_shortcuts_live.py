"""Shortcut edges (`DerivedEdge.Meta(shortcut=True)`) on the backend under test: one beside each derived edge of the
class, written and deleted with it; a class that begins or stops asking for them; what the core and the reads of
derived edges make of them (nothing); merges, deletions and restored versions; the command"""

import json
from typing import Annotated, Any, no_type_check

import pytest
from pangloss_core import storage_of
from pangloss_models import (
    Document,
    Entity,
    Match,
    ModelRegistry,
    SemanticSpace,
    Trait,
    initialise,
)
from pangloss_testing.live import run

from pangloss_derived import (
    DerivedEdge,
    DerivesEdge,
    Object,
    PerJustification,
    RuleType,
    Subject,
    SymmetricLabel,
    Var,
    read,
    rule,
    shortcuts,
)
from pangloss_derived.worker import database, run_pending_derivations, worker

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
def models(
    same_group: bool = True,
    gave_to: bool = True,
    with_gifts: bool = True,
    declared: bool = False,
):
    """`same_group`, `gave_to`: whether the class asks for shortcuts. `with_gifts=False`: the rule of `GaveTo` and its
    class are not there. `declared`: an edge declared on `Meeting` (`Met`), with shortcuts"""
    # (a test declares the models again, as a project changed and started again would have them)
    ModelRegistry._reset()

    class Negative[T](SemanticSpace[T]):
        pass

    class Agent(Trait):
        pass

    class Person(Entity, Agent):
        _meta = Entity.Meta(create_with_id=True)
        knows: list[Person]

    class Group(Entity, Agent):
        pass

    class MemberOf(Document):
        member: Person
        group: Group

    class Transfer(Document):
        given_by: Agent
        given_to: Agent
        year: int
        amount: int

    class Factoid(Document):
        statements: list[MemberOf | Transfer | Negative[MemberOf | Transfer]]

    if declared:

        class Meeting(Document):
            _derives = [
                DerivesEdge(
                    "Met",
                    subject="present",
                    object="present",
                    symmetric=True,
                    shortcut=True,
                )
            ]
            present: list[Person]

    family = RuleType("family", "Ties of family")

    class SameGroup(DerivedEdge):
        """Members of the same group"""

        _meta = DerivedEdge.Meta(symmetric=True, shortcut=same_group)
        first: Annotated[Person, SymmetricLabel("member")]
        second: Annotated[Person, SymmetricLabel("member")]
        group: Group

    @rule(types=[family])
    def same_group_rule(a: Var[Person], b: Var[Person], g: Var[Group]):
        """Two people said to be members of one group"""
        return SameGroup.Derive(first=a, second=b, group=g).when(
            MemberOf.Where(member=a, group=g),
            MemberOf.Where(member=b, group=g),
        )

    if with_gifts:

        class GaveTo(DerivedEdge):
            """Gave something to"""

            _meta = DerivedEdge.Meta(shortcut=gave_to)
            giver: Annotated[Agent, Subject()]
            receiver: Annotated[Agent, Object(reverse_name="received_from")]
            year: int
            amount: Annotated[int, PerJustification()]

        @rule(types=[family])
        def gave_to_rule(a: Var[Agent], b: Var[Agent], y: Var[int], n: Var[int]):
            """A transfer from one agent to another"""
            return GaveTo.Derive(giver=a, receiver=b, year=y, amount=n).when(
                Transfer.Where(given_by=a, given_to=b, year=y, amount=n)
            )

    initialise()
    return locals()


async def entities(m) -> dict[str, Any]:
    n = {}
    for name in "ABCDE":
        n[name] = await m["Person"].Create(label=name, knows=[]).save()
    for name in "GH":
        n[name] = await m["Group"].Create(label=name).save()
    return n


def member(who, group):
    return {
        "type": "MemberOf",
        "label": "m",
        "member": {"type": "Person", "id": who.id},
        "group": {"type": "Group", "id": group.id},
    }


def transfer(giver, receiver, year=1500, amount=10, kinds=("Person", "Person")):
    return {
        "type": "Transfer",
        "label": "t",
        "given_by": {"type": kinds[0], "id": giver.id},
        "given_to": {"type": kinds[1], "id": receiver.id},
        "year": year,
        "amount": amount,
    }


async def says(m, label, *statements):
    return await m["Factoid"].Create(label=label, statements=list(statements)).save()


def stored(db_driver) -> list[tuple[str, str, str]]:
    """Every shortcut edge: from, the class, to (by label)"""
    rows = run(
        db_driver,
        "MATCH (a)-[e]->(b) WHERE e.derived RETURN a.label AS a, type(e) AS type, b.label AS b",
    )
    return sorted((r["a"], r["type"], r["b"]) for r in rows)


def beside(db_driver) -> list[dict]:
    """Each shortcut with the node of the derived edge of its key: whether they agree"""
    return run(
        db_driver,
        """
        MATCH (a)-[e]->(b) WHERE e.derived
        OPTIONAL MATCH (d:PGDerived {key: e.key})
        OPTIONAL MATCH (d)-[s]->(a) WHERE type(s) = d.pg_subject
        OPTIONAL MATCH (d)-[o]->(b) WHERE type(o) = d.pg_object
        RETURN type(e) AS type, d.type AS node, d.pg_shortcut AS marked, s IS NOT NULL AS from_subject,
               o IS NOT NULL AS to_object, properties(e) AS properties, a.id < b.id AS in_order
        """,
    )


def assert_one_beside_each(db_driver, *, classes: tuple[str, ...]) -> None:
    """The invariant: a shortcut exactly where there is a node of a class that asks for one, from its subject to its
    object, with its key and nothing else"""
    rows = beside(db_driver)
    for row in rows:
        assert row["node"] == row["type"], row
        assert row["marked"] is True and row["from_subject"] and row["to_object"], row
        assert sorted(row["properties"]) == ["derived", "key"], row
        assert row["properties"]["derived"] is True
        assert row["type"] in classes, row
        if row["type"] in ("SameGroup", "Met"):
            assert row["in_order"], row
    nodes = run(
        db_driver,
        "MATCH (d:PGDerived) RETURN d.type AS type, d.key AS key, d.pg_shortcut AS marked",
    )
    keys = [r["properties"]["key"] for r in rows]
    assert len(keys) == len(set(keys))
    assert sorted(keys) == sorted(n["key"] for n in nodes if n["type"] in classes)
    for node in nodes:
        assert (node["marked"] is True) == (node["type"] in classes), node


async def counted() -> dict[str, dict[str, int]]:
    db = database()

    @db.read_transaction
    async def read_counts(tx):
        return await shortcuts.counts(tx)

    return await read_counts()


# ---------------------------------------------------------------------------
# Written and deleted with the derived edge
# ---------------------------------------------------------------------------


@no_type_check
async def test_each_derived_edge_of_the_class_has_a_shortcut_beside_it(
    clear_database, db_driver
):
    m = models(gave_to=False)
    n = await entities(m)
    await says(m, "F1", member(n["A"], n["G"]), member(n["B"], n["G"]))
    await says(m, "F2", member(n["A"], n["H"]), member(n["B"], n["H"]))
    await says(m, "F3", member(n["C"], n["H"]), transfer(n["A"], n["B"]))
    await run_pending_derivations()

    # (one for each edge: A and B are of two groups, so two; and none for the class that does not ask)
    assert stored(db_driver) == [
        ("A", "SameGroup", "B"),
        ("A", "SameGroup", "B"),
        ("A", "SameGroup", "C"),
        ("B", "SameGroup", "C"),
    ]
    assert_one_beside_each(db_driver, classes=("SameGroup",))
    assert await counted() == {
        "SameGroup": {"edges": 4, "shortcuts": 4, "doubled": 0, "marked": 4}
    }
    # (what they are for: a path of them, with no hop through a node)
    reached = run(
        db_driver,
        "MATCH (a:Person {label: 'C'})-[:SameGroup*1..2]-(b:Person) RETURN DISTINCT b.label AS b ORDER BY b",
    )
    assert [r["b"] for r in reached if r["b"] != "C"] == ["A", "B"]
    # (and its key leads to the edge, with what qualifies it)
    of_group = run(
        db_driver,
        """
        MATCH (:Person {label: 'A'})-[e:SameGroup]-(:Person {label: 'B'})
        MATCH (d:PGDerived {key: e.key})-[:group]->(g)
        RETURN g.label AS g ORDER BY g
        """,
    )
    assert [r["g"] for r in of_group] == ["G", "H"]


@no_type_check
async def test_an_asymmetric_shortcut_goes_from_the_subject_to_the_object(
    clear_database, db_driver
):
    m = models()
    n = await entities(m)
    # (E was made after A: the direction is the gift's, not the order of the ids)
    await says(m, "F1", transfer(n["E"], n["A"], 1500, 1))
    await says(m, "F2", transfer(n["A"], n["G"], 1501, 1, kinds=("Person", "Group")))
    # (two gifts of one year are one edge, with two justifications; of another year, another edge)
    await says(m, "F3", transfer(n["E"], n["A"], 1500, 2))
    await says(m, "F4", transfer(n["E"], n["A"], 1502, 1))
    await run_pending_derivations()
    assert stored(db_driver) == [
        ("A", "GaveTo", "G"),
        ("E", "GaveTo", "A"),
        ("E", "GaveTo", "A"),
    ]
    assert_one_beside_each(db_driver, classes=("SameGroup", "GaveTo"))


@no_type_check
async def test_a_shortcut_goes_when_the_last_justification_of_its_edge_goes(
    clear_database, db_driver
):
    m = models()
    n = await entities(m)
    f1 = await says(m, "F1", member(n["A"], n["G"]), member(n["B"], n["G"]))
    f2 = await says(m, "F2", member(n["A"], n["G"]), member(n["B"], n["G"]))
    f3 = await says(m, "F3", transfer(n["A"], n["B"]))
    await run_pending_derivations()
    assert stored(db_driver) == [("A", "GaveTo", "B"), ("A", "SameGroup", "B")]

    # (found again in another document: still one)
    await says(m, "F4", member(n["A"], n["G"]), member(n["B"], n["G"]))
    await run_pending_derivations()
    assert stored(db_driver) == [("A", "GaveTo", "B"), ("A", "SameGroup", "B")]
    assert_one_beside_each(db_driver, classes=("SameGroup", "GaveTo"))

    await m["Factoid"].delete(f1.id)
    await run_pending_derivations()
    assert stored(db_driver) == [("A", "GaveTo", "B"), ("A", "SameGroup", "B")]
    await m["Factoid"].delete(f3.id)
    await run_pending_derivations()
    assert stored(db_driver) == [("A", "SameGroup", "B")]
    # (an update that says something else: the shortcut of what it no longer says goes, and the new one is there)
    await (
        m["Factoid"]
        .Update(
            id=f2.id,
            label="F2",
            statements=[member(n["C"], n["G"])],
        )
        .save()
    )
    (f4,) = [f for f in (await m["Factoid"].list()).results if f.label == "F4"]
    await m["Factoid"].delete(f4.id)
    await run_pending_derivations()
    assert stored(db_driver) == []
    assert run(db_driver, "MATCH (d:PGDerived) RETURN count(d) AS n") == [{"n": 0}]
    await m["Factoid"].undelete(f4.id)
    await run_pending_derivations()
    assert stored(db_driver) == [
        ("A", "SameGroup", "B"),
        ("A", "SameGroup", "C"),
        ("B", "SameGroup", "C"),
    ]
    assert_one_beside_each(db_driver, classes=("SameGroup", "GaveTo"))


@no_type_check
async def test_a_rebuild_writes_no_shortcut_twice(clear_database, db_driver):
    from pangloss_derived.registry import DerivedRegistry

    m = models()
    n = await entities(m)
    await says(m, "F1", member(n["A"], n["G"]), member(n["B"], n["G"]))
    await says(m, "F2", transfer(n["A"], n["B"]), transfer(n["B"], n["A"]))
    await run_pending_derivations()
    before = stored(db_driver)
    assert before == [
        ("A", "GaveTo", "B"),
        ("A", "SameGroup", "B"),
        ("B", "GaveTo", "A"),
    ]
    for checked in DerivedRegistry.all_checked().values():
        await worker.rebuild(checked)
    await worker.sync_rules(force=list(DerivedRegistry.all_checked()))
    assert stored(db_driver) == before
    assert_one_beside_each(db_driver, classes=("SameGroup", "GaveTo"))
    assert worker.shortcuts_synced == {}


# ---------------------------------------------------------------------------
# A class that begins to ask for them, or stops
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_class_that_begins_to_ask_gets_them_and_one_that_stops_loses_them(
    clear_database, db_driver
):
    m = models(same_group=False, gave_to=False)
    n = await entities(m)
    await says(m, "F1", member(n["A"], n["G"]), member(n["B"], n["G"]))
    await says(m, "F2", member(n["C"], n["G"]), transfer(n["A"], n["B"]))
    done = await run_pending_derivations()
    assert done["rules"] == {"same_group_rule": "built", "gave_to_rule": "built"}
    assert stored(db_driver) == []
    assert_one_beside_each(db_driver, classes=())
    assert await counted() == {}

    # the project says `shortcut=True` on one class, and starts again: no rule is built again
    models(same_group=True, gave_to=False)
    done = await run_pending_derivations()
    assert done["rules"] == {}
    assert worker.shortcuts_synced == {"SameGroup": {"written": 3}}
    assert stored(db_driver) == [
        ("A", "SameGroup", "B"),
        ("A", "SameGroup", "C"),
        ("B", "SameGroup", "C"),
    ]
    assert_one_beside_each(db_driver, classes=("SameGroup",))
    # (again: nothing to do)
    await run_pending_derivations()
    assert worker.shortcuts_synced == {}

    # the other class as well, and the first no longer
    models(same_group=False, gave_to=True)
    done = await run_pending_derivations()
    assert done["rules"] == {}
    assert worker.shortcuts_synced == {
        "GaveTo": {"written": 1},
        "(classes without shortcut)": {"deleted": 3},
    }
    assert stored(db_driver) == [("A", "GaveTo", "B")]
    assert_one_beside_each(db_driver, classes=("GaveTo",))

    # a class whose rule is gone: its edges go, and their shortcuts with them
    models(same_group=True, with_gifts=False)
    done = await run_pending_derivations()
    assert done["rules"] == {"gave_to_rule": "removed"}
    assert stored(db_driver) == [
        ("A", "SameGroup", "B"),
        ("A", "SameGroup", "C"),
        ("B", "SameGroup", "C"),
    ]
    assert_one_beside_each(db_driver, classes=("SameGroup",))


@no_type_check
async def test_the_shortcuts_are_written_and_deleted_a_few_at_a_time(
    clear_database, db_driver
):
    m = models(same_group=False, with_gifts=False)
    n = await entities(m)
    await says(m, "F1", *(member(n[p], n["G"]) for p in "ABCDE"))
    await run_pending_derivations()
    assert run(db_driver, "MATCH (d:PGDerived) RETURN count(d) AS n") == [{"n": 10}]

    models(same_group=True, with_gifts=False)
    assert await shortcuts.sync(database(), chunk=3) == {"SameGroup": {"written": 10}}
    assert len(stored(db_driver)) == 10
    assert_one_beside_each(db_driver, classes=("SameGroup",))
    assert await shortcuts.sync(database(), chunk=3) == {}

    # (taken away by hand: the nodes still say they have one, so they are forgotten and written again)
    run(db_driver, "MATCH ()-[e:SameGroup]->() WHERE e.derived DELETE e")
    assert (await counted())["SameGroup"] == {
        "edges": 10,
        "shortcuts": 0,
        "doubled": 0,
        "marked": 10,
    }
    assert await shortcuts.sync(database(), chunk=3) == {}
    assert await shortcuts.forget(database(), "SameGroup", chunk=4) == 10
    assert await shortcuts.sync(database(), chunk=10) == {"SameGroup": {"written": 10}}
    assert_one_beside_each(db_driver, classes=("SameGroup",))

    models(same_group=False, with_gifts=False)
    assert await shortcuts.sync(database(), chunk=4) == {
        "(classes without shortcut)": {"deleted": 10}
    }
    assert stored(db_driver) == []
    assert_one_beside_each(db_driver, classes=())


@no_type_check
async def test_an_edge_declared_on_a_document_class_can_have_shortcuts(
    clear_database, db_driver
):
    m = models(declared=True, same_group=False, with_gifts=False)
    n = await entities(m)
    ref = lambda p: {"type": "Person", "id": n[p].id}  # noqa: E731
    await m["Meeting"].Create(label="M", present=[ref("C"), ref("A"), ref("B")]).save()
    await run_pending_derivations()
    assert stored(db_driver) == [
        ("A", "Met", "B"),
        ("A", "Met", "C"),
        ("B", "Met", "C"),
    ]
    assert_one_beside_each(db_driver, classes=("Met",))
    assert DerivedEdge.named("Met")._meta.shortcut is True


# ---------------------------------------------------------------------------
# What reads make of them: nothing
# ---------------------------------------------------------------------------


async def everything_read(m, n) -> dict[str, Any]:
    """What the core and the reads of derived edges give for the entities, as JSON"""
    operations = storage_of().operations
    seen: dict[str, Any] = {}
    for name, entity in n.items():
        model = m["Group" if name in "GH" else "Person"]
        seen[f"get {name}"] = (await model.get(entity.id)).model_dump(mode="json")
        check = await operations.check_deletable(model, entity.id)
        seen[f"deletable {name}"] = (check.deletable, check.reference_count)
        section = await read.derived_of_entity(model, entity.id)
        seen[f"derived {name}"] = json.loads(json.dumps(section, default=str))
    for name in ("Person", "Group"):
        listed = await m[name].list(use_counts=True)
        seen[f"list {name}"] = ([r.label for r in listed.results], listed.use_counts)
        seen[f"used {name}"] = [
            r.label for r in (await m[name].list(used_only=True)).results
        ]
        seen[f"most used {name}"] = [
            r.label for r in (await m[name].autocomplete("")).results
        ]
    for name in ("SameGroup", "GaveTo"):
        page = await read.list_facts(m[name], page_size=100)
        seen[f"edges {name}"] = sorted(
            json.dumps(v.model_dump(mode="json"), sort_keys=True, default=str)
            for v in page["results"]
        )
    searches = {
        "in a group": {"$derived": {"type": "SameGroup"}},
        "gave or was given": {"$derived": {"type": "GaveTo"}},
        "knows someone": {"knows": {"exists": True}},
        "named by a person": {"$incoming": [{"type": "Person", "where": {}}]},
        "any A": {"$any": {"is": str(n["A"].id)}},
    }
    for name, where in searches.items():
        found = await m["Person"].search(Match(where=where))
        seen[f"search {name}"] = sorted(r.label for r in found.results)
    return seen


@no_type_check
async def test_the_reads_are_the_same_with_shortcuts_and_without(
    clear_database, db_driver
):
    m = models(same_group=False, gave_to=False)
    n = await entities(m)
    await says(m, "F1", member(n["A"], n["G"]), member(n["B"], n["G"]))
    await says(m, "F2", member(n["C"], n["G"]), transfer(n["A"], n["B"]))
    await says(m, "F3", transfer(n["B"], n["G"], kinds=("Person", "Group")))
    await (
        m["Person"]
        .Update(id=n["D"].id, label="D", knows=[{"type": "Person", "id": n["A"].id}])
        .save()
    )
    await run_pending_derivations()
    without = await everything_read(m, n)
    assert without["search in a group"] == ["A", "B", "C"]
    assert without["search gave or was given"] == ["A", "B"]
    assert without["deletable E"] == (True, 0)
    assert without["search any A"] == ["D"]

    m = models(same_group=True, gave_to=True)
    await run_pending_derivations()
    assert len(stored(db_driver)) == 5
    assert await everything_read(m, n) == without


# ---------------------------------------------------------------------------
# Entities merged, deleted and updated; versions restored
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_merge_leaves_no_shortcut_of_the_absorbed_entity_and_an_undo_brings_them_back(
    clear_database, db_driver
):
    m = models()
    n = await entities(m)
    await says(m, "F1", member(n["A"], n["G"]), member(n["C"], n["G"]))
    await says(m, "F2", member(n["B"], n["G"]))
    await says(m, "F3", transfer(n["B"], n["D"], 1500, 1))
    await says(m, "F4", transfer(n["D"], n["B"], 1501, 1))
    await run_pending_derivations()
    before = stored(db_driver)
    assert before == [
        ("A", "SameGroup", "B"),
        ("A", "SameGroup", "C"),
        ("B", "GaveTo", "D"),
        ("B", "SameGroup", "C"),
        ("D", "GaveTo", "B"),
    ]

    result = await m["Person"].merge(absorb=n["B"].id, into=n["A"].id)
    # (the merge itself moves none of them, and none is in its record)
    assert stored(db_driver) == before
    assert run(
        db_driver,
        "MATCH (move:PGMergeMove) WHERE move.pg_field IN ['SameGroup', 'GaveTo'] RETURN count(move) AS n",
    ) == [{"n": 0}]
    # (the worker takes away what was derived of the one absorbed, and derives it of the survivor)
    await run_pending_derivations()
    assert stored(db_driver) == [
        ("A", "GaveTo", "D"),
        ("A", "SameGroup", "C"),
        ("D", "GaveTo", "A"),
    ]
    assert_one_beside_each(db_driver, classes=("SameGroup", "GaveTo"))
    assert run(
        db_driver,
        "MATCH (b {id: $id})-[e]-() WHERE e.derived RETURN count(e) AS n",
        id=str(n["B"].id),
    ) == [{"n": 0}]

    await m["Person"].unmerge(result.merge.id)
    await run_pending_derivations()
    assert stored(db_driver) == before
    assert_one_beside_each(db_driver, classes=("SameGroup", "GaveTo"))


@no_type_check
async def test_an_update_of_an_entity_leaves_its_shortcuts_and_they_do_not_count_as_uses(
    clear_database, db_driver
):
    m = models()
    n = await entities(m)
    await says(m, "F1", member(n["A"], n["G"]), member(n["B"], n["G"]))
    await says(m, "F2", transfer(n["A"], n["B"]))
    await (
        m["Person"]
        .Update(id=n["A"].id, label="A", knows=[{"type": "Person", "id": n["B"].id}])
        .save()
    )
    await run_pending_derivations()
    there = [("A", "GaveTo", "B"), ("A", "SameGroup", "B")]
    assert stored(db_driver) == there

    # (an update of the entity writes its own relations again, and nothing else)
    await m["Person"].Update(id=n["A"].id, label="A", knows=[]).save()
    await m["Person"].Update(id=n["B"].id, label="B", knows=[]).save()
    await run_pending_derivations()
    assert stored(db_driver) == there
    assert (await m["Person"].get(n["A"].id)).knows == []
    # (what refers to it is the two statements, not the shortcuts)
    check = await storage_of().operations.check_deletable(m["Person"], n["A"].id)
    assert not check.deletable and check.reference_count == 2
    assert_one_beside_each(db_driver, classes=("SameGroup", "GaveTo"))


@no_type_check
async def test_a_group_that_qualifies_edges_is_merged_and_their_shortcuts_follow(
    clear_database, db_driver
):
    m = models()
    n = await entities(m)
    await says(m, "F1", member(n["A"], n["G"]), member(n["B"], n["G"]))
    await says(m, "F2", member(n["A"], n["H"]), member(n["B"], n["H"]))
    await run_pending_derivations()
    assert stored(db_driver) == [("A", "SameGroup", "B"), ("A", "SameGroup", "B")]
    await m["Group"].merge(absorb=n["H"].id, into=n["G"].id)
    await run_pending_derivations()
    # (two edges are one now: and one shortcut)
    assert stored(db_driver) == [("A", "SameGroup", "B")]
    assert_one_beside_each(db_driver, classes=("SameGroup", "GaveTo"))
