import datetime
from typing import no_type_check
from uuid import uuid7

import pytest
from pangloss_models import initialise
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pydantic import ValidationError

TEST_META = {
    "created_by": "pangloss_default_user",
    "created_when": datetime.datetime(2020, 1, 1),
    "updated_by": None,
    "updated_when": None,
}


@no_type_check
def test_entity_edit_view_has_values_and_outgoing_relations_but_no_incoming():
    class Place(Entity):
        pass

    class Person(Entity):
        born: int
        nickname: str | None
        born_in: Place

    class Statement(Document):
        about: Person

    initialise()

    # The head view has the incoming relation; the edit view does not
    assert "about_reverse" in Person.HeadView.model_fields
    assert "about_reverse" not in Person.EditView.model_fields

    fields = Person.EditView.model_fields
    assert {"id", "type", "label", "meta", "born", "nickname", "born_in"} <= set(fields)

    # (the incoming relation of the place, through the person, is not there either)
    assert "born_in_reverse" in Place.HeadView.model_fields
    assert "born_in_reverse" not in Place.EditView.model_fields


@no_type_check
def test_entity_edit_view_is_built_from_data():
    class Place(Entity):
        pass

    class Person(Entity):
        born: int
        born_in: Place

    initialise()

    place_id = uuid7()
    person = Person.EditView(
        id=uuid7(),
        label="John Smith",
        meta=TEST_META,
        born=1900,
        born_in={"type": "Place", "id": place_id, "label": "Paris"},
    )
    assert person.born == 1900
    assert person.born_in.id == place_id
    assert person.born_in.label == "Paris"
    assert person.type == "Person"
    assert "EditView" in str(person)

    with pytest.raises(ValidationError):
        Person.EditView(id=uuid7(), label="John Smith", meta=TEST_META)


@no_type_check
def test_edit_view_is_not_a_head_view():
    class Person(Entity):
        pass

    initialise()

    assert Person.EditView is not Person.HeadView
    assert not issubclass(Person.EditView, Person.HeadView)
    assert not issubclass(Person.HeadView, Person.EditView)


@no_type_check
def test_edit_view_is_not_made_for_documents():
    class Statement(Document):
        pass

    initialise()

    assert not hasattr(Statement, "EditView")


@no_type_check
def test_edit_view_of_subclassed_entities():
    class Person(Entity):
        pass

    class Poet(Person):
        poems: int

    initialise()

    assert "poems" in Poet.EditView.model_fields
    assert "poems" not in Person.EditView.model_fields
