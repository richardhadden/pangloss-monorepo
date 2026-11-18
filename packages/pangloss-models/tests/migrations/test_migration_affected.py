"""Which models are worth reading after a migration"""

from enum import Enum
from typing import no_type_check

from migration_support import snapshot_of
from pangloss_models.migrations import PossibleRename, data_view, diff
from pangloss_models.migrations.affected import affected_models
from pangloss_models import Document, Embedded, Entity, ReifiedRelation, Trait


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


# --- found by mutation testing ------------------------------------------------------------------------------------------


@no_type_check
def test_what_holds_an_annotated_value_a_union_of_embedded_objects_or_a_wrapped_document_is_read():
    from pangloss_models import AnnotatedValue

    def declare(certainty_type, day_type, text_type):
        def models():
            class WithCertainty[T](AnnotatedValue[T]):
                certainty: certainty_type

            class Exact(Embedded):
                day: str

            class Span(Embedded):
                days: day_type

            class Person(Entity):
                name: WithCertainty[str]

            class Event(Document):
                when: Exact | Span

            class Claim(Document):
                text: text_type

            class Proxy[T](ReifiedRelation[T]):
                pass

            class Source(Document):
                claims: list[Proxy[Claim]]

            class Unrelated(Document):
                pass

        return models

    base = declare(int, int, str)
    assert affected(base, declare(str, int, str)) == {"WithCertainty", "Person"}
    assert affected(base, declare(int, str, str)) == {"Span", "Event"}
    # (through the parameters of a wrapper; the wrapper's own fields are its type variable's, not changed)
    assert affected(base, declare(int, int, int)) == {"Claim", "Source"}
    # (several changes: what each touches)
    assert affected(base, declare(str, str, str)) == {
        "WithCertainty",
        "Person",
        "Span",
        "Event",
    }


@no_type_check
def test_the_entities_each_changed_relation_is_to_are_read_and_their_subclasses():
    def declare(single: bool):
        def models():
            class Person(Entity):
                pass

            class Poet(Person):
                pass

            class Place(Entity):
                pass

            class Group(Entity):
                pass

            if single:

                class Letter(Document):
                    sender: Person
                    sent_from: Place
                    stamp: str
                    members: list[Group]

            else:

                class Letter(Document):
                    sender: list[Person]
                    sent_from: list[Place]
                    stamp: int
                    members: list[Group]

        return models

    assert affected(declare(True), declare(False)) == {
        "Letter",
        "Person",
        "Poet",
        "Place",
    }


@no_type_check
def test_a_new_field_does_not_stop_what_comes_after_it_being_read():
    def before():
        class Person(Entity):
            name: str

        class Place(Entity):
            name: str

    def after():
        class Person(Entity):
            name: str
            born: int

        class Place(Entity):
            name: int

    assert affected(before, after) == {"Person", "Place"}


@no_type_check
def test_what_a_hand_written_step_says_it_touches_is_read_with_the_rest():
    from pangloss_models.migrations import AlterLiteralType, RunCypher, RunPython

    snapshot = data_view(snapshot_of(_three_models))
    retyped = AlterLiteralType(
        model="Place", name="name", old={"type": "str"}, new={"type": "int"}
    )
    told = RunCypher(query="MATCH (n) RETURN n", affects=["Person"])
    assert affected_models([told, retyped], snapshot) == {"Person", "Place"}
    assert affected_models([retyped, told], snapshot) == {"Person", "Place"}
    # (one that does not say: everything)
    untold = RunPython(function="app.migrations:step")
    assert affected_models([untold], snapshot) == {"Person", "Place", "Group"}


def _three_models():
    class Person(Entity):
        name: str

    class Place(Entity):
        name: str

    class Group(Entity):
        pass


def test_which_added_fields_leave_nothing_unreadable():
    from pangloss_models.migrations import AddField
    from pangloss_models.migrations.affected import adds_nothing_unreadable

    def added(kind, needs_value=False, from_narrowing=False, **definition):
        return AddField(
            model="M",
            name="f",
            field_kind=kind,
            needs_value=needs_value,
            definition={"kind": kind, **definition},
            from_narrowing=from_narrowing,
        )

    assert adds_nothing_unreadable(added("literal"))
    assert not adds_nothing_unreadable(added("literal", needs_value=True))
    assert adds_nothing_unreadable(added("relation", many=True))
    assert not adds_nothing_unreadable(added("relation", many=False))
    assert not adds_nothing_unreadable(added("embedded"))
    # (a field that narrowed it wrote it already)
    assert adds_nothing_unreadable(added("embedded", from_narrowing=True))
