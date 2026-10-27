"""Meta slots: a setting that an optional package keeps on a model class (`pangloss_models.meta_slots`)"""

from dataclasses import dataclass

import pytest
from pangloss_models import meta_slots
from pangloss_models.exceptions import PanglossMetaError
from pangloss_models.meta_slots import declared_slots, register_meta_slot
from pangloss_models.model_bases.conjunction import Conjunction
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.edge_model import EdgeModel
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.reified_relation import ReifiedRelation
from pangloss_models.model_bases.semantic_space import SemanticSpace


@dataclass(frozen=True)
class ColourMeta:
    colour: str = "none"


@dataclass(frozen=True)
class OtherMeta:
    size: int = 0


@pytest.fixture(autouse=True)
def slots():
    before = dict(meta_slots._slots)
    yield
    meta_slots._slots.clear()
    meta_slots._slots.update(before)


def test_a_slot_set_on_a_class_is_the_object_on_the_class():
    register_meta_slot("_colour_meta", ColourMeta)
    value = ColourMeta("red")

    class Person(Entity):
        _colour_meta = value

    assert Person._colour_meta is value
    assert declared_slots(Person) == {"_colour_meta"}


def test_a_subclass_inherits_the_nearest_parents_and_may_replace_it():
    register_meta_slot("_colour_meta", ColourMeta)

    class Person(Entity):
        _colour_meta = ColourMeta("red")

    class Student(Person):
        pass

    class Postgraduate(Student):
        pass

    class Teacher(Person):
        _colour_meta = ColourMeta("blue")

    class Governor(Teacher):
        pass

    assert Student._colour_meta == ColourMeta("red")
    assert Postgraduate._colour_meta == ColourMeta("red")
    assert Teacher._colour_meta == ColourMeta("blue")
    assert Governor._colour_meta == ColourMeta("blue")
    # (only the class that says it declares it)
    assert declared_slots(Student) == frozenset()
    assert declared_slots(Postgraduate) == frozenset()
    assert declared_slots(Teacher) == {"_colour_meta"}
    assert declared_slots(Governor) == frozenset()


def test_a_class_with_no_value_anywhere_has_none():
    register_meta_slot("_colour_meta", ColourMeta)

    class Place(Entity):
        pass

    assert Place._colour_meta is None
    assert declared_slots(Place) == frozenset()


def test_a_subclass_of_an_inheriting_class_that_repeats_the_same_value_declares_it():
    register_meta_slot("_colour_meta", ColourMeta)
    value = ColourMeta("red")

    class Person(Entity):
        _colour_meta = value

    class Student(Person):
        _colour_meta = value

    assert declared_slots(Student) == {"_colour_meta"}


def test_a_value_of_the_wrong_type_is_refused_when_the_class_is_made():
    register_meta_slot("_colour_meta", ColourMeta)
    with pytest.raises(
        PanglossMetaError, match="Person._colour_meta must be a ColourMeta"
    ):

        class Person(Entity):
            _colour_meta = "red"  # type: ignore[assignment]


def test_a_slot_registered_after_models_exist_is_applied_to_them():
    class Person(Entity):
        _colour_meta = ColourMeta("red")

    class Student(Person):
        pass

    class Place(Entity):
        pass

    register_meta_slot("_colour_meta", ColourMeta)

    assert Person._colour_meta == ColourMeta("red")
    assert Student._colour_meta == ColourMeta("red")
    assert Place._colour_meta is None
    assert declared_slots(Person) == {"_colour_meta"}
    assert declared_slots(Student) == frozenset()


def test_an_unregistered_slot_is_left_alone():
    class Person(Entity):
        _colour_meta = ColourMeta("red")

    assert declared_slots(Person) == frozenset()
    assert Person.__private_attributes__["_colour_meta"].default == ColourMeta("red")


def test_two_slots_are_independent():
    register_meta_slot("_colour_meta", ColourMeta)
    register_meta_slot("_size_meta", OtherMeta)

    class Person(Entity):
        _colour_meta = ColourMeta("red")

    class Student(Person):
        _size_meta = OtherMeta(3)

    assert Student._colour_meta == ColourMeta("red")
    assert Student._size_meta == OtherMeta(3)
    assert Person._size_meta is None
    assert declared_slots(Student) == {"_size_meta"}


def test_a_generic_parametrisation_inherits_the_slot():
    from pangloss_models.model_bases.semantic_space import SemanticSpace

    register_meta_slot("_colour_meta", ColourMeta)

    class Negative[T](SemanticSpace[T]):
        _colour_meta = ColourMeta("grey")

    class Person(Entity):
        pass

    assert Negative[Person]._colour_meta == ColourMeta("grey")
    assert declared_slots(Negative[Person]) == frozenset()


@pytest.mark.parametrize("kind", [Document, Entity, Embedded, EdgeModel, Conjunction])
def test_every_kind_of_class_takes_a_slot(kind):
    register_meta_slot("_colour_meta", ColourMeta)

    class Thing(kind):  # type: ignore[valid-type, misc]
        _colour_meta = ColourMeta("red")

    class Sub(Thing):
        pass

    assert Thing._colour_meta == ColourMeta("red")
    assert Sub._colour_meta == ColourMeta("red")


def test_generic_kinds_take_a_slot():
    register_meta_slot("_colour_meta", ColourMeta)

    class Relation[T](ReifiedRelation[T]):
        _colour_meta = ColourMeta("red")

    class Space[T](SemanticSpace[T]):
        _colour_meta = ColourMeta("blue")

    assert Relation._colour_meta == ColourMeta("red")
    assert Space._colour_meta == ColourMeta("blue")


@pytest.mark.parametrize("name", ["colour", "_colour", "colour_meta", "_meta"])
def test_a_name_that_is_not_a_slot_name_is_refused(name):
    with pytest.raises(PanglossMetaError):
        register_meta_slot(name, ColourMeta)


def test_a_name_used_by_another_class_is_refused_but_repeating_it_is_not():
    register_meta_slot("_colour_meta", ColourMeta)
    register_meta_slot("_colour_meta", ColourMeta)
    with pytest.raises(PanglossMetaError, match="already used"):
        register_meta_slot("_colour_meta", OtherMeta)


def test_slots_are_kept_when_the_registry_is_reset():
    from pangloss_models.model_registry import ModelRegistry

    register_meta_slot("_colour_meta", ColourMeta)
    ModelRegistry._reset()
    assert "_colour_meta" in meta_slots.meta_slots()
