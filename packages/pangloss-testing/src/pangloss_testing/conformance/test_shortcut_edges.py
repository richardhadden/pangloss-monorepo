"""A shortcut of a derived edge (`pangloss-derived`, `DerivedEdge.Meta(shortcut=True)`): an edge from one entity to
another that is no relation of the models, marked `derived: true` (`fragments.model_edge`). The core sees it in none
of its reads, and none of its writes moves or removes it.

The edges are written here by hand, as the worker of `pangloss-derived` writes them: between entities that also have
relations of the models to each other, and between entities that have none."""

import dataclasses
import json
from typing import Any, no_type_check

import pytest
from pangloss_core import storage_of
from pangloss_cypher import fragments
from pangloss_models import Match, hooks
from pangloss_models.autocomplete import search_everything

from .helpers import run
from .merge_support import (
    declare,
    every_kind,
    make,
    moves_of,
    person,
    ref,
    reverse_edges_from,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture(autouse=True)
def an_app_with_such_edges():
    """An installed app says there are edges of no field, as `pangloss-derived` does when a class asks for
    shortcuts: the counts that order what is offered while typing then test each edge (`fragments.counted_edge`)"""
    said = lambda: True  # noqa: E731
    hooks.edges_of_no_field.append(said)
    yield
    hooks.edges_of_no_field.remove(said)


def add_shortcut(db_driver, a: Any, b: Any, type: str = "KnowsOf", key: str = "k"):
    made = run(
        db_driver,
        f"""
        MATCH (a:PGIndexableNode {{id: $a}}), (b:PGIndexableNode {{id: $b}})
        CREATE (a)-[e:{type} {{key: $key, {fragments.DERIVED_EDGE}: true}}]->(b)
        RETURN count(e) AS made
        """,
        a=str(a.id),
        b=str(b.id),
        key=key,
    )
    assert made == [{"made": 1}]


def edges_to(db_driver, id: Any) -> list[tuple[str, str, int | None]]:
    """The forward edges of fields into a node (`merge_support.edges_to`, without the shortcuts)"""
    rows = run(
        db_driver,
        f"""
        MATCH (n:PGIndexableNode {{id: $id}})<-[e]-(s:PGIndexableNode)
        WHERE NOT coalesce(e.reverse, false) AND e.{fragments.DERIVED_EDGE} IS NULL
        RETURN s.type AS source, type(e) AS field, e.pg_position AS position
        """,
        id=str(id),
    )
    return sorted((r["source"], r["field"], r["position"]) for r in rows)


def shortcuts(db_driver) -> list[tuple[str, str, str, str]]:
    rows = run(
        db_driver,
        f"""
        MATCH (a)-[e]->(b) WHERE e.{fragments.DERIVED_EDGE}
        RETURN a.label AS a, type(e) AS type, b.label AS b, e.key AS key
        """,
    )
    return sorted((r["a"], r["type"], r["b"], r["key"]) for r in rows)


def dumped(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, tuple):
        return [dumped(v) for v in value]
    if isinstance(value, dict):
        return {k: dumped(v) for k, v in value.items()}
    if isinstance(value, list):
        return [dumped(v) for v in value]
    if isinstance(value, type):
        return value.__name__
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: dumped(getattr(value, f.name)) for f in dataclasses.fields(value)
        }
    return json.loads(json.dumps(value, default=str))


async def everything_read(
    m: Any, entities: dict[str, tuple[Any, Any]], documents: dict[str, tuple[Any, Any]]
) -> dict[str, Any]:
    """What the core reads of the entities and the documents, each under a name that says what it is"""
    operations = storage_of().operations
    seen: dict[str, Any] = {}
    for name, (model, id) in entities.items():
        seen[f"get {name}"] = await model.get(id)
        seen[f"edit {name}"] = await operations.get_entity_for_edit(model, id)
        seen[f"some {name}"] = await operations.get_entity_with_some(model, id, 2)
        seen[f"alone {name}"] = await operations.get_entity_without_incoming(model, id)
        fields = await operations.get_incoming_fields(model, id, 2)
        seen[f"incoming fields {name}"] = fields
        for field in sorted(fields.counts):
            seen[f"incoming {name} {field}"] = await operations.get_incoming(
                model, id, field, 0, 50
            )
        seen[f"deletable {name}"] = await operations.check_deletable(model, id)
        seen[f"merges {name}"] = await model.merges(id)
    for name, (model, id) in documents.items():
        seen[f"get {name}"] = await model.get(id)
    seen["most used Entity"] = await m.Entity.autocomplete("")
    seen["typed Entity"] = await m.Entity.autocomplete("smith")
    for model in (m.Person, m.Group):
        name = model.__name__
        listed = await model.list(use_counts=True)
        seen[f"list {name}"] = (listed, listed.use_counts)
        seen[f"used {name}"] = await model.list(used_only=True)
        for deep in (False, True):
            seen[f"list smith {name} {deep}"] = await model.list(
                search_terms="smith", deep_search=deep
            )
            seen[f"list mention {name} {deep}"] = await model.list(
                search_terms="mention", deep_search=deep
            )
        seen[f"most used {name}"] = await model.autocomplete("")
        seen[f"typed {name}"] = await model.autocomplete("smith")
    for model in (m.Mention, m.Wrapped, m.Factoid, m.Statement):
        name = model.__name__
        seen[f"list {name}"] = await model.list()
        seen[f"deep {name}"] = await model.list(search_terms="smith", deep_search=True)
    seen["everything smith"] = await search_everything("smith")
    seen["everything"] = await search_everything("", [m.Person, m.Group, m.Mention])
    a = entities["a"][1]
    b = entities["b"][1]
    searches = {
        "named by a mention": (
            m.Person,
            {"$incoming": [{"type": "Mention", "where": {}}]},
        ),
        "named by a group": (m.Person, {"$incoming": [{"type": "Group", "where": {}}]}),
        "named by a person": (
            m.Person,
            {"$incoming": [{"type": "Person", "where": {}}]},
        ),
        "knows someone": (m.Person, {"knows": {"exists": True}}),
        "knows nobody": (m.Person, {"knows": {"exists": False}}),
        "knows a": (m.Person, {"knows": {"is": str(a)}}),
        "any a": (m.Person, {"$any": {"is": str(a)}}),
        "any b": (m.Group, {"$any": {"is": str(b)}}),
        "mentions a": (m.Mention, {"$mentions": {"is": str(a)}}),
        "mentions b": (m.Factoid, {"$mentions": {"is": str(b)}}),
        "group of b": (m.Group, {"members": {"is": str(b)}}),
        "wrapped a": (m.Wrapped, {"identified": {"is": str(a)}}),
    }
    for name, (model, where) in searches.items():
        found = await model.search(Match(where=where))
        seen[f"search {name}"] = sorted(str(r.id) for r in found.results)
    seen["preview c into a"] = await m.Person.merge_preview(
        absorb=entities["c"][1], into=a
    )
    seen["preview a into b"] = await m.Person.merge_preview(absorb=a, into=b)
    seen["stray"] = await operations.stray_references()
    return {name: dumped(value) for name, value in seen.items()}


VOLATILE = {"updated_when", "updated_by", "version"}


def steady(value: Any) -> Any:
    """Without what any write changes"""
    if isinstance(value, dict):
        return {k: steady(v) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [steady(v) for v in value]
    return value


def differences(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    return sorted(
        name
        for name in before.keys() | after.keys()
        if before.get(name) != after.get(name)
    )


async def world(m: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Three people that documents and entities refer to by every kind of relation, a fourth that nothing refers to,
    and a group"""
    a = await person(m, "John Smith", born=1800)
    b = await person(m, "Jon Smyth")
    c = await person(m, "Jane Smith")
    alone = await person(m, "Alone Smith")
    made = await every_kind(m, a, b)
    of_c = await every_kind(m, c, a)
    guild = await make(m.Group, "Smith guild", members=[ref(c)])
    entities = {
        "a": (m.Person, a.id),
        "b": (m.Person, b.id),
        "c": (m.Person, c.id),
        "alone": (m.Person, alone.id),
        "group": (m.Group, made["group"].id),
        "guild": (m.Group, guild.id),
    }
    documents = {
        "mention": (m.Mention, made["mention"].id),
        "rated": (m.Rated, made["rated"].id),
        "wrapped": (m.Wrapped, made["wrapped"].id),
        "order": (m.Order, made["order"].id),
        "factoid": (m.Factoid, made["factoid"].id),
        "mention of c": (m.Mention, of_c["mention"].id),
        "factoid of c": (m.Factoid, of_c["factoid"].id),
    }
    people = {"a": a, "b": b, "c": c, "alone": alone, "guild": guild}
    return entities, documents, people


def add_all(db_driver, people: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    """Shortcuts in both directions between people who have relations of the models to each other, to and from one
    who has none, two of one class between the same two, and to and from an entity of another class"""
    a, b, c, alone, guild = (people[n] for n in ("a", "b", "c", "alone", "guild"))
    add_shortcut(db_driver, a, b, key="1")
    add_shortcut(db_driver, b, a, key="2")
    add_shortcut(db_driver, a, b, "SameGuild", key="3")
    add_shortcut(db_driver, a, b, "SameGuild", key="4")
    add_shortcut(db_driver, c, a, key="5")
    add_shortcut(db_driver, b, c, key="6")
    add_shortcut(db_driver, alone, a, key="7")
    add_shortcut(db_driver, c, alone, key="8")
    add_shortcut(db_driver, guild, alone, "Hosts", key="9")
    add_shortcut(db_driver, alone, guild, "Hosts", key="10")
    found = shortcuts(db_driver)
    assert len(found) == 10
    return found


@no_type_check
async def test_no_read_of_the_core_sees_a_shortcut_edge(db_driver, clear_database):
    m = declare()
    entities, documents, people = await world(m)
    before = await everything_read(m, entities, documents)
    # (the reads say something: the people are referred to, and one is not)
    assert before["deletable alone"]["deletable"] is True
    assert before["deletable a"]["deletable"] is False
    assert before["search knows someone"] and before["search named by a person"]
    assert len(before) > 100

    add_all(db_driver, people)

    after = await everything_read(m, entities, documents)
    changed = differences(before, after)
    assert changed == [], {n: (before.get(n), after.get(n)) for n in changed[:2]}


@no_type_check
async def test_an_update_of_an_entity_leaves_its_shortcut_edges(
    db_driver, clear_database
):
    m = declare()
    entities, documents, people = await world(m)
    there = add_all(db_driver, people)
    a, b, alone = people["a"], people["b"], people["alone"]

    # (its own values; its relations given again; its relations taken away; given to someone else)
    await m.Person.Update(id=alone.id, label="Alone Smith", born=1700, knows=[]).save()
    assert shortcuts(db_driver) == there
    await m.Person.Update(id=b.id, label="Jon Smyth", knows=[ref(a)]).save()
    assert shortcuts(db_driver) == there
    await m.Person.Update(id=b.id, label="Jon Smyth", knows=[]).save()
    assert shortcuts(db_driver) == there
    assert (await m.Person.get(b.id)).knows == []
    await m.Person.Update(id=b.id, label="Jon Smyth", knows=[ref(alone)]).save()
    assert shortcuts(db_driver) == there
    assert [p.id for p in (await m.Person.get(b.id)).knows] == [alone.id]
    assert [p.id for p in (await m.Person.get(alone.id)).knows_reverse] == [b.id]
    # (an update of a document that names them; and its deletion)
    mention = documents["mention"][1]
    await m.Mention.Update(
        id=mention, label="A mention", of=ref(alone), others=[]
    ).save()
    assert shortcuts(db_driver) == there
    await m.Mention.delete(mention)
    assert shortcuts(db_driver) == there


@no_type_check
async def test_an_entity_only_shortcut_edges_reach_is_deleted_and_restored(
    db_driver, clear_database
):
    m = declare()
    entities, documents, people = await world(m)
    there = add_all(db_driver, people)
    alone = people["alone"]
    operations = storage_of().operations

    check = await operations.check_deletable(m.Person, alone.id)
    assert check.deletable and check.reference_count == 0
    await m.Person.delete(alone.id)
    assert await m.Person.get(alone.id) is None
    # (it is kept, marked as deleted, and so are its edges: the worker takes away what was derived of it)
    assert shortcuts(db_driver) == there
    # (and what the others are read as has nothing of it)
    a = await m.Person.get(people["a"].id)
    assert "Alone Smith" not in json.dumps(a.model_dump(mode="json"))
    await m.Person.undelete(alone.id)
    assert (await m.Person.get(alone.id)).label == "Alone Smith"
    assert shortcuts(db_driver) == there


@no_type_check
async def test_a_merge_does_not_move_a_shortcut_edge_and_its_undo_leaves_it(
    db_driver, clear_database
):
    m = declare()
    entities, documents, people = await world(m)
    a, c, alone = people["a"], people["c"], people["alone"]
    # (the same merge, in a database without the shortcuts: what it moves)
    plain = await m.Person.merge(absorb=c.id, into=a.id)
    plain_moves = sorted(
        (r["source"], r["field"], r["dropped"])
        for r in moves_of(db_driver, plain.merge.id)
    )
    plain_counts = (plain.merge.heads, plain.merge.moved, plain.merge.dropped)
    await m.Person.unmerge(plain.merge.id)
    plain_edges = (edges_to(db_driver, a.id), edges_to(db_driver, c.id))
    before = await everything_read(m, entities, documents)

    there = add_all(db_driver, people)
    result = await m.Person.merge(absorb=c.id, into=a.id)

    assert (
        result.merge.heads,
        result.merge.moved,
        result.merge.dropped,
    ) == plain_counts
    assert (
        sorted(
            (r["source"], r["field"], r["dropped"])
            for r in moves_of(db_driver, result.merge.id)
        )
        == plain_moves
    )
    # (the shortcuts are where they were: those of the absorbed entity are for the worker to take away)
    assert shortcuts(db_driver) == there
    assert edges_to(db_driver, c.id) == []
    assert reverse_edges_from(db_driver, c.id) == []
    assert dumped(await storage_of().operations.stray_references()) == []

    undone = await m.Person.unmerge(result.merge.id)
    assert undone.merge.state == "undone"
    assert shortcuts(db_driver) == there
    now = (edges_to(db_driver, a.id), edges_to(db_driver, c.id))
    assert [set(n) ^ set(p) for n, p in zip(now, plain_edges, strict=True)] == [
        set(),
        set(),
    ]
    assert now == plain_edges
    after = await everything_read(m, entities, documents)
    # (but for the record of the merges themselves, and of when each thing was last written)
    changed = [
        d
        for d in differences(steady(before), steady(after))
        if not d.startswith("merges ")
    ]
    assert changed == []

    # (one who only had shortcuts merges as one nothing refers to)
    lonely = await m.Person.merge(absorb=alone.id, into=a.id)
    assert (lonely.merge.heads, lonely.merge.moved) == (0, 0)
    assert shortcuts(db_driver) == there
    await m.Person.unmerge(lonely.merge.id)
    assert shortcuts(db_driver) == there


@no_type_check
async def test_a_search_of_any_relation_does_not_follow_a_shortcut(
    db_driver, clear_database
):
    m = declare()
    a = await person(m, "John Smith")
    b = await person(m, "Jon Smyth")
    c = await person(m, "Jane Smith", knows=[ref(a)])
    await make(m.Mention, "A mention", of=ref(a))
    add_shortcut(db_driver, b, a)
    add_shortcut(db_driver, b, c, key="2")
    add_shortcut(db_driver, b, c, "SameGuild", key="3")
    add_shortcut(db_driver, a, b)

    async def found(model, where):
        return sorted(r.label for r in (await model.search(Match(where=where))).results)

    assert await found(m.Person, {"$any": {"is": str(a.id)}}) == ["Jane Smith"]
    assert await found(m.Person, {"$any": {"is": str(b.id)}}) == []
    assert await found(m.Person, {"knows": {"exists": True}}) == ["Jane Smith"]
    assert await found(m.Person, {"knows": {"exists": False}}) == [
        "John Smith",
        "Jon Smyth",
    ]
    assert await found(m.Person, {"$incoming": [{"type": "Person", "where": {}}]}) == [
        "John Smith"
    ]
    listed = await m.Person.list(use_counts=True)
    assert {p.label: listed.use_counts[str(p.id)] for p in listed.results} == {
        "John Smith": 2,
        "Jon Smyth": 0,
        "Jane Smith": 0,
    }
    # (the most used first: the one two things refer to, not the one with four shortcuts)
    assert [p.label for p in (await m.Person.autocomplete("")).results] == [
        "John Smith",
        "Jane Smith",
        "Jon Smyth",
    ]
    assert [p.label for p in (await search_everything("", [m.Person])).results] == [
        "John Smith",
        "Jane Smith",
        "Jon Smyth",
    ]
    assert [p.label for p in (await search_everything("smith")).results][0] == (
        "John Smith"
    )


@no_type_check
async def test_the_counts_test_each_edge_only_when_an_app_says_there_are_such_edges(
    db_driver, clear_database, an_app_with_such_edges
):
    from pangloss_cypher.autocomplete_query import (
        most_connected_query,
        most_used_query,
        search_everything_query,
    )
    from pangloss_cypher.transactions import dialect

    def queries():
        d = dialect()
        return [
            most_used_query(d),
            search_everything_query(d),
            most_connected_query(d, ["Person"]),
        ]

    assert all(fragments.model_edge("edge") in q for q in queries())
    said = hooks.edges_of_no_field[:]
    hooks.edges_of_no_field.clear()
    try:
        assert not hooks.has_edges_of_no_field()
        assert not any("derived" in q for q in queries())
        hooks.edges_of_no_field.append(lambda: False)
        assert not any("derived" in q for q in queries())
        # (and they run as they are)
        m = declare()
        await person(m, "John Smith")
        assert [p.label for p in (await m.Person.autocomplete("")).results] == [
            "John Smith"
        ]
        assert [p.label for p in (await search_everything("smith")).results] == [
            "John Smith"
        ]
    finally:
        hooks.edges_of_no_field[:] = said
    assert hooks.has_edges_of_no_field()
