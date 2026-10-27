"""Checking a structured search pattern against the models"""

import datetime
import enum
from decimal import Decimal
from typing import TypedDict

import pytest
from pangloss_models import initialise
from pangloss_models.exceptions import PanglossSearchError, PanglossUnknownTypeError
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.trait import Trait
from pangloss_models.search import (
    CheckedCondition,
    Match,
    SearchRequest,
    check_match,
    resolve_search_type,
)


class Status(enum.Enum):
    DRAFT = "draft"


class Notes(TypedDict):
    pages: int


def models():
    class Person(Entity):
        pass

    class Letter(Document):
        title: str
        pages: int | None = None
        sent: datetime.date | None = None
        price: Decimal | None = None
        status: Status | None = None
        tags: list[str]
        sender: Person
        notes: Notes | None = None

    class Marked(Trait):
        pass

    initialise()
    return Person, Letter


def check(Letter, **where):
    return check_match(Letter, Match.model_validate({"where": where}))


def test_each_operator_becomes_a_checked_condition_with_a_value_of_the_fields_type():
    Person, Letter = models()

    assert check(Letter, sent={"gt": "1500-01-01"}) == [
        CheckedCondition("sent", "temporal", "gt", datetime.date(1500, 1, 1))
    ]
    assert check(Letter, status={"in": ["draft"]})[0].value == ["draft"]
    assert check(Letter, title={"contains": "VeNice"})[0].value == "venice"
    assert check(Letter, label={"starts_with": "A"})[0].kind == "text"
    assert check(Letter, tags={"contains_any": ["a", "b"]})[0].kind == "list"
    assert check(Letter, pages={"between": [1, 5]})[0].value == [1, 5]
    # a Decimal is compared as a number
    assert check(Letter, price={"gte": "1.10"}) == [
        CheckedCondition("price", "decimal", "gte", 1.1)
    ]


def test_several_operators_and_fields_are_all_kept():
    Person, Letter = models()

    got = check(Letter, pages={"gt": 1, "lt": 9}, title={"eq": "x"})

    assert sorted((c.field, c.operator) for c in got) == [
        ("pages", "gt"),
        ("pages", "lt"),
        ("title", "eq"),
    ]


def test_a_relation_is_by_the_id_of_what_it_points_at():
    Person, Letter = models()
    one = "0194d9c0-0000-7000-8000-000000000001"

    got = check(Letter, sender={"is": one})

    assert (got[0].kind, got[0].operator, str(got[0].value)) == ("relation", "is", one)
    assert check(Letter, sender={"is_any": [one]})[0].operator == "is_any"


@pytest.mark.parametrize(
    "where, message",
    [
        ({"nothing": {"eq": 1}}, "no field 'nothing'"),
        ({"title": {}}, "no condition"),
        ({"title": {"gt": "a"}}, "title.gt: not an operator"),
        ({"pages": {"contains": "x"}}, "pages.contains"),
        ({"sender": {"eq": "x"}}, "sender.eq"),
        ({"tags": {"eq": "x"}}, "tags.eq"),
        ({"pages": {"eq": "many"}}, "not a valid int"),
        ({"pages": {"eq": True}}, "not a valid int"),
        ({"pages": {"between": [1]}}, "two values"),
        ({"pages": {"in": []}}, "at least one"),
        ({"sent": {"eq": "tomorrow"}}, "not a valid date"),
        ({"status": {"eq": "lost"}}, "not a valid Status"),
        ({"notes": {"eq": 1}}, "cannot be searched yet"),
        ({"title": {"eq": None}}, "not a valid str"),
    ],
)
def test_what_cannot_be_searched_is_refused_naming_the_field(where, message):
    Person, Letter = models()

    with pytest.raises(PanglossSearchError, match=message):
        check(Letter, **where)


def test_the_pattern_must_be_for_the_class_searched():
    Person, Letter = models()

    check_match(Letter, Match(type="Letter"))
    with pytest.raises(PanglossSearchError, match="Person"):
        check_match(Letter, Match(type="Person"))


def test_an_operator_that_does_not_exist_is_not_accepted():
    with pytest.raises(ValueError):
        Match.model_validate({"where": {"title": {"matches": "x"}}})
    with pytest.raises(ValueError):
        Match.model_validate({"unknown": 1})
    with pytest.raises(ValueError, match="not supported"):
        Match.model_validate({"where": {"$nonsense": {"eq": 1}}})
    with pytest.raises(ValueError):  # (1 is not true)
        Match.model_validate({"where": {"title": {"exists": 1}}})


def test_the_request_has_a_page_with_limits():
    request = SearchRequest.model_validate({"type": "Letter"})
    assert (request.page, request.page_size) == (1, 25)
    for bad in ({"page": 0}, {"page_size": 0}, {"page_size": 101}):
        with pytest.raises(ValueError):
            SearchRequest.model_validate(bad)


def test_the_type_searched_is_a_document_or_an_entity():
    Person, Letter = models()

    assert resolve_search_type("Letter") is Letter
    assert resolve_search_type("Person") is Person
    for name in ("Marked", "Nothing"):
        with pytest.raises(PanglossUnknownTypeError):
            resolve_search_type(name)


def nested_models():
    class Person(Entity):
        born: int | None = None

    class Poet(Person):
        pass

    class Place(Entity):
        pass

    class Letter(Document):
        title: str
        sender: Person
        copies_to: list[Person]
        visited: list[Place | Person]

    initialise()
    return Person, Poet, Place, Letter


def test_a_relation_can_have_a_pattern_for_what_it_points_at():
    Person, Poet, Place, Letter = nested_models()

    got = check(
        Letter,
        sender={"type": "Poet", "where": {"born": {"lt": 1600}}},
        copies_to={"where": {"label": {"contains": "Sm"}}},
    )

    sender, copies = got
    assert sender.operator == copies.operator == "match"
    assert sender.value.model is Poet
    assert sender.value.items == [CheckedCondition("born", "number", "lt", 1600)]
    # (left out, the type is the one the relation allows)
    assert copies.value.model is Person
    assert copies.value.items[0].value == "sm"


def test_a_pattern_and_an_id_can_be_asked_together_and_a_relation_can_be_tested_for_having_any():
    Person, Poet, Place, Letter = nested_models()
    one = "0194d9c0-0000-7000-8000-000000000001"

    got = check(
        Letter, sender={"is": one, "type": "Person"}, copies_to={"exists": False}
    )

    assert sorted(c.operator for c in got) == ["exists", "is", "match"]


def test_patterns_nest():
    Person, Poet, Place, Letter = nested_models()

    class Note(Document):
        about: Letter

    initialise()
    got = check_match(
        Note,
        Match.model_validate(
            {"where": {"about": {"where": {"sender": {"where": {"born": {"gt": 1}}}}}}}
        ),
    )

    about = got[0].value
    assert about.model is Letter
    assert about.items[0].value.model is Person


@pytest.mark.parametrize(
    "where, message",
    [
        ({"sender": {"type": "Place"}}, "not one of the types the relation allows"),
        ({"sender": {"type": "Letter"}}, "not one of the types the relation allows"),
        ({"sender": {"type": "Nothing"}}, "no model called 'Nothing'"),
        ({"visited": {"where": {}}}, "'type' is needed"),
        ({"title": {"where": {}}}, "for relations only"),
        (
            {"sender": {"where": {"nothing": {"eq": 1}}}},
            "sender.nothing: Person has no field",
        ),
        ({"sender": {"where": {"born": {"gt": "x"}}}}, "sender.born.gt"),
    ],
)
def test_a_pattern_for_a_relation_is_checked_against_what_it_may_point_at(
    where, message
):
    Person, Poet, Place, Letter = nested_models()

    with pytest.raises(PanglossSearchError, match=message):
        check(Letter, **where)


def test_combinators_make_all_any_of_and_not():
    Person, Poet, Place, Letter = nested_models()

    got = check_match(
        Letter,
        Match.model_validate(
            {
                "where": {
                    "$any_of": [{"title": {"eq": "a"}}, {"title": {"eq": "b"}}],
                    "$not": {"title": {"eq": "c"}},
                    "$all": [{"title": {"ne": "a"}}, {"title": {"starts_with": "z"}}],
                }
            }
        ),
    )

    any_of, not_, gt, lt = got
    assert [[c.value for c in branch] for branch in any_of.branches] == [["a"], ["b"]]
    assert [c.value for c in not_.items] == ["c"]
    assert (gt.operator, lt.operator) == ("ne", "starts_with")


def test_the_combinators_need_the_right_shape_and_are_limited():
    for where in (
        {"$any_of": []},
        {"$any_of": {"title": {"eq": "a"}}},
        {"$not": [{"title": {"eq": "a"}}]},
        {"$all": [1]},
    ):
        with pytest.raises(ValueError):
            Match.model_validate({"where": where})
    deep = {"title": {"eq": "a"}}
    for _ in range(60):
        deep = {"$not": deep}
    with pytest.raises(ValueError, match="nested more than"):
        Match.model_validate({"where": deep})


def test_there_is_a_limit_to_the_patterns_for_relations():
    Person, Poet, Place, Letter = nested_models()
    many = {"$all": [{"sender": {"where": {}}} for _ in range(51)]}

    with pytest.raises(PanglossSearchError, match="More than 50 patterns"):
        check(Letter, **many)


def test_a_pattern_is_the_same_dumped_and_read_again():
    where = {
        "sender": {"type": "Person", "where": {"born": {"lt": 1}}},
        "$any_of": [{"title": {"in": ["a"]}}],
    }
    match = Match.model_validate({"type": "Letter", "where": where})

    assert match.model_dump(by_alias=True, exclude_unset=True, mode="json") == {
        "type": "Letter",
        "where": where,
    }


def wrapper_models():
    from pangloss_models.model_bases.semantic_space import SemanticSpace

    class Negative[T](SemanticSpace[T]):
        pass

    class Person(Entity):
        pass

    class Statement(Document):
        plain: Person
        about: list[Person | Negative[Person]]

    class Factoid(Document):
        statements: list[Statement | Negative[Statement]]

    initialise()
    return Person, Statement, Factoid


def test_a_relation_through_a_wrapper_is_to_what_is_inside_it():
    Person, Statement, Factoid = wrapper_models()

    got = check_match(
        Factoid,
        Match.model_validate(
            {
                "where": {
                    "statements": {
                        "where": {"about": {"through": ["Negative"], "exists": True}}
                    }
                }
            }
        ),
    )

    statements = got[0]
    assert statements.wrapped and statements.value.model is Statement
    about = statements.value.items[0]
    assert (about.wrapped, about.through) == (True, ("Negative",))
    # (and a relation that has no wrapper is not)
    plain = check_match(
        Statement, Match.model_validate({"where": {"plain": {"exists": True}}})
    )
    assert plain[0].wrapped is False


@pytest.mark.parametrize(
    "model, where, message",
    [
        ("Statement", {"plain": {"through": ["Negative"]}}, "does not pass through"),
        ("Factoid", {"statements": {"through": ["Person"]}}, "not a semantic space"),
        ("Factoid", {"statements": {"through": []}}, "needs the names"),
        ("Factoid", {"$spaces": ["Negative"]}, r"\$spaces: only for a pattern"),
        ("Person", {"$spaces": ["Negative"]}, r"\$spaces: only for a pattern"),
        (
            "Factoid",
            {"statements": {"where": {"$spaces": ["Person"]}}},
            "not a semantic space",
        ),
        (
            "Person",
            {"$somewhere": [{"type": "Statement"}]},
            "only for a search of documents",
        ),
        ("Factoid", {"$somewhere": [{"type": "Person"}]}, "not a document type"),
        ("Factoid", {"$somewhere": [{"where": {}}]}, "each is a pattern"),
        (
            "Factoid",
            {"$somewhere": [{"type": "Statement", "exists": True}]},
            "each is a pattern",
        ),
        (
            "Factoid",
            {"statements": {"where": {"$mentions": {"exists": True}}}},
            "only for a search of documents",
        ),
        ("Factoid", {"$mentions": {"contains": "x"}}, "not an operator here"),
        ("Factoid", {"$any": {"exists": True}}, "not an operator here"),
        ("Factoid", {"$any": {"where": {}}}, "'type' is needed"),
        ("Factoid", {"$any": {}}, "no condition"),
    ],
)
def test_the_conditions_of_a_node_and_its_document_are_checked(model, where, message):
    Person, Statement, Factoid = wrapper_models()
    cls = {"Person": Person, "Statement": Statement, "Factoid": Factoid}[model]

    with pytest.raises(PanglossSearchError, match=message):
        check_match(cls, Match.model_validate({"where": where}))


def test_any_relation_of_a_node_takes_the_label_conditions_too():
    Person, Statement, Factoid = wrapper_models()
    one = "0194d9c0-0000-7000-8000-000000000001"

    got = check_match(
        Statement,
        Match.model_validate({"where": {"$any": {"is": one, "contains": "Ab"}}}),
    )

    assert sorted((c.field, c.operator) for c in got) == [
        ("$any", "is"),
        ("label", "contains"),
    ]
    assert [c.value for c in got if c.field == "label"] == ["ab"]


def test_incoming_is_one_pattern_or_a_list_and_has_a_type():
    one = Match.model_validate({"where": {"$incoming": {"type": "Letter"}}})
    many = Match.model_validate(
        {"where": {"$incoming": [{"type": "A", "field": "x"}, {"type": "B"}]}}
    )

    assert [i.type for i in one.where["$incoming"]] == ["Letter"]
    assert [i.field for i in many.where["$incoming"]] == ["x", None]
    for bad in ({"field": "x"}, {"type": "A", "extra": 1}, {"type": "A", "is": "x"}):
        with pytest.raises(ValueError):
            Match.model_validate({"where": {"$incoming": [bad]}})
    assert Match.model_validate(
        {"where": {"$incoming": [{"type": "A", "where": {"x": {"eq": 1}}}]}}
    ).model_dump(by_alias=True, exclude_unset=True, mode="json") == {
        "where": {"$incoming": [{"type": "A", "where": {"x": {"eq": 1}}}]}
    }


def test_an_embedded_field_is_searched_by_a_pattern_for_it():
    from pangloss_models.model_bases.embedded import Embedded

    class When(Embedded):
        _meta = Embedded.Meta(abstract=True)
        sort_day: int | None = None

    class Exact(When):
        year: int

    class Span(When):
        earliest: Exact

    class Note(Document):
        when: When

    initialise()
    # (the type may be left out: the field is typed with one class)
    checked = check_match(
        Note, Match(where={"when": {"where": {"sort_day": {"gt": 5}}}})
    )
    assert checked[0].operator == "match" and checked[0].value.model is When
    # a subclass, and its own fields, and an embedded object inside one
    check_match(
        Note, Match(where={"when": {"type": "Exact", "where": {"year": {"eq": 1}}}})
    )
    check_match(
        Note,
        Match(
            where={
                "when": {
                    "type": "Span",
                    "where": {"earliest": {"where": {"year": {"gte": 1500}}}},
                }
            }
        ),
    )
    with pytest.raises(PanglossSearchError, match="no field"):
        check_match(
            Note,
            Match(where={"when": {"type": "Exact", "where": {"month": {"eq": 1}}}}),
        )
    with pytest.raises(PanglossSearchError):
        check_match(Note, Match(where={"when": {"type": "Note"}}))


def test_what_to_order_by_is_checked():
    from pangloss_models.model_bases.embedded import Embedded
    from pangloss_models.search import OrderBy, check_order

    class When(Embedded):
        _meta = Embedded.Meta(abstract=True)
        sort_day: int | None = None
        note: str = ""

    class Exact(When):
        year: int

    class Someone(Entity):
        pass

    class Note(Document):
        when: When
        pages: int | None = None
        tags: list[str]
        sender: Someone

    initialise()
    ordered = check_order(
        Note,
        [
            OrderBy(field="when.sort_day", direction="desc"),
            OrderBy(field="label"),
            OrderBy(field="pages"),
        ],
    )
    assert [(o.path, o.field, o.descending) for o in ordered] == [
        (("when",), "sort_day", True),
        ((), "label", False),
        ((), "pages", False),
    ]
    assert ordered[1].kind == "text"
    for bad in (
        "tags",
        "sender",
        "nonsense",
        "when",
        "when.nonsense",
        "pages.sort_day",
        "when.sort_day.x",
    ):
        with pytest.raises(PanglossSearchError):
            check_order(Note, [OrderBy(field=bad)])
    with pytest.raises(ValueError):
        Match(order_by=[{"field": "label"}] * 4)


def test_published_and_review_status_are_searched_for_a_head_document():
    Person, Letter = models()
    published, status = check(
        Letter,
        published={"eq": False},
        review_status={"in": ["unchecked", "errors_found"]},
    )
    assert (published.field, published.kind, published.operator, published.value) == (
        "published",
        "simple",
        "eq",
        False,
    )
    assert (status.kind, status.value) == ("text", ["unchecked", "errors_found"])

    # (not for an entity, and not for what a relation points at: they have no such property)
    with pytest.raises(PanglossSearchError, match="published"):
        check_match(
            Person, Match.model_validate({"where": {"published": {"eq": True}}})
        )
    with pytest.raises(PanglossSearchError, match="published_on"):
        check(Letter, published_on={"eq": 1})
    with pytest.raises(PanglossSearchError, match="published"):
        check(Letter, published={"eq": "yes"})
