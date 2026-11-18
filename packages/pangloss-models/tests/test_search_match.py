"""Checking a structured search pattern against the models"""

import datetime
import enum
import json
import re
from decimal import Decimal
from typing import TypedDict

import pytest
from pangloss_models import (
    Document,
    Entity,
    Match,
    PanglossSearchError,
    PanglossUnknownTypeError,
    SemanticSpace,
    Trait,
    initialise,
)
from pangloss_models.search import (
    CheckedCondition,
    SearchKey,
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


def test_a_type_that_is_never_a_document_of_its_own_says_what_holds_it():
    # (what a search finds is head documents: a `Statement`, `create_directly=False`, is only ever inside a `Factoid`,
    # and a search for one answered `count: 0` with no word of why)
    class Person(Entity):
        pass

    class Hearsay[T](SemanticSpace[T]):
        pass

    class Statement(Document):
        _meta = Document.Meta(abstract=True, create_directly=False)
        text: str

    class Letter(Statement):
        sender: Person

    class Report(Statement):
        reported: Hearsay[Statement]

    class Factoid(Document):
        statements: list[Statement]

    initialise()

    with pytest.raises(PanglossSearchError) as refused:
        resolve_search_type("Letter")
    message = str(refused.value)
    assert "A Letter is never a document of its own" in message
    assert "Factoid.statements, Report.reported" in message
    assert (
        '{"type": "Factoid", "where": {"$somewhere": [{"type": "Letter", ...}]}}'
        in message
    )
    with pytest.raises(PanglossSearchError):
        resolve_search_type("Statement")
    assert resolve_search_type("Factoid") is Factoid


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


def test_the_keys_can_be_written_with_search_key_and_dump_as_their_strings():
    Person, Poet, Place, Letter = nested_models()
    written = {
        SearchKey.ANY_OF: [{"title": {"eq": "a"}}, {"title": {"eq": "b"}}],
        SearchKey.NOT: {"title": {"eq": "c"}},
    }
    as_strings = {
        "$any_of": [{"title": {"eq": "a"}}, {"title": {"eq": "b"}}],
        "$not": {"title": {"eq": "c"}},
    }

    assert check_match(Letter, Match(where=written)) == check_match(
        Letter, Match(where=as_strings)
    )
    assert Match(where=written).model_dump(
        by_alias=True, exclude_unset=True, mode="json"
    ) == Match(where=as_strings).model_dump(
        by_alias=True, exclude_unset=True, mode="json"
    )
    assert json.dumps({SearchKey.SOMEWHERE: []}) == '{"$somewhere": []}'


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
    from pangloss_models import SemanticSpace

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
    from pangloss_models import Embedded

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
    from pangloss_models import Embedded, OrderBy
    from pangloss_models.search import check_order

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


@pytest.mark.parametrize("name", ["published", "review_status", "deleted"])
def test_a_field_cannot_be_named_as_a_property_kept_on_a_head_node(name):
    from pangloss_models import PanglossModelError

    type("Odd", (Document,), {"__annotations__": {name: bool | None}, name: None})
    with pytest.raises(PanglossModelError, match=name):
        initialise()


def test_field_kind_says_how_each_field_is_searched_or_why_it_cannot_be():
    from pangloss_models.search import Reach, field_kind

    Person, Letter = models()
    fields = Letter._meta.fields

    assert field_kind(fields["title"]) == ("text", str)
    assert field_kind(fields["pages"]) == ("number", int)
    assert field_kind(fields["sent"]) == ("temporal", datetime.date)
    assert field_kind(fields["status"]) == ("simple", Status)
    assert field_kind(fields["tags"]) == ("list", str)
    kind, reach = field_kind(fields["sender"])
    assert kind == "relation" and isinstance(reach, Reach) and Person in reach.options
    # (a reason, not an error: the `Where` classes leave the field out)
    assert field_kind(fields["notes"]) == (
        f"a field of type {Notes} cannot be searched yet"
    )


# --- the limits of a search, on both sides of each (what keeps a search of a client small) -------------------


def parsed(where):
    return Match.model_validate({"where": where})


def nested_nots(depth):
    where = {"label": {"eq": "x"}}
    for _ in range(depth):
        where = {"$not": where}
    return where


def test_patterns_nested_up_to_the_limit_and_no_further():
    from pangloss_models.search import MAX_DEPTH

    parsed(nested_nots(MAX_DEPTH))
    with pytest.raises(
        ValueError, match=f"patterns are nested more than {MAX_DEPTH} deep"
    ):
        parsed(nested_nots(MAX_DEPTH + 1))
    # (the depth counts through $all and $any_of as well)
    for key in ("$all", "$any_of"):
        where = {"label": {"eq": "x"}}
        for _ in range(MAX_DEPTH):
            where = {key: [where]}
        parsed(where)
        with pytest.raises(ValueError, match="nested more than"):
            parsed({key: [where]})


@pytest.mark.parametrize("key", ["$all", "$any_of"])
def test_a_list_of_conditions_has_one_to_the_limit(key):
    from pangloss_models.search import MAX_VALUES

    one = {"label": {"eq": "x"}}
    parsed({key: [one] * MAX_VALUES})
    for bad in [[one] * (MAX_VALUES + 1), [], one]:
        with pytest.raises(
            ValueError, match=re.escape(f"{key} needs a list of conditions")
        ):
            parsed({key: bad})


def test_lists_of_patterns_have_one_to_the_limit():
    from pangloss_models.search import MAX_VALUES

    one = {"where": {"label": {"eq": "x"}}}
    parsed({"$somewhere": [one] * MAX_VALUES})
    for bad in [[one] * (MAX_VALUES + 1), [], one]:
        with pytest.raises(ValueError, match=r"\$somewhere needs a list of patterns"):
            parsed({"$somewhere": bad})
    incoming = {"type": "Letter", "field": "sender"}
    parsed({"$incoming": [incoming] * MAX_VALUES})
    parsed({"$incoming": incoming})
    for bad in [[incoming] * (MAX_VALUES + 1), []]:
        with pytest.raises(
            ValueError, match=r"\$incoming needs a pattern, or a list of them"
        ):
            parsed({"$incoming": bad})


def test_spaces_are_a_list_of_names():
    parsed({"$spaces": ["Notebook"]})
    for bad in [[], "Notebook", ["Notebook", 1]]:
        with pytest.raises(ValueError, match=r"\$spaces needs a list of the names"):
            parsed({"$spaces": bad})


def test_fields_in_one_pattern_up_to_the_limit():
    from pangloss_models.search import MAX_CONDITIONS

    Person, Letter = models()
    too_many = {f"f{i}": {"eq": 1} for i in range(MAX_CONDITIONS + 1)}
    with pytest.raises(
        PanglossSearchError, match=f"More than {MAX_CONDITIONS} fields in one pattern"
    ):
        check(Letter, **too_many)
    # (at the limit, it is the first field that is not one that is refused)
    with pytest.raises(PanglossSearchError) as refused:
        check(Letter, **dict(list(too_many.items())[:MAX_CONDITIONS]))
    assert "More than" not in str(refused.value)


def test_conditions_in_a_whole_search_up_to_the_limit():
    from pangloss_models.search import MAX_EXPRESSIONS

    assert MAX_EXPRESSIONS == 500  # (the numbers below make 500)
    Person, Letter = models()
    # each item: its $all and four labels (5); the $all of 99 items (1 + 495); four fields more (500)
    item = {"$all": [{"label": {"eq": "x"}}] * 4}
    where = {
        "$all": [item] * 99,
        "title": {"eq": "a"},
        "pages": {"eq": 1},
        "tags": {"contains": "t"},
        "sent": {"gt": "1500-01-01"},
    }
    assert len(check(Letter, **where)) == 99 * 4 + 4
    with pytest.raises(
        PanglossSearchError,
        match=f"More than {MAX_EXPRESSIONS} conditions in one search",
    ):
        check(Letter, **where, price={"gt": 1})


@pytest.mark.parametrize(
    "combinator",
    [
        {"$all": [{"label": {"eq": "a"}}]},
        {"$any_of": [{"label": {"eq": "a"}}, {"label": {"eq": "b"}}]},
        {"$not": {"label": {"eq": "a"}}},
        # (and after the other keys of a pattern)
        {"$any": {"type": "Person"}},
        {"$mentions": {"type": "Person"}},
        {"$somewhere": [{"type": "Letter"}]},
    ],
)
def test_the_fields_after_a_combinator_are_checked_too(combinator):
    Person, Letter = models()
    checked = check(Letter, **combinator, pages={"eq": 1})
    assert CheckedCondition("pages", "number", "eq", 1) in checked
    with pytest.raises(PanglossSearchError, match="^nope"):
        check(Letter, **combinator, nope={"eq": 1})


@pytest.mark.parametrize("wrap", ["$all", "$any_of", "$not"])
def test_a_field_inside_a_combinator_is_named_as_it_is(wrap):
    Person, Letter = models()
    inner = {"nope": {"eq": 1}}
    with pytest.raises(PanglossSearchError, match="^nope"):
        check(Letter, **{wrap: inner if wrap == "$not" else [inner]})


# --- the values of the operators --------------------------------------------------------------------------------


def test_text_is_compared_in_lower_case():
    Person, Letter = models()
    assert check(Letter, title={"starts_with": "VeN"})[0].value == "ven"
    assert check(Letter, title={"contains": "VeN"})[0].value == "ven"


@pytest.mark.parametrize("value", ["", 5])
def test_contains_needs_some_text(value):
    Person, Letter = models()
    with pytest.raises(PanglossSearchError, match="^title.contains: needs some text$"):
        check(Letter, title={"contains": value})


def test_a_value_that_is_not_of_the_fields_type_is_named_where_it_is():
    from pangloss_models.search import MAX_VALUES

    Person, Letter = models()
    with pytest.raises(
        PanglossSearchError, match=r"^pages\.in: 'x' is not a valid int$"
    ):
        check(Letter, pages={"in": ["x"]})
    with pytest.raises(
        PanglossSearchError, match=r"^pages\.between: 'x' is not a valid int$"
    ):
        check(Letter, pages={"between": [1, "x"]})
    with pytest.raises(
        PanglossSearchError, match=r"^tags\.contains_any: 3 is not a valid str$"
    ):
        check(Letter, tags={"contains_any": ["a", 3]})
    with pytest.raises(
        PanglossSearchError, match=r"^pages\.in: 'in' needs at least one value$"
    ):
        check(Letter, pages={"in": []})
    with pytest.raises(
        PanglossSearchError,
        match=rf"^tags\.contains_all: 'contains_all' has more than {MAX_VALUES} values$",
    ):
        check(Letter, tags={"contains_all": ["a"] * (MAX_VALUES + 1)})
    with pytest.raises(
        PanglossSearchError,
        match=r"^sender\.is_any: 'is_any' needs at least one value$",
    ):
        check(Letter, sender={"is_any": []})


def test_the_items_of_a_list_of_decimals_are_compared_as_numbers():
    class Account(Document):
        amounts: list[Decimal]

    initialise()
    assert check(Account, amounts={"contains": "1.5"})[0].value == 1.5
    assert check(Account, amounts={"contains_any": ["1.5", "2"]})[0].value == [1.5, 2.0]


@pytest.mark.parametrize("wrap", ["$all", "$any_of"])
def test_what_a_head_document_has_can_be_asked_inside_a_combinator(wrap):
    Person, Letter = models()
    checked = check(
        Letter,
        **{wrap: [{"published": {"eq": True}}, {"review_status": {"eq": "done"}}]},
    )
    assert checked


def test_the_fields_after_incoming_are_checked_too():
    Person, Letter = models()
    checked = check(Person, **{"$incoming": [{"type": "Letter"}]}, label={"eq": "x"})
    assert CheckedCondition("label", "text", "eq", "x") in checked
    with pytest.raises(PanglossSearchError, match="^nope"):
        check(Person, **{"$incoming": [{"type": "Letter"}]}, nope={"eq": 1})


def test_an_apps_key_is_checked_by_the_app_with_where_it_is_and_the_fields_after_it_too():
    from pangloss_models.search import (
        Checked,
        Extension,
        extensions,
        register_extension,
    )

    Person, Letter = models()
    calls = []

    def flagged(model, value, top, path):
        calls.append((model, value, top, path))
        return Checked("TRUE", "flagged")

    register_extension(Extension("$flagged", flagged, kinds=("document",)))
    try:
        checked = check(Letter, **{"$flagged": True}, pages={"eq": 1})
        assert checked == [
            CheckedCondition(
                "$flagged", "extension", "match", Checked("TRUE", "flagged")
            ),
            CheckedCondition("pages", "number", "eq", 1),
        ]
        assert calls == [(Letter, True, True, "")]
        with pytest.raises(
            PanglossSearchError,
            match=r"^sender\.\$flagged: only for document patterns, not one of Person$",
        ):
            check(Letter, sender={"where": {"$flagged": True}})
        with pytest.raises(PanglossSearchError, match="^nope"):
            check(Letter, **{"$flagged": True}, nope={"eq": 1})
        with pytest.raises(
            ValueError,
            match="^The key of an extension begins with '\\$': not 'flagged'$",
        ):
            register_extension(Extension("flagged", flagged))
    finally:
        del extensions["$flagged"]


def test_a_document_inside_semantic_spaces_is_asked_for_by_their_names():
    Person, Statement, Factoid = wrapper_models()

    def spaces(names):
        got = check_match(
            Factoid,
            Match.model_validate(
                {
                    "where": {
                        "statements": {
                            "where": {"$spaces": names, "label": {"eq": "s"}}
                        }
                    }
                }
            ),
        )
        return got[0].value.items

    assert spaces(["Negative"]) == [
        CheckedCondition("$spaces", "spaces", "in", ["Negative"]),
        CheckedCondition("label", "text", "eq", "s"),
    ]
    for names, wrong in ((["Nothing"], "Nothing"), (["Negative", "Person"], "Person")):
        with pytest.raises(
            PanglossSearchError,
            match=rf"^statements\.\$spaces: '{wrong}' is not a semantic space$",
        ):
            spaces(names)


def test_conditions_given_as_objects_are_taken_as_they_are():
    from pangloss_models.search import Condition, Incoming, parse_where

    condition = Condition.model_validate({"eq": "x"})
    pattern = Condition.model_validate({"type": "Person"})
    incoming = Incoming.model_validate({"type": "Letter"})
    got = parse_where(
        {
            "label": condition,
            "$any": pattern,
            "$somewhere": [pattern],
            "$incoming": incoming,
        }
    )
    assert got["label"] is condition and got["$any"] is pattern
    assert got["$somewhere"][0] is pattern and got["$incoming"] == [incoming]
    with pytest.raises(ValueError, match="^'where' must be an object$"):
        parse_where(["label"])


def test_the_example_for_a_class_never_searched_starts_from_a_holder_that_is_a_document_of_its_own():
    class Statement(Document):
        _meta = Document.Meta(create_directly=False)

    # (first by name, and itself never a document of its own)
    class Aardvark(Document):
        _meta = Document.Meta(create_directly=False)
        reported: list[Statement]

    holders = {}
    for name in ("Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta"):
        holders[name] = type(
            name, (Document,), {"__annotations__": {"held": list[Statement]}}
        )

    class Lonely(Document):
        _meta = Document.Meta(create_directly=False)

    initialise()

    with pytest.raises(PanglossSearchError) as refused:
        resolve_search_type("Statement")
    assert str(refused.value) == (
        "A Statement is never a document of its own (create_directly is False), so a search for it finds nothing: "
        "it is inside Aardvark.reported, Alpha.held, Beta.held, Delta.held, Epsilon.held, Gamma.held, …. "
        "Search the document that holds it, with $somewhere: "
        '{"type": "Alpha", "where": {"$somewhere": [{"type": "Statement", ...}]}}'
    )
    with pytest.raises(PanglossSearchError) as refused:
        resolve_search_type("Lonely")
    assert str(refused.value) == (
        "A Lonely is never a document of its own (create_directly is False), and nothing holds one: a search "
        "for it finds nothing"
    )
