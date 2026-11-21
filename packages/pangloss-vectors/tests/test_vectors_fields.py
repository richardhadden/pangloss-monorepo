"""The classes a search is narrowed to (step 7a.4 of implementation_docs/similarity-build-plan.md): a field's entity
classes (`fields.field_types`: wrappers hopped over, stand-ins left out), a class's concrete classes
(`fields.classes_of`), and which of the classes asked for are searched through a group's index and which by the exact
scan (`search.narrowed`). No database."""

from typing import no_type_check

import pytest
from pangloss_models import (
    Document,
    Embedded,
    Entity,
    ReifiedRelation,
    Trait,
    hooks,
    initialise,
)
from pangloss_vectors import VectorsMeta
from pangloss_vectors.fields import NotAClass, NotAField, classes_of, field_types
from pangloss_vectors.search import Narrowed, narrowed


@pytest.fixture
def mention():
    """A stand-in of the test's own: the document `Mention` may be given in place of a `Person`"""
    stand_in = hooks.StandIn(
        document="Mention", stands_for=lambda model: model.__name__ == "Person"
    )
    hooks.stand_ins.append(stand_in)
    yield stand_in
    hooks.stand_ins.remove(stand_in)


@no_type_check
def declare():
    """Agents (a trait of `Person` and `Group`), people below them (`Saint`, an abstract `Ghost` with `Spectre`
    below it), places, wrappers, activities, and a mention that stands in for a person"""

    class Agent(Trait):
        pass

    class Person(Entity, Agent):
        _vectors_meta = VectorsMeta(searchable=True)

    class Saint(Person):
        pass

    class Ghost(Person):
        _meta = Entity.Meta(abstract=True)

    class Spectre(Ghost):
        pass

    class Group(Entity, Agent):
        _vectors_meta = VectorsMeta(searchable=True)

    class Place(Entity):
        pass

    class Building(Place):
        pass

    class Mention(Document):
        pass

    class InRole[T](ReifiedRelation[T]):
        pass

    class Identification[T](ReifiedRelation[T]):
        pass

    class Letter(Document):
        pass

    class Dimensions(Embedded):
        width: int

    class Activity(Document):
        carried_out_by: list[Agent]
        took_place_at: Place | None
        written_in: list[Person | Place]
        in_role: list[InRole[Agent]]
        identified_in_role: list[Identification[InRole[Group]]]
        ghost: list[Ghost]
        cites: list[Letter]
        note: str
        dimensions: Dimensions | None

    class Order(Document):
        given_by: list[Person]
        activities: list[Activity]

    initialise()


# ---------------------------------------------------------------------------
# A field's classes
# ---------------------------------------------------------------------------


def test_a_field_gives_the_concrete_entity_classes_it_can_hold(mention):
    declare()
    # (a plain relation: the class and those below it)
    assert field_types("Activity.took_place_at") == ["Building", "Place"]
    # (a union)
    assert field_types("Activity.written_in") == [
        "Building",
        "Person",
        "Place",
        "Saint",
        "Spectre",
    ]
    # (a trait: the classes that have it, and those below them)
    assert field_types("Activity.carried_out_by") == [
        "Group",
        "Person",
        "Saint",
        "Spectre",
    ]
    # (in JSON's spelling too)
    assert field_types("Activity.carriedOutBy") == field_types(
        "Activity.carried_out_by"
    )


def test_a_wrapper_and_a_wrapper_in_a_wrapper_are_hopped_over(mention):
    declare()
    assert field_types("Activity.in_role") == ["Group", "Person", "Saint", "Spectre"]
    assert field_types("Activity.identified_in_role") == ["Group"]


def test_a_stand_in_is_left_out_and_an_abstract_class_gives_its_concrete_ones(
    mention,
):
    declare()
    # (`Mention` may be given for a person: it is no entity, and is not searched for)
    assert field_types("Order.given_by") == ["Person", "Saint", "Spectre"]
    assert field_types("Activity.ghost") == ["Spectre"]


def test_a_field_that_is_no_model_s_no_field_of_it_or_not_a_relation_to_entities_is_refused_by_name(
    mention,
):
    declare()
    with pytest.raises(NotAField, match="'Nothing.given_by'.*no model 'Nothing'"):
        field_types("Nothing.given_by")
    with pytest.raises(
        NotAField, match="'Order.nothing'.*Order has no field 'nothing'"
    ):
        field_types("Order.nothing")
    with pytest.raises(NotAField, match="'Activity.note' is not a relation"):
        field_types("Activity.note")
    with pytest.raises(NotAField, match="'Activity.dimensions' is not a relation"):
        field_types("Activity.dimensions")
    with pytest.raises(
        NotAField, match="'Activity.cites' reaches no class of entities"
    ):
        field_types("Activity.cites")
    with pytest.raises(NotAField, match="'Order.activities' reaches no class"):
        field_types("Order.activities")
    with pytest.raises(NotAField, match="'given_by' is not a field.*Model.field"):
        field_types("given_by")


def test_a_class_gives_its_concrete_classes_and_a_name_that_is_none_is_refused(
    mention,
):
    declare()
    assert classes_of("Person") == ["Person", "Saint", "Spectre"]
    assert classes_of("Ghost") == ["Spectre"]
    assert classes_of("Agent") == ["Group", "Person", "Saint", "Spectre"]
    assert classes_of("Letter") == ["Letter"]
    for name in ("Nothing", "Dimensions", "InRole"):
        with pytest.raises(NotAClass, match=f"'{name}' is not a class of documents"):
            classes_of(name)


# ---------------------------------------------------------------------------
# Through a group's index, or by the scan
# ---------------------------------------------------------------------------


def test_classes_all_in_one_group_are_asked_through_its_index(mention):
    declare()
    assert narrowed(["Person", "Saint", "Spectre"]) == Narrowed(groups=("Person",))
    assert narrowed(["Group"]) == Narrowed(groups=("Group",))


def test_two_groups_are_each_asked_through_their_own(mention):
    declare()
    assert narrowed(["Group", "Person", "Saint", "Spectre"]) == Narrowed(
        groups=("Group", "Person")
    )


def test_a_group_and_a_class_outside_it_are_one_index_and_a_scan(mention):
    declare()
    assert narrowed(["Group", "Place", "Building"]) == Narrowed(
        groups=("Group",), scanned=("Building", "Place")
    )


def test_a_group_only_part_of_whose_classes_are_asked_for_is_scanned(mention):
    declare()
    assert narrowed(["Person", "Saint"]) == Narrowed(scanned=("Person", "Saint"))
    assert narrowed(["Saint", "Group"]) == Narrowed(
        groups=("Group",), scanned=("Saint",)
    )


@no_type_check
def test_a_group_inside_another_is_not_asked_as_well(mention):
    class Person(Entity):
        _vectors_meta = VectorsMeta(searchable=True)

    class Saint(Person):
        _vectors_meta = VectorsMeta(searchable=True)

    class Martyr(Saint):
        pass

    initialise()
    assert narrowed(["Person", "Saint", "Martyr"]) == Narrowed(groups=("Person",))
    assert narrowed(["Saint", "Martyr"]) == Narrowed(groups=("Saint",))


@no_type_check
def test_a_class_without_vectors_is_neither_asked_nor_needed_for_its_group(mention):
    class Person(Entity):
        _vectors_meta = VectorsMeta(searchable=True)

    class Ghost(Person):
        _vectors_meta = VectorsMeta(include=False)

    class Note(Document):
        _vectors_meta = VectorsMeta(include=False)

    class Letter(Document):
        pass

    initialise()
    # (a ghost's items are never hits: the group's index is enough without it)
    assert narrowed(["Person"]) == Narrowed(groups=("Person",))
    assert narrowed(["Note", "Letter"]) == Narrowed(scanned=("Letter",))
    assert narrowed(["Note"]) == Narrowed()


def test_a_name_that_is_no_class_of_documents_or_entities_is_refused(mention):
    declare()
    with pytest.raises(NotAClass, match="'Dimensions'"):
        narrowed(["Person", "Dimensions"])
