"""`SumsTo`: the items of a list relation share a total between them, by an edge property"""

from typing import Annotated, no_type_check
from uuid import uuid7

import pytest
from annotated_types import Ge, Le
from pangloss_models import (
    Conjunction,
    Document,
    EdgeModel,
    Entity,
    PanglossModelError,
    SumsTo,
    ViaEdge,
    export_models,
    initialise,
)
from pydantic import ValidationError


def person(percent: int | None) -> dict:
    return {
        "type": "Person",
        "id": uuid7(),
        "edge_properties": {} if percent is None else {"percent": percent},
    }


@no_type_check
def make_models():
    class Probability(EdgeModel):
        percent: Annotated[int, Ge(1), Le(100)]

    class Person(Entity):
        pass

    class Alternative[T](Conjunction):
        alternatives: Annotated[list[ViaEdge[T, Probability]], SumsTo("percent")]

    class Statement(Document):
        suspects: Annotated[list[ViaEdge[Person, Probability]], SumsTo("percent")]
        identified: Alternative[Person]

    initialise()
    return Statement


def statement(Statement, suspects: list, alternatives: list):
    return Statement.Create(
        label="A statement",
        suspects=suspects,
        identified={"type": "Alternative", "alternatives": alternatives},
    )


def test_shares_that_add_up_are_accepted():
    Statement = make_models()
    made = statement(Statement, [person(60), person(40)], [person(100)])
    assert [s.edge_properties.percent for s in made.suspects] == [60, 40]


def test_an_empty_list_has_nothing_to_share():
    Statement = make_models()
    statement(Statement, [], [person(100)])


@pytest.mark.parametrize(
    "suspects, alternatives, message",
    [
        ([person(60), person(30)], [person(100)], "suspects add up to 90, not 100"),
        (
            [person(100)],
            [person(50), person(60)],
            "alternatives add up to 110, not 100",
        ),
    ],
)
def test_shares_that_do_not_add_up_are_refused(suspects, alternatives, message):
    Statement = make_models()
    with pytest.raises(ValidationError, match=message):
        statement(Statement, suspects, alternatives)


def test_shares_are_checked_in_the_update_and_db_models_too():
    Statement = make_models()
    for model in (Statement.Update, Statement.CreateDB):
        with pytest.raises(ValidationError, match="add up to 90"):
            model.model_validate(
                {
                    "type": "Statement",
                    "id": uuid7(),
                    "label": "A statement",
                    "suspects": [person(90)],
                    "identified": {
                        "type": "Alternative",
                        "alternatives": [person(100)],
                    },
                }
            )


def test_the_view_is_not_checked():
    Statement = make_models()
    assert "check_shares" not in Statement.View.__pydantic_decorators__.model_validators


def test_sums_to_is_exported_with_the_validators():
    make_models()
    fields = {f["name"]: f for f in export_models()["models"]["Statement"]["fields"]}
    assert {"name": "SumsTo", "field": "percent", "total": 100} in fields["suspects"][
        "validators"
    ]
    alternative = {
        f["name"]: f for f in export_models()["models"]["Alternative"]["fields"]
    }
    assert alternative["alternatives"]["options"][0]["edgeModel"] == "Probability"


@no_type_check
def test_sums_to_on_a_literal_field_is_refused():
    class Statement(Document):
        numbers: Annotated[list[int], SumsTo("percent")]

    with pytest.raises(PanglossModelError, match="only for a list relation"):
        initialise()


@no_type_check
def test_sums_to_on_a_single_relation_is_refused():
    class Probability(EdgeModel):
        percent: int

    class Person(Entity):
        pass

    class Statement(Document):
        suspect: Annotated[ViaEdge[Person, Probability], SumsTo("percent")]

    with pytest.raises(PanglossModelError, match="only for a list relation"):
        initialise()


@no_type_check
def test_sums_to_without_an_edge_model_is_refused():
    class Person(Entity):
        pass

    class Statement(Document):
        suspects: Annotated[list[Person], SumsTo("percent")]

    with pytest.raises(PanglossModelError, match="has no edge model"):
        initialise()


@no_type_check
def test_sums_to_a_field_the_edge_model_does_not_have_as_an_int_is_refused():
    class Probability(EdgeModel):
        percent: str

    class Person(Entity):
        pass

    class Statement(Document):
        suspects: Annotated[list[ViaEdge[Person, Probability]], SumsTo("percent")]

    with pytest.raises(PanglossModelError, match="no int field 'percent'"):
        initialise()


@no_type_check
def test_sums_to_on_a_wrapper_whose_type_variable_has_no_edge_model_is_refused():
    class Alternative[T](Conjunction):
        alternatives: Annotated[list[T], SumsTo("percent")]

    with pytest.raises(PanglossModelError, match="has no edge model"):
        initialise()
