"""A relation is read on its target under its reverse name, which may not be a name the target already has"""

from typing import Annotated, no_type_check

import pytest
from pangloss_models import Entity, PanglossModelError, RelationConfig, initialise


@no_type_check
@pytest.mark.parametrize("taken", ["name", "label", "id", "type", "meta", "urls"])
def test_a_reverse_name_that_a_field_or_the_view_has_is_refused(taken):
    class Place(Entity):
        name: str

    class Person(Entity):
        born_in: Annotated[Place, RelationConfig(reverse_name=taken)]

    with pytest.raises(PanglossModelError) as error:
        initialise(bind_database=False)

    assert "Person.born_in" in str(error.value)
    assert repr(taken) in str(error.value)
    assert error.value.at_string.option == "reverse_name"
    assert error.value.at_string.value == taken


@no_type_check
def test_a_default_reverse_name_that_is_a_field_is_refused_too():
    class Place(Entity):
        born_in_reverse: str

    class Person(Entity):
        born_in: Place

    with pytest.raises(PanglossModelError, match="born_in_reverse"):
        initialise(bind_database=False)


@no_type_check
def test_a_field_of_a_subclass_of_the_target_clashes_as_well():
    class Place(Entity):
        pass

    class Town(Place):
        people: str = "none"

    class Person(Entity):
        born_in: Annotated[Place, RelationConfig(reverse_name="people")]

    with pytest.raises(PanglossModelError, match="Town"):
        initialise(bind_database=False)


@no_type_check
def test_a_reverse_name_that_nothing_on_the_target_has_is_accepted():
    class Place(Entity):
        name: str

    class Person(Entity):
        born_in: Annotated[Place, RelationConfig(reverse_name="people")]

    class Event(Entity):
        at: Annotated[Place, RelationConfig(reverse_name="people")]

    initialise(bind_database=False)
    assert "people" in Place._meta.field_definitions.incoming_fields


@no_type_check
def test_the_same_name_on_the_source_model_is_not_a_clash():
    class Place(Entity):
        name: str

    class Person(Entity):
        born_in: Annotated[Place, RelationConfig(reverse_name="born_in_here")]
        born_in_here: str = ""

    initialise(bind_database=False)
