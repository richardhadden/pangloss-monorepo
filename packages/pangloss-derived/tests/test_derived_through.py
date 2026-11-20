"""Rules that ask something of the way of a relation (`Through`, `edge=`), with no database: what a rule is checked to,
the query it compiles to, what is refused and how it is said, and when a rule counts as changed"""

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
    Through,
    Var,
    ViaEdge,
    initialise,
)

from pangloss_derived import (
    DerivedEdge,
    Object,
    PanglossDerivedError,
    PerJustification,
    Subject,
    SymmetricLabel,
    rule,
)
from pangloss_derived.check import PathValue
from pangloss_derived.compile import compile_rule, join_order
from pangloss_derived.registry import DerivedRegistry


class Names(dict):
    """The classes a function declared, by name: `m.Person`"""

    __getattr__ = dict.__getitem__


@no_type_check
def models():
    class Share(EdgeModel):
        percent: int
        tags: list[str] = []

    class Certainty(EdgeModel):
        value: int

    class Either[T](Conjunction):
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
        year: int

    class GaveTo(DerivedEdge):
        giver: Annotated[Person, Subject()]
        receiver: Annotated[Person, Object()]
        likelihood: Annotated[int, PerJustification()]

    class GaveBy(DerivedEdge):
        giver: Annotated[Person, Subject()]
        receiver: Annotated[Person, Object()]
        by: str

    class Plain(DerivedEdge):
        giver: Annotated[Person, Subject()]
        receiver: Annotated[Person, Object()]

    class CoGivers(DerivedEdge):
        _meta = DerivedEdge.Meta(symmetric=True)
        first: Annotated[Person, SymmetricLabel("giver")]
        second: Annotated[Person, SymmetricLabel("giver")]
        receiver: Person

    return Names(locals())


def declared(make):
    """Declare the models and what `make(m)` declares, and initialise"""
    m = models()
    make(m)
    initialise(bind_database=False)
    return m


def refused(make, saying):
    with pytest.raises(PanglossDerivedError, match=saying):
        declared(make)


@pytest.fixture(autouse=True)
def a_dialect(monkeypatch):
    """The queries are made with a backend's dialect: Memgraph's, with no database behind it"""
    import pangloss_cypher.search_query
    import pangloss_derived.compile
    from pangloss_memgraph.databases.memgraph.dialect import MemgraphDialect

    dialect = MemgraphDialect()
    monkeypatch.setattr(pangloss_derived.compile, "dialect", lambda: dialect)
    monkeypatch.setattr(pangloss_cypher.search_query, "dialect", lambda: dialect)


def query(name):
    checked = DerivedRegistry.checked[name]
    return compile_rule(checked, checked.seeds[0].node)


# ---------------------------------------------------------------------------
# What a rule is checked to, and its query
# ---------------------------------------------------------------------------


@no_type_check
def test_a_variable_of_the_edge_that_leaves_a_wrapper_is_a_value_of_the_relation():
    def make(m):
        @rule
        def gave_to(a: Var[m.Person], b: Var[m.Person], p: Var[int]):
            return m.GaveTo.Derive(giver=a, receiver=b, likelihood=p).when(
                m.Transfer.Where(
                    given_by=Rel(
                        is_=a,
                        through=[Through(m.Either, edge=m.Share.Where(percent=p))],
                    ),
                    given_to=b,
                ),
                p >= 60,
            )

    declared(make)
    checked = DerivedRegistry.checked["gave_to"]
    (edge,) = [e for e in checked.edges if e.field == "given_by"]
    assert edge.through == ("Either",)
    assert edge.values == (PathValue(0, "edge", "percent", "p"),)
    # (the variable is taken out of what is tested of the step: it is bound, not compared with a value)
    (step,) = edge.steps
    assert step.model.__name__ == "Either"
    assert step.items == [] and step.edge.items == []
    assert checked.head["likelihood"] == ("var", "p")
    text, params = query("gave_to")
    # (a row for each such wrapper of the path; its edge's value; the rule's own comparison, once it is bound)
    assert "UNWIND [i" in text and "AS ti_0_0" in text
    assert "relationships(rp_0)[ti_0_0] AS te_0_0" in text
    assert "te_0_0.`percent` IS NOT NULL" in text
    assert "te_0_0.`percent` >=" in text
    assert "Either" in params.values() and 60 in params.values()
    # (as Datalog, for `explain`)
    described = checked.describe()
    assert "given_by(n_0, v_a) via Either" in described
    assert "percent(given_by(n_0, v_a) Either edge, p)" in described


@no_type_check
def test_a_condition_with_no_variable_is_a_test_of_the_path():
    def make(m):
        @rule
        def surely(a: Var[m.Person], b: Var[m.Person]):
            return m.Plain.Derive(giver=a, receiver=b).when(
                m.Transfer.Where(
                    given_by=Rel(
                        is_=a,
                        through=[
                            Through(
                                m.Either,
                                edge=m.Share.Where(percent=Compare[int](gte=60)),
                            ),
                            Through(
                                m.Identification,
                                where=m.Identification.Where(score=Compare[int](gte=3)),
                            ),
                        ],
                    ),
                    given_to=b,
                )
            )

    declared(make)
    checked = DerivedRegistry.checked["surely"]
    (edge,) = [e for e in checked.edges if e.field == "given_by"]
    assert edge.values == ()
    assert [s.model.__name__ for s in edge.steps] == ["Either", "Identification"]
    assert len(edge.steps[0].edge.items) == 1 and len(edge.steps[1].items) == 1
    text, params = query("surely")
    assert "UNWIND [" not in text
    assert text.count("IN range(1, size(nodes(rp_0)) - 2)") == 2
    assert all(n in params.values() for n in (60, 3))
    assert "[2 conditions on the way]" in checked.describe()


@no_type_check
def test_a_value_of_a_wrapper_and_one_of_the_last_edge():
    def make(m):
        @rule
        def gave_by(a: Var[m.Person], b: Var[m.Person], who: Var[str]):
            return m.GaveBy.Derive(giver=a, receiver=b, by=who).when(
                m.Transfer.Where(
                    given_by=Rel(
                        is_=a,
                        through=[
                            Through(
                                m.Identification,
                                where=m.Identification.Where(identified_by=who),
                            )
                        ],
                    ),
                    given_to=b,
                )
            )

        @rule
        def seen(w: Var[m.Person], a: Var[m.Person], c: Var[int]):
            return m.GaveTo.Derive(giver=w, receiver=a, likelihood=c).when(
                m.Transfer.Where(
                    given_to=a,
                    witnesses=Rel(is_=w, edge=m.Certainty.Where(value=c)),
                ),
                c > 2,
            )

    declared(make)
    (edge,) = [
        e for e in DerivedRegistry.checked["gave_by"].edges if e.field == "given_by"
    ]
    assert edge.values == (PathValue(0, "node", "identified_by", "who"),)
    text, _ = query("gave_by")
    assert "nodes(rp_0)[ti_0_0] AS tn_0_0" in text
    assert "tn_0_0.`identified_by` IS NOT NULL" in text
    seen = DerivedRegistry.checked["seen"]
    (edge,) = [e for e in seen.edges if e.field == "witnesses"]
    assert edge.values == (PathValue(None, "edge", "value", "c"),)
    text, _ = query("seen")
    k = edge.index
    assert f"last(relationships(rp_{k})) AS le_{k}" in text
    assert f"le_{k}.`value` IS NOT NULL" in text
    assert f"le_{k}.`value` >" in text
    assert "value(witnesses(n_0, v_w) edge, c)" in seen.describe()


@no_type_check
def test_a_variable_met_twice_joins_the_two_places():
    """The share of the giver and the certainty of the witness have to be the same number"""

    def make(m):
        @rule
        def same(a: Var[m.Person], w: Var[m.Person], p: Var[int]):
            return m.GaveTo.Derive(giver=a, receiver=w, likelihood=p).when(
                m.Transfer.Where(
                    given_by=Rel(
                        is_=a,
                        through=[Through(m.Either, edge=m.Share.Where(percent=p))],
                    ),
                    witnesses=Rel(is_=w, edge=m.Certainty.Where(value=p)),
                )
            )

        @rule
        def of_the_year(a: Var[m.Person], b: Var[m.Person], y: Var[int]):
            return m.GaveTo.Derive(giver=a, receiver=b, likelihood=y).when(
                m.Transfer.Where(
                    given_by=Rel(
                        is_=a,
                        through=[Through(m.Either, edge=m.Share.Where(percent=y))],
                    ),
                    given_to=b,
                    year=y,
                )
            )

    declared(make)
    text, _ = query("same")
    # (bound at the first place it is met, compared at the second)
    assert text.count("IS NOT NULL") == 2
    assert (
        "le_1.`value` = te_0_0.`percent`" in text
        or "te_0_0.`percent` = le_1.`value`" in text
    )
    text, _ = query("of_the_year")
    assert "te_0_0.`percent` = n_0.`year`" in text


@no_type_check
def test_a_nested_pattern_with_a_variable_only_on_its_way_is_part_of_the_rule():
    def make(m):
        @rule
        def nested(a: Var[m.Person], b: Var[m.Person], c: Var[int]):
            return m.GaveTo.Derive(giver=a, receiver=b, likelihood=c).when(
                m.Transfer.Where(
                    given_by=a,
                    given_to=b,
                    witnesses=Rel(
                        match=m.Person.Where(), edge=m.Certainty.Where(value=c)
                    ),
                )
            )

    declared(make)
    checked = DerivedRegistry.checked["nested"]
    (edge,) = [e for e in checked.edges if e.field == "witnesses"]
    assert edge.values == (PathValue(None, "edge", "value", "c"),)
    assert edge.target.startswith("n_")


@no_type_check
def test_a_symmetric_rule_with_the_same_asked_of_both_is_matched_once():
    def make(m):
        def likely(m, who):
            return Rel(
                is_=who,
                through=[
                    Through(m.Either, edge=m.Share.Where(percent=Compare[int](gte=50)))
                ],
            )

        @rule
        def co_givers(a: Var[m.Person], b: Var[m.Person], r: Var[m.Person]):
            return m.CoGivers.Derive(first=a, second=b, receiver=r).when(
                m.Transfer.Where(given_by=likely(m, a), given_to=r),
                m.Transfer.Where(given_by=likely(m, b), given_to=r),
            )

        @rule
        def uneven(a: Var[m.Person], b: Var[m.Person], r: Var[m.Person]):
            return m.CoGivers.Derive(first=a, second=b, receiver=r).when(
                m.Transfer.Where(given_by=likely(m, a), given_to=r),
                m.Transfer.Where(given_by=b, given_to=r),
            )

    declared(make)
    assert DerivedRegistry.checked["co_givers"].symmetric_body is True
    # (what is asked of the way differs between the two: both orders are tried)
    assert DerivedRegistry.checked["uneven"].symmetric_body is False


@no_type_check
def test_what_is_asked_of_the_way_is_part_of_what_the_rule_is():
    """A changed threshold is a changed rule (it is built again)"""

    def hash_with(at_least, variable=False):
        def make(m):
            @rule
            def gave_to(a: Var[m.Person], b: Var[m.Person], p: Var[int]):
                share = (
                    m.Share.Where(percent=p)
                    if variable
                    else m.Share.Where(percent=Compare[int](gte=at_least))
                )
                return m.GaveTo.Derive(
                    giver=a, receiver=b, likelihood=p if variable else 1
                ).when(
                    m.Transfer.Where(
                        given_by=Rel(is_=a, through=[Through(m.Either, edge=share)]),
                        given_to=b,
                        **({} if variable else {"year": p}),
                    )
                )

        declared(make)
        return DerivedRegistry.checked["gave_to"].hash

    assert hash_with(60) == hash_with(60)
    assert hash_with(60) != hash_with(61)
    assert hash_with(60) != hash_with(60, variable=True)


# ---------------------------------------------------------------------------
# What is refused
# ---------------------------------------------------------------------------


@no_type_check
def test_a_variable_on_the_way_needs_the_relation_to_bind_what_it_is_to():
    def make(m):
        @rule
        def gave_to(a: Var[m.Person], b: Var[m.Person], p: Var[int]):
            return m.GaveTo.Derive(giver=a, receiver=b, likelihood=p).when(
                m.Transfer.Where(
                    given_by=Rel(
                        through=[Through(m.Either, edge=m.Share.Where(percent=p))]
                    ),
                    given_to=b,
                ),
                m.Transfer.Where(given_by=a),
            )

    refused(make, "given_by: a variable on the way of a relation .* not 'exists'")


@no_type_check
def test_a_variable_of_the_wrong_type_or_of_a_list_is_refused():
    def wrong_type(m):
        @rule
        def gave_to(a: Var[m.Person], b: Var[m.Person], p: Var[str]):
            return m.GaveBy.Derive(giver=a, receiver=b, by=p).when(
                m.Transfer.Where(
                    given_by=Rel(
                        is_=a,
                        through=[Through(m.Either, edge=m.Share.Where(percent=p))],
                    ),
                    given_to=b,
                )
            )

    refused(
        wrong_type,
        r"given_by.through.Either.edge.percent: a Var\[str\] \('p'\) cannot be a value of this field \(int\)",
    )

    def of_a_list(m):
        @rule
        def gave_to(a: Var[m.Person], b: Var[m.Person], t: Var[str]):
            return m.GaveBy.Derive(giver=a, receiver=b, by=t).when(
                m.Transfer.Where(
                    given_by=Rel(
                        is_=a,
                        through=[Through(m.Either, edge=m.Share.Where(tags=t))],
                    ),
                    given_to=b,
                )
            )

    refused(of_a_list, "given_by: tags is a list")


@no_type_check
def test_a_variable_inside_an_or_on_the_way_is_refused_as_anywhere():
    def make(m):
        @rule
        def gave_to(a: Var[m.Person], b: Var[m.Person], p: Var[int]):
            share = m.Share.Where(percent=p) | m.Share.Where(
                percent=Compare[int](gte=90)
            )
            return m.GaveTo.Derive(giver=a, receiver=b, likelihood=p).when(
                m.Transfer.Where(
                    given_by=Rel(is_=a, through=[Through(m.Either, edge=share)]),
                    given_to=b,
                )
            )

    refused(make, r"cannot be inside 'given_by.through.Either.edge.\$any_of'")


@no_type_check
def test_what_the_models_do_not_have_is_refused_with_the_place_of_it():
    def not_its_edge(m):
        @rule
        def gave_to(a: Var[m.Person], b: Var[m.Person], p: Var[int]):
            return m.GaveTo.Derive(giver=a, receiver=b, likelihood=p).when(
                m.Transfer.Where(
                    given_by=Rel(
                        is_=a,
                        through=[
                            Through(m.Identification, edge=m.Share.Where(percent=p))
                        ],
                    ),
                    given_to=b,
                )
            )

    refused(
        not_its_edge,
        "pattern 1, Transfer: given_by.through.Identification.edge: an edge of a Identification is never a Share",
    )

    def not_this_relation(m):
        @rule
        def gave_to(a: Var[m.Person], b: Var[m.Person], p: Var[int]):
            return m.GaveTo.Derive(giver=a, receiver=b, likelihood=p).when(
                m.Transfer.Where(
                    given_by=a,
                    given_to=Rel(is_=b, edge=m.Certainty.Where(value=p)),
                )
            )

    refused(not_this_relation, "given_to.edge: an edge of this relation is never a")

    def no_wrappers(m):
        @rule
        def gave_to(a: Var[m.Person], b: Var[m.Person], p: Var[int]):
            return m.GaveTo.Derive(giver=a, receiver=b, likelihood=p).when(
                m.Transfer.Where(
                    given_by=a,
                    given_to=Rel(
                        is_=b,
                        through=[Through(m.Either, edge=m.Share.Where(percent=p))],
                    ),
                )
            )

    refused(no_wrappers, "given_to.through: this relation does not pass through")


@no_type_check
def test_a_relation_of_a_wrapper_on_the_way_is_refused_in_the_body_of_a_rule():
    """(a search can ask `InRole.role` of a step; a rule's own compiler cannot yet, so it is refused, not left out)"""
    from uuid import uuid4

    baker = uuid4()

    def with_roles(m, asked):
        class Role(Entity):
            pass

        class InRole[T](ReifiedRelation[T]):
            role: Role | None = None
            n: int = 0

        class Hiring(Document):
            hired_by: InRole[m.Person]
            hired: m.Person

        @rule
        def gave_to(a: Var[m.Person], b: Var[m.Person]):
            return m.Plain.Derive(giver=a, receiver=b).when(
                Hiring.Where(
                    hired_by=Rel(
                        is_=a, through=[Through(InRole, where=asked(InRole.Where))]
                    ),
                    hired=b,
                )
            )

    saying = (
        "pattern 1, Hiring: hired_by.through.InRole.role: a relation of a wrapper is not tested in the body of a "
        "rule yet"
    )
    for asked in (
        lambda W: W(role=baker),
        lambda W: W(role=Rel(is_any=[baker])),
        lambda W: W(role=Rel(exists=False)),
        lambda W: W(n=Compare[int](eq=1)) | W(role=baker),
        lambda W: ~W(role=baker),
    ):
        refused(lambda m, asked=asked: with_roles(m, asked), saying)
    # (its values alone are a test of the way, as before)
    declared(lambda m: with_roles(m, lambda W: W(n=Compare[int](eq=1))))


@no_type_check
def test_a_variable_only_on_the_way_and_not_in_the_head_is_still_bound():
    """A value used only in a comparison of the rule"""

    def make(m):
        @rule
        def gave_to(a: Var[m.Person], b: Var[m.Person], p: Var[int], y: Var[int]):
            return m.GaveTo.Derive(giver=a, receiver=b, likelihood=y).when(
                m.Transfer.Where(
                    given_by=Rel(
                        is_=a,
                        through=[Through(m.Either, edge=m.Share.Where(percent=p))],
                    ),
                    given_to=b,
                    year=y,
                ),
                p >= 75,
            )

    declared(make)
    text, params = query("gave_to")
    assert "te_0_0.`percent` >=" in text and 75 in params.values()


@no_type_check
def test_each_relation_is_walked_from_what_is_found_already_backwards_if_need_be():
    """From each seed, the relations of its pattern, then the other pattern reached back along the relation the two
    share (to its target, already found), not every `Transfer` matched on its own; each head after its node"""
    import re

    def make(m):
        @rule
        def co_givers(a: Var[m.Person], b: Var[m.Person], r: Var[m.Person]):
            return m.CoGivers.Derive(first=a, second=b, receiver=r).when(
                m.Transfer.Where(given_by=a, given_to=r),
                m.Transfer.Where(given_by=b, given_to=r),
            )

    declared(make)
    checked = DerivedRegistry.checked["co_givers"]

    def order(start):
        steps = []
        for clause in join_order(checked, start):
            if found := re.match(
                r"MATCH rp_\d+ = \((\w+)\)-\[re_\d+:`(\w+)`\].*\((\w+)\)$", clause
            ):
                steps.append(found.groups())
            elif found := re.match(r"MATCH \((\w+)\)-.*\(hd_\w+:HeadNode\)$", clause):
                steps.append(("head of", found.group(1)))
            else:
                steps.append(clause)
        return steps

    assert [s.node for s in checked.seeds] == ["n_0", "n_1"]
    assert order("n_0") == [
        "UNWIND $seeds AS seed",
        ("head of", "n_0"),
        ("n_0", "given_by", "v_a"),
        ("n_0", "given_to", "v_r"),
        ("n_1", "given_to", "v_r"),
        ("head of", "n_1"),
        ("n_1", "given_by", "v_b"),
    ]
    assert order("n_1") == [
        "UNWIND $seeds AS seed",
        ("head of", "n_1"),
        ("n_1", "given_by", "v_b"),
        ("n_1", "given_to", "v_r"),
        ("n_0", "given_to", "v_r"),
        ("head of", "n_0"),
        ("n_0", "given_by", "v_a"),
    ]
