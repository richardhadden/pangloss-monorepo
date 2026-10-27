"""Naming the types of an autocomplete, and reducing them to the smallest set that finds the same entities"""

import pytest
from pangloss_models import initialise
from pangloss_models.autocomplete import (
    labels_to_match,
    resolve_entity_types,
    search_words,
    smallest_types,
)
from pangloss_models.exceptions import PanglossUnknownTypeError
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.trait import Trait


def models():
    class Agent(Trait):
        pass

    class Person(Entity, Agent):
        pass

    class Poet(Person):
        pass

    class Place(Entity):
        pass

    class Note(Document):
        pass

    class Marked(Trait):
        pass

    class Thing(Entity, Marked):
        pass

    class Paper(Document, Marked):
        pass

    initialise()
    return Agent, Person, Poet, Place, Note, Marked, Thing


def test_a_subclass_of_another_type_asked_for_is_dropped():
    Agent, Person, Poet, Place, *_ = models()

    assert smallest_types([Poet, Person]) == [Person]
    assert smallest_types([Person, Poet]) == [Person]
    assert smallest_types([Poet, Person, Place]) == [Person, Place]


def test_a_class_that_has_the_trait_is_dropped_when_the_trait_is_asked_for():
    Agent, Person, Poet, Place, *_ = models()

    assert smallest_types([Person, Agent, Place]) == [Agent, Place]


def test_unrelated_types_are_all_kept_in_order():
    Agent, Person, Poet, Place, *_ = models()

    assert smallest_types([Place, Person]) == [Place, Person]


def test_labels_to_match_are_the_names():
    Agent, Person, Poet, Place, *_ = models()

    assert labels_to_match([Poet, Person, Place]) == ["Person", "Place"]


def test_names_become_classes_once_each_in_order():
    Agent, Person, Poet, Place, *_ = models()

    assert resolve_entity_types(["Place", "Person", "Place"]) == [Place, Person]


def test_a_trait_that_only_entities_have_can_be_named():
    Agent, *_ = models()

    assert resolve_entity_types(["Agent"]) == [Agent]


def test_any_entity_can_be_named():
    models()

    assert resolve_entity_types(["Entity"]) == [Entity]


@pytest.mark.parametrize("name", ["Nothing", "Note", "Marked"])
def test_what_is_not_an_entity_type_is_refused_and_named(name):
    models()

    with pytest.raises(PanglossUnknownTypeError, match=name):
        resolve_entity_types(["Person", name])


def test_words_are_lower_case_and_have_no_punctuation():
    assert search_words("O'Brien (Dublin) .*") == ["o", "brien", "dublin"]
    assert search_words("  Smith,  John ") == ["smith", "john"]
    assert search_words("[a-") == ["a"]
    assert search_words("()") == []


def test_a_trait_that_extends_a_trait_is_dropped_for_the_trait_it_extends():
    class Agent(Trait):
        pass

    class Group(Agent):
        pass

    class Team(Entity, Group):
        pass

    initialise()

    assert smallest_types([Group, Agent]) == [Agent]
