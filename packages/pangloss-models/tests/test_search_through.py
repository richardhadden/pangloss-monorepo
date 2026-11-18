"""What is asked of the way of a relation, checked with no database: `edge` (the fields of an edge model) and the
steps of `through` (`Through`): the JSON the classes write, what `check_match` makes of it, and what it refuses"""

import datetime
from typing import no_type_check

import pytest
from pangloss_models import (
    Compare,
    Conjunction,
    Document,
    EdgeModel,
    Entity,
    Match,
    ModelRegistry,
    PanglossSearchError,
    ReifiedRelation,
    Rel,
    SemanticSpace,
    Text,
    Through,
    Var,
    ViaEdge,
    initialise,
)
from pangloss_models.search import (
    CheckedCondition,
    CheckedEdge,
    CheckedStep,
    Condition,
    EdgeCondition,
    ThroughStep,
    check_match,
    check_where,
    checked_value,
    checking_rule,
    edge_models_of_wrapper,
    field_kind,
    parse_where,
)
from pangloss_models.search_where import (
    EdgeWhere,
    WrapperWhere,
    export_search_patterns,
)
from pydantic import ValidationError


class Names(dict):
    __getattr__ = dict.__getitem__


@pytest.fixture
@no_type_check
def m():
    ModelRegistry._reset()

    class Certainty(EdgeModel):
        value: int
        on: datetime.date | None = None
        tags: list[str] = []

    class Share(EdgeModel):
        percent: int

    class Finer(Share):
        note: str | None = None

    class Lonely(EdgeModel):
        weight: int

    class Negative[T](SemanticSpace[T]):
        pass

    class Alternative[T](Conjunction):
        options: list[ViaEdge[T, Share]]

    class Identification[T](ReifiedRelation[T]):
        by: str | None = None
        score: int = 0

    class Reading[T](Identification[T]):
        folio: str | None = None

    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class Event(Document):
        who: list[
            ViaEdge[Person, Certainty]
            | Identification[Person]
            | Alternative[Person | Identification[Person]]
            | Negative[Person]
        ]
        at: Place
        year: int

    initialise(bind_database=False)
    yield Names(locals())
    ModelRegistry._reset()


def checked(m, where) -> list:
    return check_match(m.Event, Match(where=where))


def refused(m, where, saying):
    with pytest.raises(PanglossSearchError, match=saying):
        checked(m, where)


# ---------------------------------------------------------------------------
# The classes, and the JSON they write
# ---------------------------------------------------------------------------


def test_an_edge_model_and_a_wrapper_have_a_where_of_their_values(m):
    assert issubclass(m.Certainty.Where, EdgeWhere)
    assert issubclass(m.Identification.Where, WrapperWhere)
    assert issubclass(m.Alternative.Where, WrapperWhere)
    assert issubclass(m.Negative.Where, WrapperWhere)
    assert {"value", "on", "tags"} <= set(m.Certainty.Where.model_fields)
    assert {"by", "score"} <= set(m.Identification.Where.model_fields)
    # (a subclass has what its parent has, and its own)
    assert {"percent", "note"} <= set(m.Finer.Where.model_fields)
    assert {"by", "score", "folio"} <= set(m.Reading.Where.model_fields)
    # (what a wrapper points at is not one of its values)
    assert "target" not in m.Identification.Where.model_fields
    assert "options" not in m.Alternative.Where.model_fields
    assert "contents" not in m.Negative.Where.model_fields
    # (nothing to order by, and not in what the interface is told of patterns)
    assert not hasattr(m.Certainty, "Order") and not hasattr(m.Identification, "Order")
    exported = export_search_patterns(ModelRegistry._models)
    assert "Event" in exported
    assert not {"Certainty", "Share", "Identification", "Alternative"} & set(exported)
    # (the parametrised forms have none of their own)
    assert "Where" not in vars(m.Identification[m.Person])


def test_the_json_of_through_and_edge(m):
    where = m.Event.Where(
        who=Rel(
            is_="0194a1b2-0000-7000-8000-000000000001",
            through=[
                m.Negative,
                Through(
                    m.Alternative, edge=m.Share.Where(percent=Compare[int](gte=60))
                ),
                Through(
                    "Identification",
                    where=m.Identification.Where(by=Text(eq="a")),
                ),
            ],
            edge=m.Certainty.Where(
                on=Compare[datetime.date](lt=datetime.date(1600, 1, 1))
            ),
        )
    )
    written = where.to_json()["who"]
    assert written["through"] == [
        "Negative",
        {
            "type": "Alternative",
            "edge": {"type": "Share", "where": {"percent": {"gte": 60}}},
        },
        {"type": "Identification", "where": {"by": {"eq": "a"}}},
    ]
    assert written["edge"] == {
        "type": "Certainty",
        "where": {"on": {"lt": datetime.date(1600, 1, 1)}},
    }
    # (and read back as the models of the JSON)
    condition = parse_where(where)["who"]
    assert isinstance(condition, Condition)
    assert condition.through[0] == "Negative"
    assert isinstance(condition.through[1], ThroughStep)
    assert isinstance(condition.through[1].edge, EdgeCondition)
    assert isinstance(condition.edge, EdgeCondition)
    assert condition.operators() == ["is"]
    assert condition.of_relations


def test_an_edge_with_nothing_asked_and_a_step_with_nothing_asked(m):
    assert Rel(edge=m.Share.Where()).to_json() == {
        "edge": {"type": "Share", "where": {}}
    }
    assert Through(m.Alternative).to_json() == {"type": "Alternative"}
    # (a step with nothing asked is no more than its name)
    (c,) = checked(m, {"who": {"through": [{"type": "Alternative"}]}})
    assert (c.operator, c.through, c.steps) == ("exists", ("Alternative",), ())


# ---------------------------------------------------------------------------
# What it is checked to
# ---------------------------------------------------------------------------


def test_what_a_search_is_checked_to(m):
    (c,) = checked(
        m,
        {
            "who": {
                "through": [
                    "Negative",
                    {
                        "type": "Alternative",
                        "edge": {"type": "Share", "where": {"percent": {"gte": 60}}},
                    },
                    {"type": "Identification", "where": {"score": {"in": [1, 2]}}},
                ],
                "edge": {"type": "Certainty", "where": {"on": {"lt": "1600-01-01"}}},
            }
        },
    )
    assert isinstance(c, CheckedCondition)
    # (`through` alone: there is such a relation)
    assert (c.kind, c.operator, c.value, c.wrapped) == (
        "relation",
        "exists",
        True,
        True,
    )
    assert c.through == ("Negative", "Alternative", "Identification")
    alternative, identification = c.steps
    assert isinstance(alternative, CheckedStep) and alternative.model is m.Alternative
    assert alternative.items == []
    assert (
        isinstance(alternative.edge, CheckedEdge) and alternative.edge.model is m.Share
    )
    (percent,) = alternative.edge.items
    assert (percent.field, percent.kind, percent.operator, percent.value) == (
        "percent",
        "number",
        "gte",
        60,
    )
    assert identification.model is m.Identification and identification.edge is None
    (score,) = identification.items
    assert (score.operator, score.value) == ("in", [1, 2])
    # (a value of the edge is made the type of its field, as it is stored)
    assert c.edge is not None and c.edge.model is m.Certainty
    (on,) = c.edge.items
    assert on.kind == "temporal" and on.operator == "lt"
    assert on.value == checked_value(datetime.date, "temporal", "1600-01-01", "")


def test_each_operator_of_the_relation_carries_what_is_asked_of_the_way(m):
    conditions = checked(
        m,
        {
            "who": {
                "is": "0194a1b2-0000-7000-8000-000000000001",
                "exists": True,
                "type": "Person",
                "edge": {"type": "Certainty", "where": {"value": {"gte": 1}}},
            }
        },
    )
    assert sorted(c.operator for c in conditions) == ["exists", "is", "match"]
    assert all(c.edge is not None and c.edge.model is m.Certainty for c in conditions)


def test_the_edge_models_a_relation_can_have(m):
    kind, reach = field_kind(m.Event._meta.fields["who"])
    assert kind == "relation"
    # (its own, and that of the relation of the alternative on the way)
    assert set(reach.edges) == {m.Certainty, m.Share}
    _, at = field_kind(m.Event._meta.fields["at"])
    assert at.edges == ()
    assert edge_models_of_wrapper(m.Alternative) == [m.Share]
    assert edge_models_of_wrapper(m.Identification) == []


def test_a_parent_or_a_subclass_of_the_edge_model_will_do(m):
    # (`Finer` is a `Share`: its fields are tested as the properties of the edge)
    (c,) = checked(
        m,
        {
            "who": {
                "through": [
                    {
                        "type": "Alternative",
                        "edge": {"type": "Finer", "where": {"note": {"eq": "x"}}},
                    }
                ]
            }
        },
    )
    assert c.steps[0].edge.model is m.Finer
    # (and a subclass of the wrapper, with the parent's values)
    (c,) = checked(
        m,
        {"who": {"through": [{"type": "Reading", "where": {"by": {"eq": "a"}}}]}},
    )
    assert c.steps[0].model is m.Reading


def test_combinators_of_the_values(m):
    (c,) = checked(
        m,
        {
            "who": {
                "edge": {
                    "type": "Certainty",
                    "where": {
                        "$any_of": [
                            {"value": {"gte": 8}},
                            {"$not": {"tags": {"contains": "doubtful"}}},
                        ]
                    },
                }
            }
        },
    )
    (any_of,) = c.edge.items
    assert len(any_of.branches) == 2


# ---------------------------------------------------------------------------
# What is refused
# ---------------------------------------------------------------------------


def test_what_is_not_an_edge_model_or_not_this_relations(m):
    refused(m, {"who": {"edge": {"type": "Person"}}}, "'Person' is not an edge model")
    refused(m, {"who": {"edge": {"type": "Nope"}}}, "'Nope' is not an edge model")
    refused(
        m,
        {"who": {"edge": {"type": "Lonely"}}},
        r"who.edge: an edge of this relation is never a Lonely \(it can be Certainty, Share\)",
    )
    refused(
        m,
        {"at": {"edge": {"type": "Certainty"}}},
        r"at.edge: an edge of this relation is never a Certainty \(it has no edge model\)",
    )
    refused(
        m,
        {"year": {"edge": {"type": "Certainty"}}},
        "year: 'type', 'where', 'through' and 'edge' are for relations only",
    )


def test_what_an_edge_does_not_have(m):
    def edge(where):
        return {"who": {"edge": {"type": "Certainty", "where": where}}}

    refused(
        m, edge({"nope": {"eq": 1}}), "who.edge.nope: Certainty has no field 'nope'"
    )
    refused(m, edge({"label": {"eq": "x"}}), "who.edge.label: Certainty has no field")
    refused(
        m,
        edge({"value": {"contains": "x"}}),
        "who.edge.value.contains: not an operator",
    )
    refused(
        m,
        edge({"value": {"gte": "many"}}),
        "who.edge.value.gte: 'many' is not a valid int",
    )
    refused(m, edge({"value": {}}), "who.edge.value: no condition is given")
    refused(m, edge({"$spaces": ["Negative"]}), r"who.edge.\$spaces: not for an edge")
    refused(m, edge({"$any": {"contains": "x"}}), r"who.edge.\$any: not for an edge")
    refused(
        m,
        edge({"$not": {"$somewhere": [{"type": "Event"}]}}),
        r"who.edge.\$somewhere: not for an edge",
    )
    refused(
        m,
        edge({"value": {"through": ["Negative"]}}),
        "who.edge.value: 'type', 'where', 'through' and 'edge' are for relations only",
    )


def test_what_a_step_does_not_have(m):
    def step(**asked):
        return {"who": {"through": [{"type": "Identification", **asked}]}}

    refused(
        m,
        {"who": {"through": [{"type": "Person"}]}},
        "who.through: 'Person' is not a semantic space, conjunction or reified relation",
    )
    refused(
        m,
        {"at": {"through": [{"type": "Identification"}]}},
        "at.through: this relation does not pass through",
    )
    refused(
        m,
        step(where={"nope": {"eq": 1}}),
        "who.through.Identification.nope: Identification has no field 'nope'",
    )
    refused(
        m,
        step(where={"target": {"exists": True}}),
        "who.through.Identification.target",
    )
    refused(
        m,
        step(where={"score": {"starts_with": "x"}}),
        "who.through.Identification.score.starts_with: not an operator",
    )
    refused(
        m,
        step(edge={"type": "Share"}),
        r"who.through.Identification.edge: an edge of a Identification is never a Share \(it has no edge model\)",
    )
    refused(
        m,
        {"who": {"through": [{"type": "Alternative", "edge": {"type": "Certainty"}}]}},
        r"an edge of a Alternative is never a Certainty \(it can be Share\)",
    )


def test_what_is_not_read_at_all(m):
    """A key that is not one: the JSON is refused before it is checked against the models"""
    with pytest.raises(ValidationError):
        Match(where={"who": {"through": [{"type": "Alternative", "nope": 1}]}})
    with pytest.raises(ValidationError):
        Match(where={"who": {"edge": {"where": {}}}})
    with pytest.raises(ValidationError):
        Match(where={"who": {"edge": {"type": "Share", "nope": 1}}})
    with pytest.raises(ValidationError):
        Match(where={"who": {"through": [{"where": {}}]}})
    with pytest.raises(ValidationError):
        Match(where={"who": {"edge": {"type": "Share", "where": "x"}}})


def test_the_classes_take_only_the_right_kind_of_where(m):
    with pytest.raises(ValidationError):
        Rel(edge=m.Person.Where())
    with pytest.raises(ValidationError):
        Rel(edge=m.Identification.Where())
    with pytest.raises(ValidationError):
        Through(m.Alternative, edge=m.Identification.Where())
    with pytest.raises(ValidationError):
        Through(m.Alternative, where=m.Share.Where())
    with pytest.raises(ValueError, match="the pattern is of a Identification"):
        Through(m.Alternative, where=m.Identification.Where())
    with pytest.raises(TypeError, match="given twice"):
        Through(m.Alternative, type="Alternative")
    with pytest.raises(ValidationError):
        Through()
    # (a parent's pattern for a subclass, and the other way)
    Through(m.Reading, where=m.Identification.Where(by=Text(eq="a")))
    Through(m.Identification, where=m.Reading.Where(folio=Text(eq="1r")))
    with pytest.raises(ValidationError):
        m.Share.Where(percent=Compare[int](gte="many"))
    with pytest.raises(ValidationError):
        m.Share.Where(nope=1)


def test_the_limits_of_a_search_count_them(m):
    step = {
        "type": "Alternative",
        "edge": {"type": "Share", "where": {"percent": {"gte": 1}}},
    }
    with pytest.raises(PanglossSearchError, match="More than 50 patterns"):
        checked(m, {"who": {"through": [step] * 60}})


# ---------------------------------------------------------------------------
# Variables (only in the body of a rule)
# ---------------------------------------------------------------------------


def test_a_variable_on_the_way_is_only_of_a_rule(m):
    variable = {
        "who": {"edge": {"type": "Certainty", "where": {"value": {"$var": "p"}}}}
    }
    refused(m, variable, r"who.edge.value: a variable \('p'\) is only in a rule")
    p = Var("p", int)
    with checking_rule({"p": p}):
        (c,) = check_where(m.Event, parse_where(variable), [0, 0], "", False)
    (value,) = c.edge.items
    assert (value.operator, value.value) == ("var", p)
    # (written with the classes)
    where = m.Event.Where(
        who=Rel(
            through=[Through(m.Alternative, edge=m.Share.Where(percent=p))],
        )
    )
    assert where.to_json()["who"]["through"][0]["edge"]["where"] == {
        "percent": {"$var": "p"}
    }
    with checking_rule({"p": p}):
        (c,) = check_where(m.Event, parse_where(where), [0, 0], "", False)
    assert c.steps[0].edge.items[0].value is p
    # (of the wrong type, and inside an "or")
    with checking_rule({"p": Var("p", str)}):
        with pytest.raises(
            PanglossSearchError, match=r"a Var\[str\] \('p'\) cannot be"
        ):
            check_where(m.Event, parse_where(variable), [0, 0], "", False)
    inside = {
        "who": {
            "edge": {
                "type": "Certainty",
                "where": {"$any_of": [{"value": {"$var": "p"}}, {"value": {"eq": 1}}]},
            }
        }
    }
    with checking_rule({"p": p}):
        with pytest.raises(PanglossSearchError, match="cannot be inside"):
            check_where(m.Event, parse_where(inside), [0, 0], "", False)
