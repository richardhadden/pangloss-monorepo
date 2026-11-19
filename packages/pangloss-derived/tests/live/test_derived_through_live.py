"""Rules that ask something of the way of a relation, on the backend under test: a wrapper passed through only when its
values, or the edge that leaves it, are as asked (`Through`); what the edge that reaches an entity has to be (`edge=`);
and the values met there used in the head: kept on each justification (`PerJustification()`), or part of what the edge is"""

from typing import Annotated, no_type_check

import pytest
from pangloss_models import (
    Compare,
    Conjunction,
    Document,
    EdgeModel,
    Entity,
    ReifiedRelation,
    Rel,
    SemanticSpace,
    Text,
    Through,
    ViaEdge,
    initialise,
)
from pangloss_testing.live import run

from pangloss_derived import (
    DerivedEdge,
    DerivedMeta,
    Object,
    PerJustification,
    Subject,
    Var,
    read,
    rule,
)
from pangloss_derived.registry import DerivedRegistry
from pangloss_derived.worker import worker
from pangloss_derived.worker import run_pending_derivations

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
def models():
    class Share(EdgeModel):
        percent: int

    class Certainty(EdgeModel):
        value: int
        note: str | None = None

    class Negative[T](SemanticSpace[T]):
        pass

    # (as the library's `WeightedAlternative`: one alternative at a time, and an edge through it is not plain)
    class Either[T](Conjunction):
        _derived_meta = DerivedMeta(derivation="qualify", exclusive=True)
        either: list[ViaEdge[T, Share]]

    class Identification[T](ReifiedRelation[T]):
        identified_by: str
        score: int = 0

    class Person(Entity):
        pass

    class Transfer(Document):
        given_by: (
            Person | Identification[Person] | Either[Person | Identification[Person]]
        )
        given_to: Person
        witnesses: list[ViaEdge[Person, Certainty]]

    class Factoid(Document):
        statements: list[Transfer | Negative[Transfer]]

    class GaveTo(DerivedEdge):
        """Gave to, with how likely each source makes it"""

        giver: Annotated[Person, Subject()]
        receiver: Annotated[Person, Object(reverse_name="received_from")]
        likelihood: Annotated[int, PerJustification()]

    class SurelyGaveTo(DerivedEdge):
        """Gave to, by an alternative of 60 per cent or more"""

        giver: Annotated[Person, Subject()]
        receiver: Annotated[Person, Object()]

    class GaveToAccordingTo(DerivedEdge):
        """Gave to, by whose identification (which is part of what the edge is)"""

        giver: Annotated[Person, Subject()]
        receiver: Annotated[Person, Object()]
        according_to: str

    class Witnessed(DerivedEdge):
        """Saw a gift given, with how sure each source is"""

        witness: Annotated[Person, Subject()]
        giver: Annotated[Person, Object()]
        certainty: Annotated[int, PerJustification()]

    class SurelyWitnessed(DerivedEdge):
        witness: Annotated[Person, Subject()]
        giver: Annotated[Person, Object()]

    class AsSureAsTheShare(DerivedEdge):
        """Saw a gift given by one of several, as sure of it as the share of that one"""

        witness: Annotated[Person, Subject()]
        giver: Annotated[Person, Object()]

    @rule
    def gave_to(a: Var[Person], b: Var[Person], p: Var[int]):
        """A gift by one of several, when that one is at least as likely as not"""
        return GaveTo.Derive(giver=a, receiver=b, likelihood=p).when(
            Transfer.Where(
                given_by=Rel(
                    is_=a, through=[Through(Either, edge=Share.Where(percent=p))]
                ),
                given_to=b,
            ),
            p >= 50,
        )

    @rule
    def surely_gave_to(a: Var[Person], b: Var[Person]):
        return SurelyGaveTo.Derive(giver=a, receiver=b).when(
            Transfer.Where(
                given_by=Rel(
                    is_=a,
                    through=[
                        Through(Either, edge=Share.Where(percent=Compare[int](gte=60)))
                    ],
                ),
                given_to=b,
            )
        )

    @rule
    def gave_to_according_to(a: Var[Person], b: Var[Person], who: Var[str]):
        return GaveToAccordingTo.Derive(giver=a, receiver=b, according_to=who).when(
            Transfer.Where(
                given_by=Rel(
                    is_=a,
                    through=[
                        Through(
                            Identification,
                            where=Identification.Where(
                                identified_by=who, score=Compare[int](gte=3)
                            ),
                        )
                    ],
                ),
                given_to=b,
            )
        )

    @rule
    def witnessed(w: Var[Person], a: Var[Person], c: Var[int]):
        return Witnessed.Derive(witness=w, giver=a, certainty=c).when(
            Transfer.Where(
                given_by=a,
                witnesses=Rel(is_=w, edge=Certainty.Where(value=c)),
            )
        )

    @rule
    def surely_witnessed(w: Var[Person], a: Var[Person]):
        return SurelyWitnessed.Derive(witness=w, giver=a).when(
            Transfer.Where(
                given_by=a,
                witnesses=Rel(
                    match=Person.Where(is_=w),
                    edge=Certainty.Where(
                        value=Compare[int](gte=8), note=Text(exists=False)
                    ),
                ),
            )
        )

    @rule
    def as_sure_as_the_share(w: Var[Person], a: Var[Person], c: Var[int]):
        # (one variable met on the way of two relations: the second time, it is a condition)
        return AsSureAsTheShare.Derive(witness=w, giver=a).when(
            Transfer.Where(
                given_by=Rel(
                    is_=a, through=[Through(Either, edge=Share.Where(percent=c))]
                ),
                witnesses=Rel(is_=w, edge=Certainty.Where(value=c)),
            )
        )

    initialise()
    return locals()


async def setup(clear_database):
    m = models()
    n = {}
    for name in "ABCDW":
        n[name] = await m["Person"].Create(label=name).save()
    return m, n


def person(item):
    return {"type": "Person", "id": item.id}


def identified(item, by="Smith", score=5):
    return {
        "type": "Identification",
        "identified_by": by,
        "score": score,
        "target": [person(item)],
    }


def either(*options):
    """`(what, percent)` each"""
    return {
        "type": "Either",
        "either": [
            {**what, "edge_properties": {"percent": percent}}
            for what, percent in options
        ],
    }


def transfer(giver, receiver, *witnesses):
    """`giver`: what `given_by` takes; `witnesses`: `(person, certainty)` or `(person, certainty, note)`"""
    return {
        "type": "Transfer",
        "label": "t",
        "given_by": giver,
        "given_to": person(receiver),
        "witnesses": [
            {
                **person(w[0]),
                "edge_properties": {"value": w[1]}
                | ({"note": w[2]} if len(w) > 2 else {}),
            }
            for w in witnesses
        ],
    }


async def says(m, label, *statements):
    return await m["Factoid"].Create(label=label, statements=list(statements)).save()


async def edges(m, name):
    page = await read.list_facts(m[name], page_size=100)
    return sorted(
        (
            *(
                end.label
                for end in (getattr(v, m[name]._ends[0]), getattr(v, m[name]._ends[1]))
            ),
            v.justification_count,
        )
        for v in page["results"]
    )


async def values(m, name, field):
    """Each edge of the class with the values of its justifications: `{(subject, object): [(value, evidence), ...]}`"""
    found = {}
    for view in (await read.list_facts(m[name], page_size=100))["results"]:
        detail = await read.get_fact(m[name], view.id)
        ends = tuple(getattr(view, end).label for end in m[name]._ends)
        found[ends] = sorted(
            (j.values[field], j.evidence[0].label) for j in detail.justifications
        )
    return found


# ---------------------------------------------------------------------------
# A value of the edge that leaves a wrapper
# ---------------------------------------------------------------------------


@no_type_check
async def test_the_share_of_an_alternative_is_kept_on_the_justification_and_tested(
    clear_database,
):
    m, n = await setup(clear_database)
    A, B, C = n["A"], n["B"], n["C"]
    await says(m, "F1", transfer(either((person(A), 80), (person(C), 20)), B))
    await run_pending_derivations()
    # (A at 80; C at 20 is under the rule's 50)
    assert await values(m, "GaveTo", "likelihood") == {("A", "B"): [(80, "F1")]}
    assert await edges(m, "SurelyGaveTo") == [("A", "B", 1)]


@no_type_check
async def test_two_sources_of_one_edge_keep_their_own_likelihoods(clear_database):
    m, n = await setup(clear_database)
    A, B, C = n["A"], n["B"], n["C"]
    await says(m, "F1", transfer(either((person(A), 80), (person(C), 20)), B))
    await says(m, "F2", transfer(either((person(A), 55), (person(C), 45)), B))
    await says(m, "F3", transfer(either((person(A), 40), (person(C), 60)), B))
    await run_pending_derivations()
    assert await values(m, "GaveTo", "likelihood") == {
        ("A", "B"): [(55, "F2"), (80, "F1")],
        ("C", "B"): [(60, "F3")],
    }
    # (the edge with a threshold of its own, and no value: 80 only for A, 60 for C)
    assert await edges(m, "SurelyGaveTo") == [("A", "B", 1), ("C", "B", 1)]


@no_type_check
async def test_a_changed_share_changes_the_justification_and_a_low_one_takes_the_edge_away(
    clear_database, db_driver
):
    m, n = await setup(clear_database)
    A, B, C = n["A"], n["B"], n["C"]
    made = await says(m, "F1", transfer(either((person(A), 80), (person(C), 20)), B))
    await run_pending_derivations()

    async def now(first, second):
        await (
            m["Factoid"]
            .Update(
                id=made.id,
                label="F1",
                statements=[
                    transfer(either((person(A), first), (person(C), second)), B)
                ],
            )
            .save()
        )
        await run_pending_derivations()

    await now(65, 35)
    assert await values(m, "GaveTo", "likelihood") == {("A", "B"): [(65, "F1")]}
    assert await edges(m, "SurelyGaveTo") == [("A", "B", 1)]
    await now(55, 45)
    assert await values(m, "GaveTo", "likelihood") == {("A", "B"): [(55, "F1")]}
    assert await edges(m, "SurelyGaveTo") == []
    await now(50, 50)
    # (each alternative alone: an exclusive wrapper gives one at a time)
    assert await values(m, "GaveTo", "likelihood") == {
        ("A", "B"): [(50, "F1")],
        ("C", "B"): [(50, "F1")],
    }
    await now(10, 90)
    assert await values(m, "GaveTo", "likelihood") == {("C", "B"): [(90, "F1")]}
    assert await edges(m, "SurelyGaveTo") == [("C", "B", 1)]
    await m["Factoid"].delete(made.id)
    await run_pending_derivations()
    assert await edges(m, "GaveTo") == []
    assert run(db_driver, "MATCH (d:PGDerived) RETURN count(d) AS n") == [{"n": 0}]
    assert run(db_driver, "MATCH (j:PGJustification) RETURN count(j) AS n") == [
        {"n": 0}
    ]


@no_type_check
async def test_a_relation_that_does_not_pass_through_the_wrapper_gives_nothing(
    clear_database,
):
    m, n = await setup(clear_database)
    A, B = n["A"], n["B"]
    await says(m, "direct", transfer(person(A), B))
    await says(m, "identified", transfer(identified(A), B))
    await run_pending_derivations()
    assert await edges(m, "GaveTo") == []
    assert await edges(m, "SurelyGaveTo") == []
    assert await edges(m, "GaveToAccordingTo") == [("A", "B", 1)]


@no_type_check
async def test_the_share_is_of_the_alternative_whatever_is_inside_it(clear_database):
    """An identification inside an alternative: the share is the alternative's edge, the name the identification's"""
    m, n = await setup(clear_database)
    A, B, C = n["A"], n["B"], n["C"]
    await says(
        m,
        "F1",
        transfer(either((identified(A, by="Jones", score=4), 70), (person(C), 30)), B),
    )
    await run_pending_derivations()
    assert await values(m, "GaveTo", "likelihood") == {("A", "B"): [(70, "F1")]}
    assert await edges(m, "SurelyGaveTo") == [("A", "B", 1)]
    page = await read.list_facts(m["GaveToAccordingTo"])
    assert [
        (v.giver.label, v.receiver.label, v.qualifiers.according_to)
        for v in page["results"]
    ] == [("A", "B", "Jones")]


@no_type_check
async def test_an_edge_through_a_wrapper_that_qualifies_is_not_plain(clear_database):
    m, n = await setup(clear_database)
    A, B, C = n["A"], n["B"], n["C"]
    await says(m, "F1", transfer(either((person(A), 80), (person(C), 20)), B))
    await says(m, "F2", transfer(identified(A), B))
    await run_pending_derivations()
    (gave,) = (await read.list_facts(m["GaveTo"]))["results"]
    assert gave.plain is False
    detail = await read.get_fact(m["GaveTo"], gave.id)
    (justification,) = detail.justifications
    # (the context has the wrapper, and what its edge says)
    (relation,) = [
        r for r in justification.context.relations if r["field"] == "given_by"
    ]
    assert relation["through"] == ["Either"]
    assert relation["properties"]["percent"] == 80
    # (an identification says nothing of the derivation: an edge through it alone is plain)
    (according,) = (await read.list_facts(m["GaveToAccordingTo"]))["results"]
    assert according.plain is True


# ---------------------------------------------------------------------------
# A value of the wrapper itself
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_value_of_a_wrapper_can_be_part_of_what_the_edge_is(clear_database):
    m, n = await setup(clear_database)
    A, B = n["A"], n["B"]
    await says(m, "F1", transfer(identified(A, by="Smith", score=5), B))
    await says(m, "F2", transfer(identified(A, by="Jones", score=3), B))
    await says(m, "F3", transfer(identified(A, by="Smith", score=9), B))
    # (under the score the rule asks for)
    await says(m, "F4", transfer(identified(A, by="Brown", score=2), B))
    await run_pending_derivations()
    page = await read.list_facts(m["GaveToAccordingTo"], page_size=100)
    assert sorted(
        (v.giver.label, v.qualifiers.according_to, v.justification_count)
        for v in page["results"]
    ) == [("A", "Jones", 1), ("A", "Smith", 2)]


# ---------------------------------------------------------------------------
# The edge that reaches what the relation is to
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_value_of_the_edge_to_an_entity_is_kept_and_tested(clear_database):
    m, n = await setup(clear_database)
    A, B, C, W = n["A"], n["B"], n["C"], n["W"]
    await says(m, "F1", transfer(person(A), B, (W, 9), (C, 3)))
    await says(m, "F2", transfer(person(A), B, (W, 4, "by hearsay")))
    await says(m, "F3", transfer(person(A), B, (C, 9, "by hearsay")))
    await run_pending_derivations()
    assert await values(m, "Witnessed", "certainty") == {
        ("W", "A"): [(4, "F2"), (9, "F1")],
        ("C", "A"): [(3, "F1"), (9, "F3")],
    }
    # (at least 8, and no note: of W in F1 alone)
    assert await edges(m, "SurelyWitnessed") == [("W", "A", 1)]


@no_type_check
async def test_a_value_met_on_the_way_of_two_relations_must_be_the_same_on_both(
    clear_database,
):
    m, n = await setup(clear_database)
    A, B, C, D, W = n["A"], n["B"], n["C"], n["D"], n["W"]
    await says(m, "F1", transfer(either((person(A), 9), (person(C), 3)), B, (W, 9)))
    await says(m, "F2", transfer(either((person(A), 9), (person(C), 3)), B, (D, 3)))
    await says(m, "F3", transfer(either((person(A), 5), (person(C), 4)), B, (W, 6)))
    await run_pending_derivations()
    # (W is as sure as A's share in F1, D as C's in F2; in F3 no share is 6)
    assert await edges(m, "AsSureAsTheShare") == [("D", "C", 1), ("W", "A", 1)]


@no_type_check
async def test_a_rebuild_finds_the_same_edges_and_values(clear_database, db_driver):
    m, n = await setup(clear_database)
    A, B, C, W = n["A"], n["B"], n["C"], n["W"]
    await says(m, "F1", transfer(either((person(A), 80), (person(C), 20)), B, (W, 9)))
    await says(
        m, "F2", transfer(either((identified(A, score=4), 55), (person(C), 45)), B)
    )
    await run_pending_derivations()

    def stored():
        return run(
            db_driver,
            "MATCH (j:PGJustification) RETURN j.key AS key, j.values AS v ORDER BY key",
        )

    before = stored()
    assert len(before) >= 4
    for name in DerivedRegistry.checked:
        await worker.rebuild(DerivedRegistry.checked[name])
    assert stored() == before


@no_type_check
async def test_inside_a_semantic_space_the_value_is_still_read(clear_database):
    m, n = await setup(clear_database)
    A, B, C = n["A"], n["B"], n["C"]
    await says(
        m,
        "F1",
        {
            "type": "Negative",
            "contents": [transfer(either((person(A), 80), (person(C), 20)), B)],
        },
    )
    await run_pending_derivations()
    assert await values(m, "GaveTo", "likelihood") == {("A", "B"): [(80, "F1")]}
    (gave,) = (await read.list_facts(m["GaveTo"]))["results"]
    detail = await read.get_fact(m["GaveTo"], gave.id)
    assert "Negative" in detail.justifications[0].context_labels
