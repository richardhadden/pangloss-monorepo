"""`via`, the places of the way of a relation asked for in order (implementation_docs/relation-steps-plan.md, step 3),
checked with no database: what `check_match` makes of it (`CheckedVia`), what it counts, and what it refuses. The
shapes are those of the conformance file `test_relation_steps_live.py`, with a few more classes"""

from typing import no_type_check

import pytest
from pangloss_models import (
    Document,
    EdgeModel,
    Entity,
    Match,
    ModelRegistry,
    PanglossSearchError,
    ReifiedRelation,
    SemanticSpace,
    ViaEdge,
    ViaItem,
    initialise,
)
from pangloss_models.search import (
    MAX_PATTERNS,
    MAX_VALUES,
    CheckedCondition,
    CheckedVia,
    Condition,
    check_match,
    check_where,
    conditions_of,
    field_kind,
    parse_where,
)
from pydantic import ValidationError

JOHN = "0194a1b2-0000-7000-8000-000000000001"


class Names(dict):
    __getattr__ = dict.__getitem__


@pytest.fixture
@no_type_check
def m():
    ModelRegistry._reset()

    class Certainty(EdgeModel):
        value: int
        note: str | None = None

    class Lonely(EdgeModel):
        weight: int

    class RoleType(Entity):
        pass

    class Step[T](ReifiedRelation[T]):
        pass

    class EdgeA[T](Step[T]):
        a: int

    class Finer[T](EdgeA[T]):
        fine: int = 0

    class EdgeB[T](ReifiedRelation[T]):
        b: int

    class EdgeC[T](ReifiedRelation[T]):
        c: int

    class InRole[T](ReifiedRelation[T]):
        role: RoleType

    class Negative[T](SemanticSpace[T]):
        pass

    class Person(Entity):
        pass

    class Doc(Document):
        chain: list[EdgeA[EdgeB[EdgeC[Person]]]]
        twice: list[EdgeA[EdgeA[Person]]]
        edge_in: list[ViaEdge[EdgeA[Person], Certainty]]
        edge_out: list[EdgeA[ViaEdge[Person, Certainty]]]
        both: list[ViaEdge[EdgeA[ViaEdge[Person, Certainty]], Certainty]]
        role: list[InRole[Person]]
        plain: list[ViaEdge[Person, Certainty]]

    initialise(bind_database=False)
    yield Names(locals())
    ModelRegistry._reset()


def item(type_, **where):
    """`item("EdgeA", a=1)` asks `a` to be 1; a value that is a dict is the condition as it is"""
    made: dict = {"type": type_}
    if where:
        made["where"] = {
            k: v if isinstance(v, dict) else {"eq": v} for k, v in where.items()
        }
    return made


def checked(m, where, **match) -> list:
    return check_match(m.Doc, Match(where=where, **match))


def refused(m, where, saying, **match):
    with pytest.raises(PanglossSearchError, match=saying):
        checked(m, where, **match)


# ---------------------------------------------------------------------------
# The JSON
# ---------------------------------------------------------------------------


def test_an_item_is_a_type_and_a_where_that_may_be_left_out(m):
    condition = parse_where(
        {"chain": {"via": [item("EdgeA", a=1), {"type": "EdgeB"}]}}
    )["chain"]
    assert isinstance(condition, Condition)
    first, second = condition.via
    assert isinstance(first, ViaItem) and first.type == "EdgeA"
    assert isinstance(first.where["a"], Condition)
    assert second.where is None
    # (`via` is of a relation: not an operator, and enough alone)
    assert condition.operators() == []
    assert condition.of_relations
    # (a key it does not have is refused, as of `through` and `edge`)
    with pytest.raises(ValidationError, match="Extra inputs"):
        parse_where({"chain": {"via": [{"type": "EdgeA", "edge": {}}]}})
    with pytest.raises(ValidationError):
        parse_where({"chain": {"via": "EdgeA"}})


def test_the_fields_of_an_item_are_named_as_in_python_as_those_of_edge_and_through_are(
    m,
):
    (c,) = checked(m, {"edge_in": {"via": [item("Certainty", value=9)]}})
    assert c.via[0].items[0].field == "value"
    # (a search names fields as Python does, everywhere: not `noteText` for `note_text`)
    refused(
        m,
        {"edge_in": {"via": [item("Certainty", Value=9)]}},
        "edge_in.via.0.Certainty.Value: Certainty has no field 'Value'",
    )


# ---------------------------------------------------------------------------
# What it is checked to
# ---------------------------------------------------------------------------


def test_a_mixed_via_is_checked_to_its_items_in_the_order_given(m):
    (c,) = checked(
        m,
        {
            "both": {
                "via": [
                    item("Certainty", value=9),
                    {"type": "EdgeA"},
                    item("Certainty", value={"lte": 2}),
                ]
            }
        },
    )
    assert isinstance(c, CheckedCondition)
    # (alone: there is a relation by such a way)
    assert (c.kind, c.operator, c.value, c.wrapped) == (
        "relation",
        "exists",
        True,
        True,
    )
    assert all(isinstance(v, CheckedVia) for v in c.via)
    assert [(v.kind, v.model) for v in c.via] == [
        ("edge", m.Certainty),
        ("wrapper", m.EdgeA),
        ("edge", m.Certainty),
    ]
    outer, wrapper, inner = c.via
    (value,) = outer.items
    assert (value.field, value.kind, value.operator, value.value) == (
        "value",
        "number",
        "eq",
        9,
    )
    assert wrapper.items == []
    assert (inner.items[0].operator, inner.items[0].value) == ("lte", 2)
    # (nothing of `through` or `edge` is made of it)
    assert (c.through, c.steps, c.edge) == ((), (), None)


def test_the_order_is_kept_and_an_item_may_come_twice(m):
    (c,) = checked(m, {"twice": {"via": [item("EdgeA", a=2), item("EdgeA", a=1)]}})
    assert [v.items[0].value for v in c.via] == [2, 1]
    (c,) = checked(m, {"chain": {"via": [item("EdgeC", c=3), item("EdgeA", a=1)]}})
    assert [v.model for v in c.via] == [m.EdgeC, m.EdgeA]


def test_every_operator_of_the_relation_carries_the_via(m):
    conditions = checked(
        m,
        {
            "chain": {
                "is": JOHN,
                "exists": True,
                "type": "Person",
                "through": ["EdgeB"],
                "via": [item("EdgeA", a=1)],
            }
        },
    )
    assert sorted(c.operator for c in conditions) == ["exists", "is", "match"]
    assert all(
        [v.model for v in c.via] == [m.EdgeA] and c.through == ("EdgeB",)
        for c in conditions
    )
    # (and `exists: false`: has no relation by such a way)
    (c,) = checked(m, {"chain": {"exists": False, "via": [item("EdgeA", a=1)]}})
    assert (c.operator, c.value, len(c.via)) == ("exists", False, 1)


def test_a_wrapper_is_met_by_its_class_or_one_above_or_below_it(m):
    # (`Finer` is an `EdgeA`; `Step` is what `EdgeA` is a kind of)
    (c,) = checked(m, {"chain": {"via": [item("Finer", fine=1, a=2)]}})
    assert c.via[0].model is m.Finer
    assert sorted(e.field for e in c.via[0].items) == ["a", "fine"]
    (c,) = checked(m, {"chain": {"via": [{"type": "Step"}]}})
    assert c.via[0].model is m.Step


def test_a_relation_knows_the_wrappers_on_its_way(m):
    _, chain = field_kind(m.Doc._meta.fields["chain"])
    assert set(chain.wrappers) == {m.EdgeA, m.EdgeB, m.EdgeC}
    _, role = field_kind(m.Doc._meta.fields["role"])
    # (not those of a wrapper's own relations: `InRole.role` is not on the way)
    assert role.wrappers == (m.InRole,)
    _, plain = field_kind(m.Doc._meta.fields["plain"])
    assert plain.wrappers == () and not plain.wrapped


def test_combinators_of_the_values_of_an_item(m):
    (c,) = checked(
        m,
        {
            "edge_in": {
                "via": [
                    {
                        "type": "Certainty",
                        "where": {
                            "$any_of": [
                                {"value": {"gte": 8}},
                                {"note": {"exists": True}},
                            ]
                        },
                    },
                    {"type": "EdgeA", "where": {"$not": {"a": {"eq": 2}}}},
                ]
            }
        },
    )
    (any_of,) = c.via[0].items
    assert len(any_of.branches) == 2
    (not_,) = c.via[1].items
    assert not_.items[0].field == "a"


def test_any_relation_and_mentions_take_any_edge_model_and_any_wrapper(m):
    via = [item("EdgeA", a=4), item("Lonely", weight=1), {"type": "Negative"}]
    for key in ("$any", "$mentions"):
        (c,) = checked(m, {key: {"is": JOHN, "via": via}})
        assert c.field == key
        assert [v.model for v in c.via] == [m.EdgeA, m.Lonely, m.Negative]
        # (alone, too)
        (c,) = checked(m, {key: {"via": via}})
        assert c.operator == "exists" and len(c.via) == 3
    # (but what is not an edge model or a wrapper is not)
    refused(
        m,
        {"$any": {"via": [{"type": "Person"}]}},
        r"\$any.via.0: 'Person' is not an edge model",
    )
    # (an edge model with nothing asked means nothing there either)
    refused(m, {"$mentions": {"via": [{"type": "Lonely"}]}}, "ask something of it")
    # (and `exists` is refused of both, as without `via`)
    refused(
        m,
        {"$any": {"exists": False, "via": via}},
        r"\$any.exists: not an operator here",
    )
    refused(
        m,
        {"$mentions": {"exists": False, "via": via}},
        r"\$mentions.exists: not an operator here",
    )


def test_via_in_a_pattern_for_what_a_relation_points_at(m):
    # (a field of the class searched is not the only place: an `$incoming` pattern's where takes it too)
    (c,) = check_match(
        m.Person,
        Match(
            where={
                "$incoming": [
                    {
                        "type": "Doc",
                        "where": {"role": {"via": [item("InRole")]}},
                    }
                ]
            }
        ),
    )
    (inner,) = c.value.pattern.items
    assert inner.field == "role" and inner.via[0].model is m.InRole


# ---------------------------------------------------------------------------
# conditions_of, counting
# ---------------------------------------------------------------------------


def test_the_conditions_of_the_items_are_found_by_conditions_of(m):
    found = [
        (c.field, c.operator)
        for c in conditions_of(
            checked(
                m,
                {
                    "label": {"eq": "x"},
                    "$not": {
                        "both": {
                            "is": JOHN,
                            "via": [
                                item("Certainty", value=9),
                                item("EdgeA", a=1),
                            ],
                        }
                    },
                },
            )
        )
    ]
    assert found == [("label", "eq"), ("both", "is"), ("value", "eq"), ("a", "eq")]


def test_each_item_is_a_pattern_of_the_search(m):
    budget = [0, 0]
    check_where(
        m.Doc,
        parse_where(
            {
                "both": {
                    "via": [
                        item("Certainty", value=9),
                        item("EdgeA", a=1),
                        {"type": "EdgeA"},
                    ]
                }
            }
        ),
        budget,
        "",
        True,
    )
    assert budget[0] == 3
    # (as an `edge` is one, and a step of `through` with a `where` none)
    budget = [0, 0]
    check_where(
        m.Doc,
        parse_where(
            {
                "both": {
                    "edge": item("Certainty", value=9),
                    "through": [item("EdgeA", a=1)],
                }
            }
        ),
        budget,
        "",
        True,
    )
    assert budget[0] == 1


def test_items_up_to_the_limits_and_no_further(m):
    many = [{"type": "EdgeA"}] * MAX_PATTERNS
    (c,) = checked(m, {"twice": {"via": many}})
    assert len(c.via) == MAX_PATTERNS
    refused(
        m,
        {"twice": {"via": many + [{"type": "EdgeA"}]}},
        f"More than {MAX_PATTERNS} patterns",
    )
    # (the patterns of the rest of the search count too)
    refused(
        m,
        {"twice": {"via": many}, "chain": {"type": "Person"}},
        f"More than {MAX_PATTERNS} patterns",
    )
    refused(
        m,
        {"twice": {"via": [{"type": "EdgeA"}] * (MAX_VALUES + 1)}},
        f"twice.via: more than {MAX_VALUES} items",
    )
    refused(m, {"twice": {"via": []}}, "twice.via: needs at least one item")


# ---------------------------------------------------------------------------
# What is refused
# ---------------------------------------------------------------------------


def test_what_is_neither_an_edge_model_nor_a_wrapper(m):
    for name in ("Nope", "Person", "Doc", "RoleType"):
        refused(
            m,
            {"chain": {"via": [item("EdgeA", a=1), {"type": name}]}},
            f"chain.via.1: '{name}' is not an edge model, semantic space, conjunction or reified relation",
        )


def test_an_edge_model_no_edge_of_the_relation_has(m):
    refused(
        m,
        {"chain": {"via": [item("Certainty", value=1)]}},
        r"chain.via.0.Certainty: an edge of this relation is never a Certainty \(it has no edge model\)",
    )
    refused(
        m,
        {"plain": {"via": [item("Lonely", weight=1)]}},
        r"plain.via.0.Lonely: an edge of this relation is never a Lonely \(it can be Certainty\)",
    )
    # (`edge_out` has an `EdgeA` whose edge onwards is a `Certainty`: that is not on the way of `chain`, whose
    # `EdgeA` is of an `EdgeB`. As `edge` says)
    refused(
        m,
        {"chain": {"edge": item("Certainty", value=1)}},
        "chain.edge: an edge of this relation is never a Certainty",
    )
    (c,) = checked(m, {"edge_out": {"via": [item("Certainty", value=1)]}})
    assert c.via[0].model is m.Certainty
    # (a step of `through` is of the class wherever it is used: its edge onwards may be one)
    (c,) = checked(
        m,
        {"chain": {"through": [{"type": "EdgeA", "edge": item("Certainty", value=1)}]}},
    )
    assert c.steps[0].edge.model is m.Certainty


def test_an_edge_model_with_nothing_asked_of_it(m):
    for given in ({"type": "Certainty"}, {"type": "Certainty", "where": {}}):
        refused(
            m,
            {"plain": {"via": [given]}},
            "plain.via.0.Certainty: ask something of it",
        )


def test_a_wrapper_where_the_relation_has_none_or_not_that_one(m):
    refused(
        m,
        {"plain": {"via": [{"type": "EdgeA"}]}},
        "plain.via.0.EdgeA: this relation does not pass through semantic spaces, conjunctions or reified relations",
    )
    refused(
        m,
        {"chain": {"via": [item("InRole")]}},
        r"chain.via.0.InRole: this relation never passes through a InRole \(it can pass through EdgeA, EdgeB, EdgeC\)",
    )
    refused(
        m,
        {"role": {"via": [{"type": "Negative"}]}},
        r"role.via.0.Negative: this relation never passes through a Negative \(it can pass through InRole\)",
    )


def test_what_a_wrapper_holds_or_points_at_is_not_asked_in_an_item(m):
    refused(
        m,
        {"chain": {"via": [item("EdgeA", target={"exists": True})]}},
        "chain.via.0.EdgeA.target",
    )
    # (its own relations by which they are (step 2), not by a pattern)
    checked(m, {"role": {"via": [item("InRole", role={"is": JOHN})]}})
    refused(
        m,
        {"role": {"via": [item("InRole", role={"type": "RoleType"})]}},
        "role.via.0.InRole.role: a relation of a wrapper",
    )
    refused(
        m,
        {"chain": {"via": [item("EdgeA", nope=1)]}},
        r"chain.via.0.EdgeA.nope: EdgeA has no field 'nope' \(it has a, target\)",
    )
    refused(
        m,
        {"chain": {"via": [{"type": "EdgeA", "where": {"$spaces": ["Negative"]}}]}},
        r"chain.via.0.EdgeA.\$spaces: not for a wrapper \(EdgeA\)",
    )
    refused(
        m,
        {"edge_in": {"via": [item("Certainty", value={"contains": "x"})]}},
        "edge_in.via.0.Certainty.value.contains: not an operator",
    )


def test_via_is_of_relations_only(m):
    refused(
        m,
        {"label": {"via": [item("EdgeA", a=1)]}},
        "label: 'type', 'where', 'through', 'edge' and 'via' are for relations only",
    )
    refused(
        m,
        {"$somewhere": [{"type": "Doc", "via": [item("EdgeA", a=1)]}]},
        r"\$somewhere: each is a pattern",
    )


def test_a_wrapper_the_search_leaves_out_is_refused(m):
    refused(
        m,
        {"chain": {"via": [item("EdgeA", a=1)]}},
        "chain.via.0: 'EdgeA' is a wrapper the search leaves out",
        exclude_wrappers=["EdgeA"],
    )
    # (a class below one left out is left out)
    refused(
        m,
        {"chain": {"via": [item("EdgeB", b=1), item("Finer", a=1)]}},
        "chain.via.1: 'Finer' is a wrapper the search leaves out",
        exclude_wrappers=["EdgeA"],
    )
    # (wherever it is: inside a combinator, of `$any`)
    refused(
        m,
        {"$not": {"$any": {"is": JOHN, "via": [{"type": "EdgeC"}]}}},
        r"\$any.via.0: 'EdgeC' is a wrapper the search leaves out",
        exclude_wrappers=["EdgeC"],
    )
    # (another wrapper, an edge model, or a class above the one left out (it is met by others too) will do)
    checked(
        m,
        {"chain": {"via": [item("EdgeB", b=1)]}},
        exclude_wrappers=["EdgeA"],
    )
    checked(
        m,
        {"edge_in": {"via": [item("Certainty", value=1)]}},
        exclude_wrappers=["EdgeA"],
    )
    checked(m, {"chain": {"via": [item("EdgeA", a=1)]}}, exclude_wrappers=["Finer"])


# ---------------------------------------------------------------------------
# `$incoming` (step 5): the way from what refers to the entity
# ---------------------------------------------------------------------------


def incoming(m, **given) -> CheckedCondition:
    match = given.pop("match", {})
    (condition,) = check_match(
        m.Person, Match(where={"$incoming": [{"type": "Doc", **given}]}, **match)
    )
    assert isinstance(condition, CheckedCondition)
    return condition


def incoming_refused(m, saying, **given):
    with pytest.raises(PanglossSearchError, match=saying):
        incoming(m, **given)


def test_incoming_takes_a_via_checked_as_that_of_the_relation_is(m):
    condition = incoming(m, field="chain", via=[item("EdgeA", a=1), item("EdgeC", c=3)])
    assert condition.kind == "incoming"
    assert [(each.kind, each.model) for each in condition.via] == [
        ("wrapper", m.EdgeA),
        ("wrapper", m.EdgeC),
    ]
    condition = incoming(
        m, field="edge_in", via=[item("Certainty", value=9), {"type": "EdgeA"}]
    )
    assert [each.kind for each in condition.via] == ["edge", "wrapper"]
    assert condition.via[1].items == []
    # (with `through`, by name, as before)
    condition = incoming(m, field="chain", through=["EdgeB"], via=[item("EdgeA", a=1)])
    assert condition.through == ("EdgeB",) and len(condition.via) == 1
    # (none without one)
    assert incoming(m, field="chain").via == ()


def test_incoming_with_no_field_takes_what_any_of_the_relations_can_have(m):
    # (`chain` has an EdgeB, `plain` a Certainty: with no field, either is on the way of some relation)
    condition = incoming(m, via=[item("EdgeB", b=2)])
    assert condition.via[0].model is m.EdgeB
    assert incoming(m, via=[item("Certainty", value=9)]).via[0].kind == "edge"
    incoming_refused(m, "never a Lonely", via=[item("Lonely", weight=1)])
    incoming_refused(m, "never passes through a Negative", via=[{"type": "Negative"}])


def test_incoming_asks_a_wrapper_of_the_way_by_its_own_relation(m):
    condition = incoming(m, field="role", via=[item("InRole", role={"is": JOHN})])
    inner = [c for c in conditions_of(condition) if c is not condition]
    assert [(c.kind, c.operator, str(c.value)) for c in inner] == [
        ("relation", "is", JOHN)
    ]


def test_what_a_via_of_incoming_cannot_ask(m):
    incoming_refused(
        m,
        r"\$incoming.via.0.EdgeA: this relation does not pass through",
        field="plain",
        via=[{"type": "EdgeA"}],
    )
    incoming_refused(
        m,
        r"\$incoming.via.0.Certainty: an edge of this relation is never a Certainty",
        field="chain",
        via=[item("Certainty", value=1)],
    )
    incoming_refused(
        m,
        r"\$incoming.via.0.InRole: this relation never passes through a InRole",
        field="chain",
        via=[{"type": "InRole"}],
    )
    incoming_refused(m, r"\$incoming.via: needs at least one item", via=[])
    incoming_refused(
        m, "ask something of it", field="plain", via=[{"type": "Certainty"}]
    )
    incoming_refused(m, "is not an edge model", via=[{"type": "Person"}])
    # (what the wrapper holds)
    incoming_refused(
        m,
        r"\$incoming.via.0.EdgeA.target",
        field="chain",
        via=[item("EdgeA", target={"is": JOHN})],
    )
    # (a wrapper the search leaves out)
    incoming_refused(
        m,
        r"\$incoming.via.0: 'EdgeA' is a wrapper the search leaves out",
        field="chain",
        via=[item("EdgeA", a=1)],
        match={"exclude_wrappers": ["EdgeA"]},
    )


def test_each_item_of_a_via_of_incoming_is_a_pattern_of_the_search(m):
    one = [{"type": "EdgeA"}]
    incoming(m, field="chain", via=one * min(MAX_VALUES, MAX_PATTERNS - 1))
    with pytest.raises(PanglossSearchError, match="More than"):
        check_match(
            m.Person,
            Match(
                where={
                    "$incoming": [
                        {"type": "Doc", "field": "chain", "via": one * MAX_VALUES}
                    ]
                    * (MAX_PATTERNS // MAX_VALUES + 1)
                }
            ),
        )
