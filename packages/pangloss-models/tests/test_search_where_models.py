"""The `Where` that `initialise` makes for each model: the same fields, kinds and operators as `check_match` takes"""

import datetime
import types
import typing
import uuid

import kitchen_sink
import pytest
from pangloss_models import initialise
from pangloss_models.exceptions import PanglossModelError
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_registry import ModelRegistry
from pangloss_models.search import OPERATORS, Match, check_match, field_kind
from pangloss_models.search_where import (
    Choice,
    Compare,
    DocumentWhere,
    EmbeddedWhere,
    EntityWhere,
    IncomingFrom,
    Items,
    Rel,
    Text,
    Where,
    can_have_where,
)
from pydantic import BaseModel, ValidationError

SMITH = uuid.UUID("0194a1b2-0000-7000-8000-000000000001")


def operator_names(cls: type[BaseModel]) -> set[str]:
    """The operators of an operator class, by their names in the JSON"""
    return {f.serialization_alias or name for name, f in cls.model_fields.items()}


def members(annotation) -> list:
    """The classes of a union (without `None`)"""
    if typing.get_origin(annotation) in (typing.Union, types.UnionType):
        return [a for a in typing.get_args(annotation) if a is not type(None)]
    return [annotation]


KIND_OF_CLASS = {Text: {"text"}, Choice: {"simple"}, Items: {"list"}}


def kind_of_operators(cls: type) -> set[str]:
    origin = (cls.__pydantic_generic_metadata__ or {}).get("origin") or cls
    if origin is Compare:
        return {"number", "decimal", "temporal"}
    return KIND_OF_CLASS[origin]


def test_each_operator_class_has_the_operators_of_its_kinds():
    assert operator_names(Text) == OPERATORS["text"]
    for kind in ("number", "decimal", "temporal"):
        assert operator_names(Compare) == OPERATORS[kind]
    assert operator_names(Choice) == OPERATORS["simple"]
    assert operator_names(Items) == OPERATORS["list"]
    assert operator_names(Rel) == OPERATORS["relation"] | {"through", "match"}


def test_every_where_has_a_field_of_the_kind_check_match_finds_for_each_field_that_can_be_searched():
    """The guard against the `Where` classes and `check_match` drifting apart: for every model of the kitchen sink"""
    ModelRegistry._reset()
    kitchen_sink.declare()
    initialise()
    checked = 0
    for model in ModelRegistry._models:
        if not can_have_where(model):
            assert "Where" not in vars(model), model
            continue
        where = model.Where
        assert where._model is model
        base = {
            Document: DocumentWhere,
            Entity: EntityWhere,
            Embedded: EmbeddedWhere,
        }
        assert any(
            issubclass(model, kind) and issubclass(where, b) for kind, b in base.items()
        )
        for name, definition in model._meta.fields.items():
            found = field_kind(definition)
            if name == "label":
                continue
            if isinstance(found, str):
                assert name not in where.model_fields, (model, name)
                continue
            kind, reach = found
            annotation = members(where.model_fields[name].annotation)
            if kind == "relation":
                assert annotation[0] is Rel
                targets = {w._model for w in annotation[1:] if w is not Where}
                assert targets == {o for o in reach.options if can_have_where(o)}, (
                    model,
                    name,
                )
            else:
                (cls,) = annotation
                assert kind in kind_of_operators(cls), (model, name, kind, cls)
                assert (cls.__pydantic_generic_metadata__ or {}).get("args", ()) in (
                    (),
                    (reach,),
                )
            checked += 1
    assert checked > 30


def models():
    class When(Embedded):
        year: int

    class Person(Entity):
        born: int | None = None

    class Poet(Person):
        pass

    class Place(Entity):
        pass

    class Letter(Document):
        title: str
        sent: datetime.date | None = None
        tags: list[str]
        sender: Person
        copies_to: list[Person]
        when: When

    class Order(Document):
        """A document that can hold another of itself"""

        sequence: "list[Statement]"

    class Statement(Document):
        text: str
        then: "list[Order]"

    initialise()
    return Person, Poet, Place, Letter, When, Order, Statement


def test_the_examples_of_the_docs_written_as_where_are_the_same_search():
    Person, Poet, Place, Letter, When, *_ = models()

    written = Letter.Where(
        sender=Rel(is_=SMITH),
        sent=Compare(lt=datetime.date(1600, 1, 1)),
        title=Text(contains="plague"),
        copies_to=Person.Where(label=Text(contains="venice")),
        when=When.Where(year=Compare(gt=1500)),
        tags=Items(contains="a"),
        not_=Letter.Where(published=Choice(eq=False)),
    )
    as_json = {
        "sender": {"is": str(SMITH)},
        "sent": {"lt": "1600-01-01"},
        "title": {"contains": "plague"},
        "copies_to": {"type": "Person", "where": {"label": {"contains": "venice"}}},
        "when": {"type": "When", "where": {"year": {"gt": 1500}}},
        "tags": {"contains": "a"},
        "$not": {"published": {"eq": False}},
    }

    # (the same conditions; a `Where` has them in the order of the fields of its model)
    assert sorted(map(repr, check_match(Letter, Match(where=written)))) == sorted(
        map(repr, check_match(Letter, Match(where=as_json)))
    )


def test_a_relation_takes_a_where_of_what_it_points_at_and_of_its_subclasses_only():
    Person, Poet, Place, Letter, *_ = models()

    Letter.Where(sender=Poet.Where(born=Compare(lt=1600)))
    with pytest.raises(ValidationError):
        Letter.Where(sender=Place.Where())
    with pytest.raises(ValidationError):
        Letter.Where(title=Compare(gt=1))
    with pytest.raises(ValidationError):
        Letter.Where(no_such_field=Text(eq="a"))
    # (the combinators are of the same class)
    with pytest.raises(ValidationError):
        Letter.Where(any_of_=[Person.Where()])


def test_incoming_and_somewhere_take_the_where_of_other_models():
    Person, Poet, Place, Letter, *_ = models()

    found = check_match(
        Person,
        Match(
            where=Person.Where(
                incoming_=[
                    Letter.Where(title=Text(eq="a")),
                    IncomingFrom(where=Letter.Where(), field="sender"),
                ]
            )
        ),
    )
    assert [c.value.fields for c in found] == [("copies_to", "sender"), ("sender",)]
    check_match(
        Letter, Match(where=Letter.Where(somewhere_=[Letter.Where(title=Text(eq="a"))]))
    )


def test_models_that_refer_to_each_other_nest_without_limit():
    *_, Order, Statement = models()

    pattern = Statement.Where(text=Text(eq="x"))
    # (each is two patterns, of the 50 a search may have)
    for _ in range(24):
        pattern = Statement.Where(then=Order.Where(sequence=pattern))
    check_match(Statement, Match(where=pattern))


def test_a_field_with_a_name_of_the_pattern_is_an_error():
    class Gadget(Entity):
        to_json: str

    with pytest.raises(PanglossModelError, match="a name of its search pattern"):
        initialise()


def test_search_match_makes_a_match_of_a_where_a_match_or_nothing():
    from pangloss_models.search import OrderBy, search_match

    Person, Poet, Place, Letter, *_ = models()

    assert search_match(Letter) == Match(type="Letter")
    match = search_match(Letter, Letter.Where(title=Text(eq="a")))
    assert match.type == "Letter" and list(match.where) == ["title"]
    assert search_match(Letter, Match(where={})).type == "Letter"
    # (a `Where` of another class keeps its type, for `check_match` to refuse)
    assert search_match(Letter, Person.Where()).type == "Person"
    assert search_match(
        Letter, order_by=["title", OrderBy(field="sent", direction="desc")]
    ).order_by == [
        OrderBy(field="title"),
        OrderBy(field="sent", direction="desc"),
    ]
    with pytest.raises(ValueError, match="both"):
        search_match(
            Letter, Match(order_by=[OrderBy(field="title")]), order_by=["title"]
        )
    with pytest.raises(TypeError, match="Letter.Where"):
        search_match(Letter, {"title": {"eq": "a"}})


def test_or_and_and_not_are_the_combinators():
    Person, Poet, Place, Letter, *_ = models()
    a, b, c = (Letter.Where(title=Text(eq=t)) for t in "abc")

    assert (a | b).to_json() == {
        "$any_of": [{"title": {"eq": "a"}}, {"title": {"eq": "b"}}]
    }
    assert (a & b).to_json() == {
        "$all": [{"title": {"eq": "a"}}, {"title": {"eq": "b"}}]
    }
    assert (~a).to_json() == {"$not": {"title": {"eq": "a"}}}
    # (one combinator of three, not two nested; and a mixed one is kept as it is)
    assert len((a | b | c).any_of_) == 3
    assert len(((a & b) | c).any_of_) == 2
    assert ((a | b) & ~c).to_json() == {
        "$all": [
            {"$any_of": [{"title": {"eq": "a"}}, {"title": {"eq": "b"}}]},
            {"$not": {"title": {"eq": "c"}}},
        ]
    }
    # (the same search as the dict)
    check_match(Letter, Match(where=a | ~b))
    with pytest.raises(TypeError, match="can only be combined with another"):
        a | Person.Where()
