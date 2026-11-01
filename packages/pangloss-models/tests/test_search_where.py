"""The classes that write a structured search pattern (`search_where`): each is the JSON it stands for"""

import datetime
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pangloss_models import initialise
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.search import Match, check_match
from pangloss_models.search_where import (
    AnyRel,
    Choice,
    Compare,
    EntityWhere,
    IncomingFrom,
    Items,
    Rel,
    Text,
    Where,
)
from pydantic import ValidationError

SMITH = uuid.UUID("0194a1b2-0000-7000-8000-000000000001")
JONES = uuid.UUID("0194a1b2-0000-7000-8000-000000000002")


def test_each_operator_class_is_the_json_of_a_condition():
    assert Text(eq="a", in_=["b"], contains="c", starts_with="d").to_json() == {
        "eq": "a",
        "in": ["b"],
        "contains": "c",
        "starts_with": "d",
    }
    assert Compare[datetime.date](
        gt=datetime.date(1500, 1, 1),
        between=(datetime.date(1500, 1, 1), datetime.date(1600, 1, 1)),
    ).to_json() == {
        "gt": datetime.date(1500, 1, 1),
        "between": [datetime.date(1500, 1, 1), datetime.date(1600, 1, 1)],
    }
    assert Compare[Decimal](lte=Decimal("1.5")).to_json() == {"lte": Decimal("1.5")}
    assert Choice[bool](eq=False, exists=True).to_json() == {
        "eq": False,
        "exists": True,
    }
    assert Items[str](contains_any=["a", "b"]).to_json() == {"contains_any": ["a", "b"]}
    # (only what is given: `eq=None` is given)
    assert Text().to_json() == {}
    assert Text(eq=None).to_json() == {"eq": None}


def test_an_operator_its_kind_does_not_take_and_a_value_of_the_wrong_type_are_refused():
    for make in (
        lambda: Text(gt="a"),
        lambda: Choice[bool](contains=True),
        lambda: Items[str](eq="a"),
        lambda: Rel(contains="a"),
        lambda: Compare[datetime.date](lt="not a date"),
        lambda: Text(exists="yes"),
    ):
        with pytest.raises(ValidationError):
            make()


def test_the_keys_of_the_json_can_be_given_as_well_as_the_python_names():
    assert Text.model_validate({"in": ["a"]}).to_json() == {"in": ["a"]}
    assert Rel.model_validate({"is": str(SMITH)}).to_json() == {"is": SMITH}


def test_a_relation_takes_ids_or_what_has_one_and_wrapper_classes_or_names():
    smith = SimpleNamespace(id=SMITH)

    class Negative:
        pass

    assert Rel(is_=smith, through=[Negative, "Uncertain"]).to_json() == {
        "is": SMITH,
        "through": ["Negative", "Uncertain"],
    }
    assert Rel(is_any=[smith, JONES]).to_json() == {"is_any": [SMITH, JONES]}
    assert AnyRel(contains="smith").to_json() == {"contains": "smith"}


def models():
    class Person(Entity):
        born: int | None = None

    class Letter(Document):
        title: str
        sender: Person
        copies_to: list[Person]

    initialise()
    return Person, Letter, Person.Where, Letter.Where


def test_a_where_is_the_where_of_the_json_and_a_where_of_another_node_is_its_pattern():
    Person, Letter, PersonWhere, LetterWhere = models()

    written = LetterWhere(
        title=Text(contains="plague"),
        sender=PersonWhere(born=Compare[int](lt=1600)),
        copies_to=Rel(through=["Negative"], match=PersonWhere(label=Text(eq="x"))),
        any_of_=[LetterWhere(title=Text(eq="a")), LetterWhere(title=Text(eq="b"))],
        not_=LetterWhere(published=Choice[bool](eq=False)),
        mentions_=AnyRel(is_=SMITH),
    )

    assert written.to_json() == {
        "title": {"contains": "plague"},
        "sender": {"type": "Person", "where": {"born": {"lt": 1600}}},
        "copies_to": {
            "through": ["Negative"],
            "type": "Person",
            "where": {"label": {"eq": "x"}},
        },
        "$any_of": [{"title": {"eq": "a"}}, {"title": {"eq": "b"}}],
        "$not": {"published": {"eq": False}},
        "$mentions": {"is": SMITH},
    }
    # (a pattern with nothing in its `where` is only its type)
    assert PersonWhere().to_pattern() == {"type": "Person"}


def test_somewhere_and_incoming_are_patterns_of_other_nodes():
    Person, Letter, PersonWhere, LetterWhere = models()

    assert PersonWhere(
        incoming_=[
            LetterWhere(title=Text(eq="a")),
            IncomingFrom(where=LetterWhere(), field="sender", through=["Negative"]),
        ]
    ).to_json() == {
        "$incoming": [
            {"type": "Letter", "where": {"title": {"eq": "a"}}},
            {"type": "Letter", "field": "sender", "through": ["Negative"]},
        ]
    }
    assert LetterWhere(somewhere_=[LetterWhere(title=Text(eq="a"))]).to_json() == {
        "$somewhere": [{"type": "Letter", "where": {"title": {"eq": "a"}}}]
    }


def test_a_where_that_is_not_of_a_model_cannot_be_a_pattern():
    with pytest.raises(TypeError, match="is not the Where of a model"):
        Where().to_pattern()


def test_check_match_takes_a_where_and_the_classes_in_a_dict_as_it_takes_the_json():
    Person, Letter, PersonWhere, LetterWhere = models()
    as_json = {
        "title": {"contains": "plague"},
        "sender": {"type": "Person", "where": {"born": {"lt": 1600}}},
        "$any_of": [{"title": {"eq": "a"}}, {"title": {"eq": "b"}}],
    }
    written = LetterWhere(
        title=Text(contains="plague"),
        sender=PersonWhere(born=Compare[int](lt=1600)),
        any_of_=[LetterWhere(title=Text(eq="a")), LetterWhere(title=Text(eq="b"))],
    )
    mixed = {
        "title": Text(contains="plague"),
        "sender": PersonWhere(born=Compare[int](lt=1600)),
        "$any_of": [LetterWhere(title=Text(eq="a")), {"title": {"eq": "b"}}],
    }

    expected = check_match(Letter, Match(where=as_json))
    assert check_match(Letter, Match(where=written)) == expected
    assert check_match(Letter, Match(where=mixed)) == expected
    # (and the JSON sent to the API is the same)
    dump = dict(by_alias=True, exclude_unset=True, mode="json")
    assert Match(where=written).model_dump(**dump) == Match(where=as_json).model_dump(
        **dump
    )


def test_an_operator_class_without_its_type_is_made_the_type_of_the_field():
    class DatedWhere(EntityWhere):
        on: Compare[datetime.date] | None = None

    # (`Compare(...)` is checked as the `Compare[datetime.date]` of the field, and is only what was given)
    assert DatedWhere(on=Compare(lt="1600-01-01")).to_json() == {
        "on": {"lt": datetime.date(1600, 1, 1)}
    }
    with pytest.raises(ValidationError):
        DatedWhere(on=Compare(lt=3))
