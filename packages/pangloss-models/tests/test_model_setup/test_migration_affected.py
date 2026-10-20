"""Which models are worth reading after a migration"""

from typing import Annotated, no_type_check
from enum import Enum

from migration_support import snapshot_of
from pangloss_models.migrations import data_view, diff
from pangloss_models.migrations.affected import affected_models
from pangloss_models.migrations import PossibleRename
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.reified_relation import ReifiedRelation
from pangloss_models.model_bases.trait import Trait


def affected(before, after, **answers) -> set[str]:
    old, new = snapshot_of(before), snapshot_of(after)
    result = diff(old, new, **answers)
    assert result.is_final, [q.question() for q in result.questions]
    return affected_models(result.changes, data_view(new))


@no_type_check
def test_adding_models_and_optional_fields_leaves_nothing_to_read():
    def before():
        class Person(Entity):
            name: str

    def after():
        class Colour(Enum):
            RED = "red"

        class Place(Entity):
            pass

        class Person(Entity):
            name: str
            nickname: str | None
            places: list[Place]
            favourite: Colour | None

    assert affected(before, after) == set()


@no_type_check
def test_a_required_field_is_worth_reading():
    def before():
        class Person(Entity):
            name: str

        class Place(Entity):
            pass

    def after():
        class Person(Entity):
            name: str
            born: int

        class Place(Entity):
            pass

    assert affected(before, after) == {"Person"}


@no_type_check
def test_a_single_relation_that_every_node_must_have_is_worth_reading():
    def before():
        class Place(Entity):
            pass

        class Person(Entity):
            pass

    def after():
        class Place(Entity):
            pass

        class Person(Entity):
            home: Place

    # (Person has to have one; and Place is read with the people who refer to it)
    assert affected(before, after) == {"Person"}


@no_type_check
def test_the_models_that_hold_a_changed_model_are_read():
    def before():
        class Date(Embedded):
            when: str

        class Statement(Document):
            date: Date

        class Letter(Document):
            text: str

    def after():
        class Date(Embedded):
            when: int

        class Statement(Document):
            date: Date

        class Letter(Document):
            text: str

    assert affected(before, after) == {"Date", "Statement"}


@no_type_check
def test_wrapping_a_relation_reads_the_entity_it_is_to():
    def before():
        class Person(Entity):
            pass

        class Place(Entity):
            pass

        class Statement(Document):
            person: Person

    def after():
        class IdentifiedAs[T](ReifiedRelation[T]):
            certainty: int

        class Person(Entity):
            pass

        class Place(Entity):
            pass

        class Statement(Document):
            person: IdentifiedAs[Person]

    # (the person is read with the relation to it; the place is not touched)
    assert affected(before, after) == {"Statement", "Person"}


@no_type_check
def test_subclasses_are_read_with_the_class_that_changed():
    def before():
        class Statement(Document):
            text: str

        class Action(Statement):
            pass

        class Other(Document):
            pass

    def after():
        class Statement(Document):
            text: int

        class Action(Statement):
            pass

        class Other(Document):
            pass

    assert affected(before, after) == {"Statement", "Action"}


@no_type_check
def test_a_trait_added_to_a_model_is_read():
    def before():
        class Agent(Trait):
            pass

        class Person(Entity):
            pass

    def after():
        class Agent(Trait):
            pass

        class Person(Entity, Agent):
            pass

    assert affected(before, after) == {"Person"}


@no_type_check
def test_enums():
    def before():
        class Colour(Enum):
            RED = "red"
            GREEN = "green"

        class Person(Entity):
            favourite: Colour

        class Place(Entity):
            pass

    def renamed():
        class Colour(Enum):
            RED = "red"
            LIME = "green"

        class Person(Entity):
            favourite: Colour

        class Place(Entity):
            pass

    def removed():
        class Colour(Enum):
            RED = "red"

        class Person(Entity):
            favourite: Colour

        class Place(Entity):
            pass

    # a member renamed is done in place: the values follow
    rename = PossibleRename(what="enum_member", scope="Colour", old="GREEN", new="LIME")
    assert affected(before, renamed, confirmed=[rename]) == set()
    # a member that goes has its values moved
    assert affected(before, removed) == {"Person"}


@no_type_check
def test_a_renamed_model_is_worth_reading():
    def before():
        class Human(Entity):
            name: str

    def after():
        class Person(Entity):
            name: str

    rename = PossibleRename(what="model", old="Human", new="Person")
    assert affected(before, after, confirmed=[rename]) == {"Person"}
