"""What the worker knows of a description's criteria (`pangloss_criteria.analysis`): whether a write can change a
match only of an entity it names (`reach`), the entities every match is joined to (`anchors`, with how many heads
away), whether the pattern is all one condition that holds them (`complete`), and its shape
(implementation_docs/matches-criteria.md, "As built", step 7). No database."""

import importlib
from typing import ClassVar

import pangloss_criteria.models
import pytest
from pangloss_criteria.analysis import FAR, LOCAL, Anchor, analyse, shape_of
from pangloss_criteria.pattern import SearchPattern, check_stored
from pangloss_models import (
    Cites,
    Document,
    EdgeModel,
    Embedded,
    Entity,
    ReifiedRelation,
    ViaEdge,
    hooks,
    initialise,
)
from pangloss_models.search import (
    CheckedCondition,
    CheckedIncoming,
    CheckedPattern,
    resolve_search_type,
)

X = "01a1c564-7def-70f0-bd21-410a35c82ab1"
Y = "01a1c564-7def-70f0-bd21-410a35c82ab2"
O = "01a1c564-7def-70f0-bd21-410a35c82ab3"
P = "01a1c564-7def-70f0-bd21-410a35c82ab4"
S = "01a1c564-7def-70f0-bd21-410a35c82ab5"


@pytest.fixture(autouse=True)
def placeholder_stands_in():
    """A document a relation to a person takes in the person's place (as `Unreconciled` does)"""
    stand_in = hooks.StandIn(
        document="Placeholder",
        stands_for=lambda model: getattr(model, "replaceable", False),
    )
    hooks.stand_ins.append(stand_in)
    yield
    hooks.stand_ins.remove(stand_in)


def models():
    # (the registry was reset, and a module is only run once: its class is declared again)
    importlib.reload(pangloss_criteria.models)
    MatchesCriteria = pangloss_criteria.models.MatchesCriteria

    class Certainty(EdgeModel):
        percent: int

    class Placeholder(Document):
        _meta = Document.Meta(create_directly=False)
        name: str

    class Person(Entity):
        replaceable: ClassVar[bool] = True
        title: str | None = None
        knows: list[Person] = []
        born_in: Place | None = None

    class Place(Entity):
        pass

    class Office(Entity):
        pass

    class Source(Document):
        title: str | None = None

    class InRole[T](ReifiedRelation[T]):
        role: str | None = None
        kind: Office | None = None

    class Detail(Embedded):
        note: str

    class Paragraph(Document):
        _meta = Document.Meta(create_directly=False)
        names: list[Person] = []

    class HoldsOffice(Document):
        holder: list[Person | MatchesCriteria[Person]]
        office: Office
        employer: Person
        witness: list[InRole[Person]] = []
        surely: list[ViaEdge[Person, Certainty]] = []
        detail: Detail | None = None
        parts: list[Paragraph] = []
        evidence: list[Cites[Source]] = []
        year: int | None = None

    initialise()
    return Person, HoldsOffice


def analysed(where: dict, type: str = "Person"):
    pattern = SearchPattern({"type": type, "where": where})
    items = check_stored(pattern, None, pangloss_criteria.models.EXCLUDED)
    return analyse(resolve_search_type(type), items)


def incoming(where: dict, field: str = "holder", type: str = "HoldsOffice") -> dict:
    return {"$incoming": [{"type": type, "field": field, "where": where}]}


def table(analysis) -> tuple:
    return (
        analysis.reach,
        analysis.anchors,
        analysis.complete,
        analysis.stored_anchors,
    )


SECRETARY = incoming({"employer": {"is": X}})

CASES = {
    # (the plain case: one `$incoming` that names the anchor)
    "secretary of X": (SECRETARY, (LOCAL, (Anchor((X,), 1),), True, [X])),
    "two ids in one document: two groups": (
        incoming({"office": {"is": O}, "employer": {"is": X}}),
        # (in the order of the keys of the pattern as it is stored)
        (LOCAL, (Anchor((X,), 1), Anchor((O,), 1)), True, [X, O]),
    ),
    "is_any: one group of several": (
        incoming({"employer": {"is_any": [X, Y]}}),
        (LOCAL, (Anchor((X, Y), 1),), True, [X, Y]),
    ),
    "an is inside $not is no anchor": (
        incoming({"$not": {"employer": {"is": X}}}),
        (LOCAL, (), False, []),
    ),
    "an is inside $any_of is no anchor": (
        incoming({"$any_of": [{"employer": {"is": X}}, {"office": {"is": O}}]}),
        (LOCAL, (), False, []),
    ),
    "a whole $incoming inside $not": (
        {"$not": SECRETARY},
        (LOCAL, (), False, []),
    ),
    "a literal of the root beside: anchored, not complete": (
        {"title": {"eq": "Dr"}, **SECRETARY},
        (LOCAL, (Anchor((X,), 1),), False, []),
    ),
    "two $incoming: not complete": (
        {
            "$incoming": [
                {
                    "type": "HoldsOffice",
                    "field": "holder",
                    "where": {"employer": {"is": X}},
                },
                {
                    "type": "HoldsOffice",
                    "field": "witness",
                    "where": {"office": {"is": O}},
                },
            ]
        },
        (LOCAL, (Anchor((X,), 1), Anchor((O,), 1)), False, []),
    ),
    "the root's own relation alone: complete": (
        {"knows": {"is": X}},
        (LOCAL, (Anchor((X,), 1),), True, [X]),
    ),
    "the root's own relation beside a literal": (
        {"knows": {"is": X}, "title": {"eq": "Dr"}},
        (LOCAL, (Anchor((X,), 1),), False, []),
    ),
    "a nested document on the way": (
        incoming({"parts": {"type": "Paragraph", "where": {"names": {"is": X}}}}),
        (LOCAL, (Anchor((X,), 1),), True, [X]),
    ),
    "an embedded object on the way": (
        incoming({"employer": {"is": X}, "detail": {"where": {"note": {"eq": "a"}}}}),
        (LOCAL, (Anchor((X,), 1),), True, [X]),
    ),
    "through a wrapper": (
        incoming({"witness": {"is": X}}),
        (LOCAL, (Anchor((X,), 1),), True, [X]),
    ),
    "through a wrapper named in through": (
        incoming({"witness": {"is": X, "through": ["InRole"]}}),
        (LOCAL, (Anchor((X,), 1),), True, [X]),
    ),
    "with an edge model and a condition on the edge": (
        incoming(
            {
                "surely": {
                    "is": X,
                    "edge": {"type": "Certainty", "where": {"percent": {"gte": 60}}},
                }
            }
        ),
        (LOCAL, (Anchor((X,), 1),), True, [X]),
    ),
    "by a way (via): a wrapper of it with a value": (
        incoming(
            {
                "witness": {
                    "is": X,
                    "via": [{"type": "InRole", "where": {"role": {"eq": "scribe"}}}],
                }
            }
        ),
        (LOCAL, (Anchor((X,), 1),), True, [X]),
    ),
    "by a way: an edge of it": (
        incoming(
            {
                "surely": {
                    "is": X,
                    "via": [{"type": "Certainty", "where": {"percent": {"gte": 60}}}],
                }
            }
        ),
        (LOCAL, (Anchor((X,), 1),), True, [X]),
    ),
    "the way of what refers to the root": (
        {
            "$incoming": [
                {
                    "type": "HoldsOffice",
                    "field": "witness",
                    "via": [{"type": "InRole", "where": {"kind": {"is": O}}}],
                    "where": {"employer": {"is": X}},
                }
            ]
        },
        # (which office the wrapper is of is in the same head; it is not counted as an anchor)
        (LOCAL, (Anchor((X,), 1),), True, [X]),
    ),
    "a way alone, a wrapper of it by its own relation: local, no anchor": (
        incoming(
            {"witness": {"via": [{"type": "InRole", "where": {"kind": {"is": O}}}]}}
        ),
        (LOCAL, (), False, []),
    ),
    "$any is no field: no anchor": (
        incoming({"$any": {"is": X}}),
        (LOCAL, (), False, []),
    ),
    "a second entity with conditions: far": (
        incoming({"employer": {"type": "Person", "where": {"title": {"eq": "Dr"}}}}),
        (FAR, (), False, []),
    ),
    "an is beyond a second entity: far, two hops": (
        incoming({"employer": {"type": "Person", "where": {"born_in": {"is": P}}}}),
        (FAR, (Anchor((P,), 2),), False, []),
    ),
    "a second entity beside an anchor of the first hop": (
        incoming(
            {
                "office": {"is": O},
                "employer": {"type": "Person", "where": {"born_in": {"is": P}}},
            }
        ),
        (FAR, (Anchor((P,), 2), Anchor((O,), 1)), False, []),
    ),
    "the root's own relation to a second entity with conditions: far": (
        {"born_in": {"type": "Place", "where": {"label": {"eq": "Wien"}}}},
        (FAR, (), False, []),
    ),
    "a citation with conditions: far": (
        # (a pattern of a citation is of its node: what it cites is another head)
        incoming(
            {
                "employer": {"is": X},
                "evidence": {"type": "PGCitation", "where": {"target_id": {"eq": S}}},
            }
        ),
        (FAR, (Anchor((X,), 1),), False, []),
    ),
    "an id of a citation: an anchor": (
        incoming({"evidence": {"is": S}}),
        (LOCAL, (Anchor((S,), 1),), True, [S]),
    ),
    "a relation that takes a stand-in too: an anchor all the same": (
        incoming({"employer": {"is": X}, "year": {"gt": 1500}}),
        (LOCAL, (Anchor((X,), 1),), True, [X]),
    ),
    "no anchor at all": (
        incoming({"year": {"gt": 1500}}),
        (LOCAL, (), False, []),
    ),
    "nothing asked": ({}, (LOCAL, (), False, [])),
}


@pytest.mark.parametrize("name", list(CASES))
def test_what_a_pattern_is(name):
    models()
    where, expected = CASES[name]

    assert table(analysed(where)) == expected


def test_a_relation_that_takes_a_stand_in_takes_one():
    """(the case above is of a relation that takes the stand-in: it is one)"""
    Person, HoldsOffice = models()
    options = HoldsOffice._meta.fields.relation_fields["employer"].type_options
    assert "Placeholder" in {o.annotated_type.__name__ for o in options}


def test_what_refers_to_a_document_node_is_far():
    """(`check_match` refuses `$incoming` of a document: what `analyse` does with one is asked of it directly. What
    refers to a document is a head that cites it)"""
    models()
    inner = check_stored(
        SearchPattern({"type": "HoldsOffice", "where": {"employer": {"is": X}}}),
        None,
        pangloss_criteria.models.EXCLUDED,
    )
    referred = CheckedCondition(
        "$incoming",
        "incoming",
        "match",
        CheckedIncoming(
            CheckedPattern(resolve_search_type("HoldsOffice"), inner), ("parts",)
        ),
    )

    found = analyse(resolve_search_type("Source"), [referred])

    assert table(found) == (FAR, (), False, [])


def test_mentions_on_a_document_is_no_anchor():
    models()

    found = analysed({"$mentions": {"is": X}}, type="HoldsOffice")

    assert table(found) == (LOCAL, (), False, [])
    # (and a field of the document, by contrast)
    assert analysed({"employer": {"is": X}}, type="HoldsOffice").anchors == (
        Anchor((X,), 1),
    )


# --- the shape --------------------------------------------------------------------------------------------------------


def shape(where: dict, type: str = "Person") -> str:
    return shape_of(SearchPattern({"type": type, "where": where}))


def test_patterns_that_differ_only_in_their_ids_and_values_have_one_shape():
    assert shape(SECRETARY) == shape(incoming({"employer": {"is": Y}}))
    assert shape(incoming({"employer": {"is_any": [X, Y]}})) == shape(
        incoming({"employer": {"is_any": [P]}})
    )
    assert shape({"title": {"eq": "Dr"}, **SECRETARY}) == shape(
        {"title": {"eq": "Prof"}, **incoming({"employer": {"is": O}})}
    )
    assert shape({"born_in": {"type": "Place", "where": {"label": {"eq": "A"}}}}) == (
        shape({"born_in": {"type": "Place", "where": {"label": {"eq": "B"}}}})
    )
    assert shape(incoming({"year": {"between": [1500, 1510]}})) == shape(
        incoming({"year": {"between": [1400, 1600]}})
    )


def test_another_field_type_or_operator_is_another_shape():
    first = shape(SECRETARY)
    assert first != shape(incoming({"office": {"is": X}}))
    assert first != shape(incoming({"employer": {"is_any": [X]}}))
    assert first != shape(incoming({"employer": {"is": X}}, field="witness"))
    assert first != shape(SECRETARY, type="Place")
    assert first != shape({"title": {"eq": "Dr"}, **SECRETARY})
    assert shape({"title": {"eq": "Dr"}}) != shape({"title": {"ne": "Dr"}})
    assert shape(
        {"born_in": {"type": "Place", "where": {"label": {"eq": "A"}}}}
    ) != shape({"born_in": {"type": "Person", "where": {"label": {"eq": "A"}}}})
