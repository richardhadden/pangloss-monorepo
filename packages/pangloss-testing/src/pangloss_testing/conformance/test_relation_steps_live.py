"""A relation through several wrappers as one edge (implementation_docs/relation-steps-plan.md): what is read back of
it from the entity it reaches, and what a search can ask of any step of its way, whether the values of the step are on
an edge (an edge model) or on a node (a wrapper). What cannot be done yet is marked with the step of the plan that
lifts it."""

from typing import no_type_check

import pytest
from pangloss_models import (
    Document,
    EdgeModel,
    Entity,
    Match,
    PanglossSearchError,
    ReifiedRelation,
    ViaEdge,
    initialise,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    class Certainty(EdgeModel):
        value: int
        note: str | None = None

    class RoleType(Entity):
        pass

    class EdgeA[T](ReifiedRelation[T]):
        a: int

    class EdgeB[T](ReifiedRelation[T]):
        b: int

    class EdgeC[T](ReifiedRelation[T]):
        c: int

    class InRole[T](ReifiedRelation[T]):
        role: RoleType

    class Person(Entity):
        pass

    class Doc(Document):
        chain: list[EdgeA[EdgeB[EdgeC[Person]]]]
        twice: list[EdgeA[EdgeA[Person]]]
        # (an edge model on the edge into a wrapper; on the edge out of one; on both)
        edge_in: list[ViaEdge[EdgeA[Person], Certainty]]
        edge_out: list[EdgeA[ViaEdge[Person, Certainty]]]
        both: list[ViaEdge[EdgeA[ViaEdge[Person, Certainty]], Certainty]]
        # (a wrapper with a relation of its own)
        role: list[InRole[Person]]
        plain: list[ViaEdge[Person, Certainty]]

    initialise()
    return Person, RoleType, Doc


FIELDS = ("chain", "twice", "edge_in", "edge_out", "both", "role", "plain")


def ref(item, **edge):
    made = {"type": item.type, "id": item.id}
    if edge:
        made["edge_properties"] = edge
    return made


def chain(person, a, b, c):
    return {
        "type": "EdgeA",
        "a": a,
        "target": [
            {
                "type": "EdgeB",
                "b": b,
                "target": [{"type": "EdgeC", "c": c, "target": [ref(person)]}],
            }
        ],
    }


def edge_a(a, *target, value=None):
    made = {"type": "EdgeA", "a": a, "target": list(target)}
    if value is not None:
        made["edge_properties"] = {"value": value}
    return made


def in_role(role, person):
    return {"type": "InRole", "role": ref(role), "target": [ref(person)]}


def labels(found):
    return sorted(item.label for item in found.results)


@no_type_check
async def make(clear_database):
    """The people and documents of every test. A person for each shape whose reverse read fails today (Ann by `role`,
    Bea and Dan by `edge_in`, Cat by `both`), so that a read of the others is not made to fail by them"""
    Person, RoleType, Doc = models()
    people = {
        name: await Person.Create(label=name).save()
        for name in ("John", "Jane", "Ann", "Bea", "Cat", "Dan")
    }
    john, jane, ann, bea, cat, dan = people.values()
    baker = await RoleType.Create(label="baker").save()
    miller = await RoleType.Create(label="miller").save()

    async def doc(label, **fields):
        return await Doc.Create(
            label=label, **{f: fields.get(f, []) for f in FIELDS}
        ).save()

    docs = [
        await doc("chain 123 john", chain=[chain(john, 1, 2, 3)]),
        await doc("chain 456 john", chain=[chain(john, 4, 5, 6)]),
        await doc("chain 123 jane", chain=[chain(jane, 1, 2, 3)]),
        # (two ways in one document: what is asked of one way has all to hold of one of them)
        await doc("two chains", chain=[chain(john, 7, 8, 9), chain(jane, 1, 1, 1)]),
        await doc("twice 1 2", twice=[edge_a(1, edge_a(2, ref(john)))]),
        await doc("twice 2 1", twice=[edge_a(2, edge_a(1, ref(john)))]),
        await doc("edge_in 9", edge_in=[edge_a(1, ref(bea), value=9)]),
        await doc("edge_in 2", edge_in=[edge_a(2, ref(dan), value=2)]),
        await doc("edge_out 9", edge_out=[edge_a(1, ref(john, value=9))]),
        await doc(
            "edge_out crossed",
            edge_out=[edge_a(1, ref(john, value=2)), edge_a(2, ref(john, value=9))],
        ),
        await doc("both 9 2", both=[edge_a(1, ref(cat, value=2), value=9)]),
        await doc("both 2 9", both=[edge_a(1, ref(cat, value=9), value=2)]),
        await doc("ann baker", role=[in_role(baker, ann)]),
        await doc("ann miller", role=[in_role(miller, ann)]),
        await doc("plain 9", plain=[ref(john, value=9)]),
        await doc("plain 2", plain=[ref(john, value=2)]),
        await doc("nothing"),
    ]
    return {
        "Person": Person,
        "Doc": Doc,
        **{name.lower(): p for name, p in people.items()},
        "baker": baker,
        "miller": miller,
        "all": sorted(d.label for d in docs),
    }


@no_type_check
def searcher(m):
    async def found(where, **match):
        return labels(await m["Doc"].search(Match(where=where, **match)))

    return found


def item(type_, **where):
    """A `via` item or a `through` step: `item("EdgeA", a=1)` asks `a` to be 1; a value that is a dict is the
    condition as it is"""
    made: dict = {"type": type_}
    if where:
        made["where"] = {
            k: v if isinstance(v, dict) else {"eq": v} for k, v in where.items()
        }
    return made


# --- what holds today: a chain of wrappers is one relation ------------------------------------------------------------


@no_type_check
async def test_a_relation_through_three_wrappers_is_found_by_what_it_reaches(
    clear_database,
):
    m = await make(clear_database)
    found = searcher(m)
    john, jane = str(m["john"].id), str(m["jane"].id)
    assert await found({"chain": {"is": john}}) == [
        "chain 123 john",
        "chain 456 john",
        "two chains",
    ]
    assert await found({"chain": {"is": jane}}) == ["chain 123 jane", "two chains"]
    assert await found({"chain": {"is_any": [john, jane]}}) == [
        "chain 123 jane",
        "chain 123 john",
        "chain 456 john",
        "two chains",
    ]


@no_type_check
async def test_whether_there_is_a_relation_through_three_wrappers(clear_database):
    m = await make(clear_database)
    found = searcher(m)
    with_chain = ["chain 123 jane", "chain 123 john", "chain 456 john", "two chains"]
    assert await found({"chain": {"exists": True}}) == with_chain
    assert await found({"chain": {"exists": False}}) == sorted(
        set(m["all"]) - set(with_chain)
    )


@no_type_check
async def test_a_document_mentions_what_it_reaches_through_three_wrappers(
    clear_database,
):
    m = await make(clear_database)
    found = searcher(m)
    assert await found({"$mentions": {"is": str(m["jane"].id)}}) == [
        "chain 123 jane",
        "two chains",
    ]
    assert await found(
        {"$mentions": {"is": str(m["jane"].id), "through": ["EdgeB"]}}
    ) == ["chain 123 jane", "two chains"]


@no_type_check
async def test_each_of_three_wrappers_is_asked_by_its_own_values(clear_database):
    m = await make(clear_database)
    found = searcher(m)
    john = str(m["john"].id)
    assert await found({"chain": {"is": john, "through": [item("EdgeA", a=4)]}}) == [
        "chain 456 john"
    ]
    assert await found({"chain": {"is": john, "through": [item("EdgeB", b=5)]}}) == [
        "chain 456 john"
    ]
    assert await found({"chain": {"is": john, "through": [item("EdgeC", c=3)]}}) == [
        "chain 123 john"
    ]
    assert await found(
        {"chain": {"through": [item("EdgeA", a=1), item("EdgeC", c=3)]}}
    ) == ["chain 123 jane", "chain 123 john"]
    # (the values of two wrappers of different ways of one document are not those of one way)
    assert (
        await found({"chain": {"through": [item("EdgeA", a=1), item("EdgeB", b=8)]}})
        == []
    )


@no_type_check
async def test_what_a_wrapper_holds_is_not_asked_in_a_step(clear_database):
    m = await make(clear_database)
    with pytest.raises(PanglossSearchError, match="role.through.InRole.target"):
        await searcher(m)(
            {"role": {"through": [item("InRole", target={"exists": True})]}}
        )


@no_type_check
async def test_an_entity_is_found_by_what_refers_to_it_through_three_wrappers(
    clear_database,
):
    m = await make(clear_database)

    async def people(*incoming):
        return labels(
            await m["Person"].search(Match(where={"$incoming": list(incoming)}))
        )

    assert await people(
        {"type": "Doc", "field": "chain", "through": ["EdgeA", "EdgeB", "EdgeC"]}
    ) == ["Jane", "John"]
    assert await people({"type": "Doc", "field": "chain", "through": ["EdgeC"]}) == [
        "Jane",
        "John",
    ]
    assert await people({"type": "Doc", "field": "role", "through": ["InRole"]}) == [
        "Ann"
    ]
    assert await people({"type": "Doc", "field": "chain", "through": ["InRole"]}) == []


@no_type_check
async def test_an_entity_reads_back_a_relation_through_three_wrappers(clear_database):
    m = await make(clear_database)
    read = await m["Person"].get(id=m["jane"].id)
    by_label = {d.label: d for d in read.chain_reverse}
    assert sorted(by_label) == ["chain 123 jane", "two chains"]
    a = by_label["chain 123 jane"].chain[0]
    b = a.target[0]
    c = b.target[0]
    assert (a.type, a.a, b.type, b.b, c.type, c.c) == (
        "EdgeA",
        1,
        "EdgeB",
        2,
        "EdgeC",
        3,
    )
    assert [t.id for t in c.target] == [m["jane"].id]
    # (of the document with two ways, only the one that reaches her)
    assert [w.a for w in by_label["two chains"].chain] == [1]


@no_type_check
async def test_an_entity_reads_back_the_relations_whose_edges_carry_values_only_out_of_a_wrapper(
    clear_database,
):
    """John is reached by `chain`, `twice`, `edge_out` and `plain`: none has values on an edge into a wrapper"""
    m = await make(clear_database)
    read = await m["Person"].get(id=m["john"].id)
    assert sorted(d.label for d in read.twice_reverse) == ["twice 1 2", "twice 2 1"]
    twice = {d.label: d.twice[0] for d in read.twice_reverse}
    assert (twice["twice 1 2"].a, twice["twice 1 2"].target[0].a) == (1, 2)
    out = {d.label: d.edge_out for d in read.edge_out_reverse}
    assert sorted(out) == ["edge_out 9", "edge_out crossed"]
    assert [w.target[0].edge_properties.value for w in out["edge_out 9"]] == [9]
    assert sorted(d.label for d in read.plain_reverse) == ["plain 2", "plain 9"]


# --- step 1: the reverse read -----------------------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="relation-steps step 1: the reverse read gives a wrapper what it holds, not its own relations "
    "(role_reverse.0.role.0.InRole.role: Field required)",
)
@no_type_check
async def test_an_entity_reads_back_a_relation_through_a_wrapper_with_a_relation_of_its_own(
    clear_database,
):
    m = await make(clear_database)
    read = await m["Person"].get(id=m["ann"].id)
    roles = {d.label: d.role[0].role for d in read.role_reverse}
    assert sorted(roles) == ["ann baker", "ann miller"]
    assert roles["ann baker"].id == m["baker"].id
    assert roles["ann baker"].label == "baker"
    assert roles["ann miller"].id == m["miller"].id


@pytest.mark.xfail(
    strict=True,
    reason="relation-steps step 1: the properties of the edge into a wrapper are not read back "
    "(edge_in_reverse.0.edge_in.0.EdgeA.edgeProperties: Field required)",
)
@no_type_check
async def test_an_entity_reads_back_the_values_of_the_edge_into_a_wrapper(
    clear_database,
):
    m = await make(clear_database)
    read = await m["Person"].get(id=m["bea"].id)
    assert [d.label for d in read.edge_in_reverse] == ["edge_in 9"]
    wrapper = read.edge_in_reverse[0].edge_in[0]
    assert (wrapper.a, wrapper.edge_properties.value) == (1, 9)
    assert [t.id for t in wrapper.target] == [m["bea"].id]


@pytest.mark.xfail(
    strict=True,
    reason="relation-steps step 1: the properties of the edge into a wrapper are not read back "
    "(both_reverse.0.both.0.EdgeA.edgeProperties: Field required)",
)
@no_type_check
async def test_an_entity_reads_back_the_values_of_the_edges_into_and_out_of_a_wrapper_each_in_its_place(
    clear_database,
):
    m = await make(clear_database)
    read = await m["Person"].get(id=m["cat"].id)
    seen = {
        d.label: (
            d.both[0].edge_properties.value,
            d.both[0].target[0].edge_properties.value,
        )
        for d in read.both_reverse
    }
    assert seen == {"both 9 2": (9, 2), "both 2 9": (2, 9)}


# --- step 2: a wrapper's own relations in a `where` -------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="relation-steps step 2: only the values of a wrapper can be tested in a step, not its relations",
)
@no_type_check
async def test_a_step_asks_a_wrapper_by_its_own_relation(clear_database):
    m = await make(clear_database)
    found = searcher(m)
    ann, baker, miller = (str(m[k].id) for k in ("ann", "baker", "miller"))

    def by_role(**condition):
        return {"role": {"is": ann, "through": [item("InRole", role=condition)]}}

    assert await found(by_role(**{"is": baker})) == ["ann baker"]
    assert await found(by_role(**{"is": miller})) == ["ann miller"]
    assert await found(by_role(is_any=[baker])) == ["ann baker"]
    assert await found(by_role(is_any=[baker, miller])) == ["ann baker", "ann miller"]


@pytest.mark.xfail(
    strict=True,
    reason="relation-steps step 2: only the values of a wrapper can be tested in a step, not its relations",
)
@no_type_check
async def test_a_step_asks_whether_a_wrapper_has_a_relation_of_its_own(clear_database):
    # (`InRole.role` is required, so every role has one: `exists` is true of both and false of none)
    m = await make(clear_database)
    found = searcher(m)
    ann = str(m["ann"].id)

    def by_role(exists):
        return {
            "role": {"is": ann, "through": [item("InRole", role={"exists": exists})]}
        }

    assert await found(by_role(True)) == ["ann baker", "ann miller"]
    assert await found(by_role(False)) == []


# --- step 3: `via`, the check -----------------------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="relation-steps step 3: there is no `via` (a condition with it is not read: extra inputs are not permitted)",
)
@no_type_check
async def test_what_a_via_cannot_ask_is_refused(clear_database):
    m = await make(clear_database)
    found = searcher(m)

    async def refused(field, via, **match):
        with pytest.raises(PanglossSearchError):
            await found({field: {"via": via}}, **match)

    # (an edge model no edge of the relation has; a wrapper on a relation with none in its type)
    await refused("chain", [item("Certainty", value=1)])
    await refused("plain", [item("EdgeA")])
    # (an edge model with nothing asked of it: an edge does not say what it is)
    await refused("plain", [{"type": "Certainty"}])
    await refused("plain", [{"type": "Certainty", "where": {}}])
    # (what a wrapper holds is the relation's own business)
    await refused("chain", [item("EdgeA", target={"exists": True})])
    # (no such class; a wrapper the search leaves out)
    await refused("chain", [{"type": "Nope"}])
    await refused("chain", [item("EdgeA", a=1)], exclude_wrappers=["EdgeA"])


# --- step 4: `via` on a relation field --------------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="relation-steps step 4: there is no `via` (a condition with it is not read)",
)
@no_type_check
async def test_via_asks_each_wrapper_of_a_chain_in_order(clear_database):
    m = await make(clear_database)
    found = searcher(m)
    john = str(m["john"].id)

    async def chain_of_john(*via):
        return await found({"chain": {"is": john, "via": list(via)}})

    a1, b2, c3 = item("EdgeA", a=1), item("EdgeB", b=2), item("EdgeC", c=3)
    assert await chain_of_john(a1, b2, c3) == ["chain 123 john"]
    assert await chain_of_john(
        item("EdgeA", a=4), item("EdgeB", b=5), item("EdgeC", c=6)
    ) == ["chain 456 john"]
    # (one value of another document's)
    assert await chain_of_john(a1, item("EdgeB", b=5), c3) == []
    # (some of the steps: others may lie between)
    assert await chain_of_john(a1, c3) == ["chain 123 john"]
    assert await chain_of_john(b2) == ["chain 123 john"]
    # (in the wrong order)
    assert await chain_of_john(c3, a1) == []
    assert await chain_of_john(b2, a1) == []


@pytest.mark.xfail(
    strict=True,
    reason="relation-steps step 4: there is no `via` (a condition with it is not read)",
)
@no_type_check
async def test_via_tells_the_outer_from_the_inner_of_two_wrappers_of_one_class(
    clear_database,
):
    m = await make(clear_database)
    found = searcher(m)
    assert await found(
        {"twice": {"via": [item("EdgeA", a=1), item("EdgeA", a=2)]}}
    ) == ["twice 1 2"]
    assert await found(
        {"twice": {"via": [item("EdgeA", a=2), item("EdgeA", a=1)]}}
    ) == ["twice 2 1"]
    # (one item is met by either)
    assert await found({"twice": {"via": [item("EdgeA", a=1)]}}) == [
        "twice 1 2",
        "twice 2 1",
    ]


@pytest.mark.xfail(
    strict=True,
    reason="relation-steps step 4: there is no `via` (a condition with it is not read)",
)
@no_type_check
async def test_via_asks_the_edge_into_a_wrapper(clear_database):
    m = await make(clear_database)
    found = searcher(m)
    sure = item("Certainty", value={"gte": 8})
    assert await found({"edge_in": {"via": [sure]}}) == ["edge_in 9"]
    assert await found({"edge_in": {"is": str(m["bea"].id), "via": [sure]}}) == [
        "edge_in 9"
    ]
    assert await found({"edge_in": {"is": str(m["dan"].id), "via": [sure]}}) == []


@pytest.mark.xfail(
    strict=True,
    reason="relation-steps step 4: there is no `via` (a condition with it is not read)",
)
@no_type_check
async def test_via_tells_the_edge_into_a_wrapper_from_the_edge_out_of_it(
    clear_database,
):
    m = await make(clear_database)
    found = searcher(m)

    def both(outer, inner):
        return {
            "both": {
                "via": [
                    item("Certainty", value=outer),
                    item("EdgeA"),
                    item("Certainty", value=inner),
                ]
            }
        }

    assert await found(both(9, 2)) == ["both 9 2"]
    assert await found(both(2, 9)) == ["both 2 9"]
    # (the edge into the wrapper alone, and the edge out of it alone)
    assert await found(
        {"both": {"via": [item("Certainty", value=9), item("EdgeA")]}}
    ) == ["both 9 2"]
    assert await found(
        {"both": {"via": [item("EdgeA"), item("Certainty", value=9)]}}
    ) == ["both 2 9"]


@pytest.mark.xfail(
    strict=True,
    reason="relation-steps step 4: there is no `via` (a condition with it is not read)",
)
@no_type_check
async def test_via_with_an_edge_model_alone_asks_what_edge_does_of_the_last_edge(
    clear_database,
):
    m = await make(clear_database)
    found = searcher(m)
    sure = item("Certainty", value={"gte": 8})
    for field, wanted in (
        ("plain", ["plain 9"]),
        ("edge_out", ["edge_out 9", "edge_out crossed"]),
    ):
        assert await found({field: {"edge": sure}}) == wanted
        assert await found({field: {"via": [sure]}}) == wanted
        assert await found({field: {"is": str(m["john"].id), "via": [sure]}}) == wanted


@pytest.mark.xfail(
    strict=True,
    reason="relation-steps step 4: there is no `via` (a condition with it is not read)",
)
@no_type_check
async def test_via_mixes_an_edge_model_and_a_wrapper_without_saying_how_each_is_stored(
    clear_database,
):
    m = await make(clear_database)
    found = searcher(m)
    sure = item("Certainty", value={"gte": 8})
    assert await found({"edge_in": {"via": [sure, item("EdgeA", a=1)]}}) == [
        "edge_in 9"
    ]
    assert await found({"edge_in": {"via": [sure, item("EdgeA", a=2)]}}) == []
    # (the certainty is on the edge into the wrapper: not after it)
    assert await found({"edge_in": {"via": [item("EdgeA", a=1), sure]}}) == []


@pytest.mark.xfail(
    strict=True,
    reason="relation-steps step 4: there is no `via` (a condition with it is not read)",
)
@no_type_check
async def test_via_asks_a_wrapper_by_its_own_relation(clear_database):
    m = await make(clear_database)
    found = searcher(m)
    baker = str(m["baker"].id)
    assert await found({"role": {"via": [item("InRole", role={"is": baker})]}}) == [
        "ann baker"
    ]
    assert await found(
        {
            "role": {
                "is": str(m["ann"].id),
                "via": [item("InRole", role={"is_any": [str(m["miller"].id)]})],
            }
        }
    ) == ["ann miller"]


@pytest.mark.xfail(
    strict=True,
    reason="relation-steps step 4: there is no `via` (a condition with it is not read)",
)
@no_type_check
async def test_via_alone_is_whether_there_is_a_relation_by_such_a_way(clear_database):
    m = await make(clear_database)
    found = searcher(m)
    a1 = [item("EdgeA", a=1)]
    # ("two chains" has a way to Jane through an EdgeA with a = 1)
    by_a1 = ["chain 123 jane", "chain 123 john", "two chains"]
    assert await found({"chain": {"via": a1}}) == by_a1
    assert await found({"chain": {"exists": True, "via": a1}}) == by_a1
    assert await found({"chain": {"exists": False, "via": a1}}) == sorted(
        set(m["all"]) - set(by_a1)
    )


@pytest.mark.xfail(
    strict=True,
    reason="relation-steps step 4: there is no `via` (a condition with it is not read)",
)
@no_type_check
async def test_via_holds_of_the_same_way_as_the_rest_of_the_condition(clear_database):
    m = await make(clear_database)
    found = searcher(m)
    john, jane = str(m["john"].id), str(m["jane"].id)
    a1 = item("EdgeA", a=1)
    # (`is`: in "two chains" the way with a = 1 reaches Jane, not John)
    assert await found({"chain": {"is": john, "via": [a1]}}) == ["chain 123 john"]
    assert await found(
        {"chain": {"is_any": [john, jane], "via": [item("EdgeB", b=2)]}}
    ) == [
        "chain 123 jane",
        "chain 123 john",
    ]
    # (`through`)
    assert await found(
        {"chain": {"through": [item("EdgeB", b=8)], "via": [item("EdgeA", a=7)]}}
    ) == ["two chains"]
    assert await found({"chain": {"through": [item("EdgeB", b=8)], "via": [a1]}}) == []
    # (`edge`: in "edge_out crossed" the certain edge leaves the wrapper with a = 2)
    sure = {"type": "Certainty", "where": {"value": {"gte": 8}}}
    assert await found({"edge_out": {"edge": sure, "via": [a1]}}) == ["edge_out 9"]
    assert await found({"edge_out": {"edge": sure, "via": [item("EdgeA", a=2)]}}) == [
        "edge_out crossed"
    ]


@pytest.mark.xfail(
    strict=True,
    reason="relation-steps step 4: there is no `via` (a condition with it is not read)",
)
@no_type_check
async def test_any_relation_and_mentions_take_via(clear_database):
    m = await make(clear_database)
    found = searcher(m)
    john = str(m["john"].id)
    via = [item("EdgeA", a=4), item("EdgeB", b=5)]
    assert await found({"$any": {"is": john, "via": via}}) == ["chain 456 john"]
    assert await found({"$mentions": {"is": john, "via": via}}) == ["chain 456 john"]
    sure = [item("Certainty", value={"gte": 8})]
    assert await found({"$mentions": {"is": str(m["bea"].id), "via": sure}}) == [
        "edge_in 9"
    ]


# --- step 5: `$incoming` with `via` -----------------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="relation-steps step 5: `$incoming` takes the names of wrappers only (a `via` is not read)",
)
@no_type_check
async def test_an_entity_is_found_by_the_way_something_refers_to_it(clear_database):
    m = await make(clear_database)

    async def people(**incoming):
        return labels(
            await m["Person"].search(
                Match(where={"$incoming": [{"type": "Doc", **incoming}]})
            )
        )

    assert await people(field="chain", via=[item("EdgeB", b=2)]) == ["Jane", "John"]
    assert await people(field="chain", via=[item("EdgeB", b=5)]) == ["John"]
    assert (
        await people(field="chain", via=[item("EdgeC", c=3), item("EdgeA", a=1)]) == []
    )
    assert await people(field="edge_in", via=[item("Certainty", value={"gte": 8})]) == [
        "Bea"
    ]
    assert await people(
        field="edge_in", via=[item("Certainty", value={"gte": 8}), item("EdgeA", a=1)]
    ) == ["Bea"]
    assert await people(
        field="role", via=[item("InRole", role={"is": str(m["miller"].id)})]
    ) == ["Ann"]
