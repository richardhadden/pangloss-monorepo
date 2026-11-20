"""Shapes of relations that once failed quietly or with an error of pydantic's: a type among a field's types more than
once, a generic wrapper with a relation of its own through another wrapper, a class with no parameters below a use of a
wrapper, and the values of an edge that are no field of its edge model"""

from typing import no_type_check

import pytest
from pangloss_models import (
    Conjunction,
    Document,
    EdgeModel,
    Entity,
    ModelRegistry,
    PanglossModelError,
    ReifiedRelation,
    SemanticSpace,
    Trait,
    ViaEdge,
    initialise,
)
from pangloss_models.model_bases.labels import labels_for_model
from pangloss_models.search import edge_model_names, wrapper_labels
from pydantic import ValidationError

ID = "0194a1b2-0000-7000-8000-000000000001"


def refused(declare, saying):
    ModelRegistry._reset()
    with pytest.raises(PanglossModelError, match=saying):
        declare()
        initialise(bind_database=False)


# --- a type is among the types of a field once ---------------------------------------------------------------------


@no_type_check
def test_a_target_with_two_edge_models_is_refused_and_says_why():
    def two_edge_models():
        class Certainty(EdgeModel):
            value: int

        class Likelihood(EdgeModel):
            value: int

        class Person(Entity):
            pass

        class Doc(Document):
            who: list[ViaEdge[Person, Certainty] | ViaEdge[Person, Likelihood]]

    refused(
        two_edge_models,
        "Doc.who: Person is among the types of the field more than once, with Certainty and Likelihood: "
        "an edge of the field to a Person has one edge model",
    )

    def with_and_without():
        class Certainty(EdgeModel):
            value: int

        class Person(Entity):
            pass

        class Doc(Document):
            who: list[Person | ViaEdge[Person, Certainty]]

    refused(with_and_without, "Doc.who: Person .* with Certainty and no edge model")

    def by_a_trait():
        class Certainty(EdgeModel):
            value: int

        class Agent(Trait):
            pass

        class Person(Entity, Agent):
            pass

        class Group(Entity, Agent):
            pass

        class Doc(Document):
            who: list[ViaEdge[Person, Certainty] | Agent]

    refused(by_a_trait, "Doc.who: Person .* with Certainty and no edge model")

    def a_wrapper():
        class Certainty(EdgeModel):
            value: int

        class Person(Entity):
            pass

        class InRole[T](ReifiedRelation[T]):
            pass

        class Doc(Document):
            who: InRole[Person] | ViaEdge[InRole[Person], Certainty]

    refused(a_wrapper, "Doc.who: InRole .* with Certainty and no edge model")


@no_type_check
def test_two_uses_of_one_wrapper_in_a_field_are_refused_and_say_what_to_write():
    def two_uses():
        class Person(Entity):
            pass

        class Place(Entity):
            pass

        class InRole[T](ReifiedRelation[T]):
            pass

        class Doc(Document):
            who: list[InRole[Person] | InRole[Place]]

    refused(
        two_uses,
        r"Doc.who: InRole is among the types of the field more than once, for different types: "
        r"write the types in one use of it \(`InRole\[A \| B\]`\)",
    )


@no_type_check
def test_what_is_among_the_types_once_in_more_than_one_way_is_allowed():
    class Certainty(EdgeModel):
        value: int

    class Likelihood(EdgeModel):
        value: int

    class Agent(Trait):
        pass

    class Person(Entity, Agent):
        pass

    class Saint(Person):
        pass

    class Place(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        pass

    class Doc(Document):
        # (a class and one below it; a class and its trait; each target its own edge model)
        people: list[Person | Saint | Agent]
        both: list[ViaEdge[Person, Certainty] | ViaEdge[Saint, Certainty]]
        each: list[ViaEdge[Person, Certainty] | ViaEdge[Place, Likelihood]]
        roles: list[InRole[Person | Place]]

    initialise(bind_database=False)
    made = Doc.Create(
        label="x",
        people=[{"type": "Saint", "id": ID}],
        both=[{"type": "Saint", "id": ID, "edge_properties": {"value": 1}}],
        each=[{"type": "Place", "id": ID, "edge_properties": {"value": 1}}],
        roles=[],
    )
    assert type(made.each[0].edge_properties) is Likelihood


# --- the values of an edge -------------------------------------------------------------------------------------------


@no_type_check
def test_a_value_of_an_edge_that_is_no_field_of_its_edge_model_is_refused():
    class Certainty(EdgeModel):
        value: int
        how_sure: str | None = None

    class Person(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        pass

    class Doc(Document):
        who: list[ViaEdge[Person, Certainty]]
        roles: list[ViaEdge[InRole[ViaEdge[Person, Certainty]], Certainty]]

    initialise(bind_database=False)

    def who(**edge):
        return [{"type": "Person", "id": ID, "edge_properties": edge}]

    for model, more in ((Doc.Create, {}), (Doc.Update, {"id": ID})):
        # (by the name of the field, or in camelCase, as everywhere)
        for given in ({"value": 1, "how_sure": "x"}, {"value": 1, "howSure": "x"}):
            made = model(label="x", who=who(**given), roles=[], **more)
            assert made.who[0].edge_properties.how_sure == "x"
        with pytest.raises(ValidationError, match="Certainty has no field 'nope'"):
            model(label="x", who=who(value=1, nope=2), roles=[], **more)
        # (of the edge into a wrapper, and of the edge out of it)
        inner = {"type": "Person", "id": ID, "edge_properties": {"value": 2}}
        role = {"type": "InRole", "edge_properties": {"value": 1}, "target": [inner]}
        model(label="x", who=[], roles=[role], **more)
        with pytest.raises(ValidationError, match="Certainty has no field 'bad'"):
            model(
                label="x",
                who=[],
                roles=[{**role, "edge_properties": {"value": 1, "bad": 1}}],
                **more,
            )
        with pytest.raises(ValidationError, match="Certainty has no field 'worse'"):
            wrong = {**inner, "edge_properties": {"value": 2, "worse": 1}}
            model(label="x", who=[], roles=[{**role, "target": [wrong]}], **more)
    # (an instance of the edge model is taken as it is)
    made = Doc.Create(
        label="x",
        roles=[],
        who=[{"type": "Person", "id": ID, "edge_properties": Certainty(value=3)}],
    )
    assert made.who[0].edge_properties.value == 3


# --- wrappers --------------------------------------------------------------------------------------------------------


@no_type_check
def test_a_generic_wrapper_has_a_relation_of_its_own_through_another_wrapper():
    class RoleType(Entity):
        pass

    class Person(Entity):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Sure[T](ReifiedRelation[T]):
        how: int = 0

    class Either[A, B](Conjunction):
        one: A
        other: B

    class InOffice[T](ReifiedRelation[T]):
        office: Negative[RoleType] | None = None
        ranks: list[Sure[RoleType]]
        choice: Either[RoleType, Person] | None = None

    class Doc(Document):
        who: list[InOffice[Person]]

    initialise(bind_database=False)
    person, role = {"type": "Person", "id": ID}, {"type": "RoleType", "id": ID}
    made = Doc.Create(
        label="x",
        who=[
            {
                "type": "InOffice",
                "target": [person],
                "office": {"type": "Negative", "contents": [role]},
                "ranks": [{"type": "Sure", "how": 2, "target": [role]}],
                "choice": {"type": "Either", "one": role, "other": person},
            }
        ],
    )
    held = made.who[0]
    assert held.office.contents[0].type == "RoleType"
    assert (held.ranks[0].how, held.ranks[0].target[0].type) == (2, "RoleType")
    assert (held.choice.one.type, held.choice.other.type) == ("RoleType", "Person")
    # (what each holds is checked: a person is no role)
    with pytest.raises(ValidationError):
        Doc.Create(
            label="x",
            who=[
                {
                    "type": "InOffice",
                    "target": [person],
                    "ranks": [{"type": "Sure", "target": [person]}],
                }
            ],
        )
    # (and it may be left out where it is optional)
    Doc.Create(
        label="x",
        who=[{"type": "InOffice", "target": [person], "ranks": []}],
    )


@no_type_check
def test_a_wrapper_around_the_type_variable_of_the_class_it_is_in_is_refused():
    def around_the_parameter():
        class Person(Entity):
            pass

        class Sure[T](ReifiedRelation[T]):
            pass

        class InOffice[T](ReifiedRelation[T]):
            doubted: list[Sure[T]]

        class Doc(Document):
            who: list[InOffice[Person]]

    refused(
        around_the_parameter,
        "a wrapper around the type variable of the class it is declared in is not supported",
    )


@no_type_check
def test_a_class_with_no_parameters_below_a_use_of_a_wrapper_is_that_use():
    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        role: str | None = None

    class Finer[T](InRole[T]):
        fine: int = 0

    class JohnRole(InRole[Person]):
        extra: int = 0

    class Negative[T](SemanticSpace[T]):
        pass

    class NotAPerson(Negative[Person]):
        pass

    class Doc(Document):
        john: list[JohnRole]
        either: list[Person | InRole[Place] | JohnRole]
        never: list[NotAPerson]

    initialise(bind_database=False)
    person, place = {"type": "Person", "id": ID}, {"type": "Place", "id": ID}
    made = Doc.Create(
        label="x",
        john=[{"type": "JohnRole", "extra": 1, "role": "r", "target": [person]}],
        either=[
            person,
            {"type": "InRole", "target": [place]},
            {"type": "JohnRole", "target": [person]},
        ],
        never=[{"type": "NotAPerson", "contents": [person]}],
    )
    assert (made.john[0].type, made.john[0].extra, made.john[0].role) == (
        "JohnRole",
        1,
        "r",
    )
    assert [item.type for item in made.either] == ["Person", "InRole", "JohnRole"]
    # (it holds what the use it is below holds, and nothing else)
    with pytest.raises(ValidationError):
        Doc.Create(
            label="x",
            john=[{"type": "JohnRole", "target": [place]}],
            either=[],
            never=[],
        )
    # (its node has the label of its own class, not of the use, nor of the wrapper: as a class below the generic)
    assert labels_for_model(JohnRole, "ReifiedRelation") == [
        "JohnRole",
        "ReifiedRelation",
    ]
    assert labels_for_model(Finer, "ReifiedRelation") == ["Finer", "ReifiedRelation"]
    assert labels_for_model(NotAPerson, "SemanticSpace") == [
        "NotAPerson",
        "SemanticSpace",
    ]
    # (so a wrapper asked for by its class is looked for by the names of the classes below it too)
    assert wrapper_labels(InRole) == ["InRole", "Finer", "JohnRole"]
    assert wrapper_labels(Finer) == ["Finer"]
    assert wrapper_labels(Negative) == ["Negative", "NotAPerson"]


@no_type_check
def test_the_names_an_edge_of_an_edge_model_or_of_one_below_it_has():
    class Certainty(EdgeModel):
        value: int

    class Strong(Certainty):
        reason: str | None = None

    class Stronger(Strong):
        pass

    class Other(EdgeModel):
        value: int

    class Person(Entity):
        pass

    class Doc(Document):
        who: list[ViaEdge[Person, Stronger]]

    initialise(bind_database=False)
    assert edge_model_names(Certainty) == ["Certainty", "Strong", "Stronger"]
    assert edge_model_names(Strong) == ["Strong", "Stronger"]
    assert edge_model_names(Other) == ["Other"]
