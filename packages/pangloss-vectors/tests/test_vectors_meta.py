"""`_vectors_meta` (implementation_docs/similarity-build-plan.md, step 2.2): inherited as the other slots are; a group
is a class that says `searchable=True` itself; refused on anything but a document or entity class. No database."""

from typing import no_type_check

import pytest
from pangloss_models import Document, Embedded, Entity, PanglossMetaError, initialise
from pangloss_models import ReifiedRelation
from pangloss_vectors import VectorsMeta
from pangloss_vectors.meta import groups, groups_of, included, vectors_meta


@no_type_check
def test_a_class_with_none_has_the_default_and_a_subclass_has_its_parent_s_unless_it_says():
    class Thing(Entity):
        pass

    class Person(Entity):
        _vectors_meta = VectorsMeta(searchable=True)

    class Saint(Person):
        pass

    class Ghost(Person):
        _vectors_meta = VectorsMeta(include=False)

    initialise()
    assert vectors_meta(Thing) == VectorsMeta(searchable=False, include=True)
    assert vectors_meta(Saint) == VectorsMeta(searchable=True)
    assert vectors_meta(Ghost) == VectorsMeta(searchable=False, include=False)


@no_type_check
def test_a_class_left_out_and_those_below_it_have_no_vectors():
    class Note(Document):
        _vectors_meta = VectorsMeta(include=False)

    class Margin(Note):
        pass

    class Letter(Document):
        pass

    initialise()
    assert not included("Note") and not included("Margin")
    assert included("Letter")
    # (a class that is no model's is the part's business)
    assert included("NoSuchClass")


@no_type_check
def test_a_group_is_a_class_that_says_searchable_itself_and_holds_the_classes_below_it():
    class Agent(Entity):
        pass

    class Person(Agent):
        _vectors_meta = VectorsMeta(searchable=True)

    class Saint(Person):
        pass

    class Martyr(Saint):
        _vectors_meta = VectorsMeta(searchable=True)

    class Hermit(Person):
        # (its own setting is not searchable: it is still in its parent's group)
        _vectors_meta = VectorsMeta(searchable=False)

    initialise()
    assert groups() == ["Martyr", "Person"]
    assert groups_of("Agent") == []
    assert groups_of("Person") == ["Person"]
    assert groups_of("Saint") == ["Person"]
    assert groups_of("Martyr") == ["Martyr", "Person"]
    assert groups_of("Hermit") == ["Person"]
    assert groups_of("NoSuchClass") == []


@no_type_check
def test_searchable_on_an_embedded_class_is_refused_at_initialise_by_name():
    class Dimensions(Embedded):
        _vectors_meta = VectorsMeta(searchable=True)
        width: int

    class Painting(Document):
        size: Dimensions

    with pytest.raises(PanglossMetaError, match="Dimensions: VectorsMeta"):
        initialise()


@no_type_check
def test_searchable_on_a_reified_relation_is_refused_at_initialise_by_name():
    class Person(Entity):
        pass

    class Identification[T](ReifiedRelation[T]):
        _vectors_meta = VectorsMeta(searchable=True)

    class Statement(Document):
        person: Identification[Person]

    with pytest.raises(PanglossMetaError, match="Identification: VectorsMeta"):
        initialise()


@no_type_check
def test_left_out_on_an_embedded_class_is_not_refused():
    class Dimensions(Embedded):
        _vectors_meta = VectorsMeta(include=False)
        width: int

    class Painting(Document):
        size: Dimensions

    initialise()
