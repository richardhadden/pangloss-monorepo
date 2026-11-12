"""A companion as it is sent (implementation_docs/companion-documents.md): `companion_create` puts the new entity in the
field of each part that is for it, and refuses what the declaration does not allow, before anything is written"""

from typing import no_type_check
from uuid import uuid7

import pytest
from pangloss_models import (
    Companion,
    CompanionPart,
    Document,
    Entity,
    PanglossWriteRefused,
    ReifiedRelation,
    initialise,
)
from pangloss_models.companions import companion_create
from pydantic import ValidationError


@no_type_check
def declare():
    class Source(Entity):
        pass

    class AtPage[T](ReifiedRelation[T]):
        page: str

    class Person(Entity):
        _meta = Entity.Meta(
            companions=[
                Companion(
                    name="naming_and_gender",
                    document="Factoid",
                    field="statements",
                    parts=[
                        CompanionPart(type="Naming", entity_field="named"),
                        CompanionPart(type="Gendering", entity_field="among"),
                    ],
                ),
                Companion(name="note", document="Note", entity_field="about"),
            ]
        )

    class Naming(Document):
        named: Person
        first_name: str | None = None

    class Gendering(Document):
        among: list[Person]
        gender: str

    class Factoid(Document):
        source: AtPage[Source]
        statements: list[Naming | Gendering]

    class Note(Document):
        text: str
        about: Person

    initialise(bind_database=False)
    return Person, Factoid, Note


SOURCE = {
    "type": "AtPage",
    "page": "12",
    "target": [{"type": "Source", "id": str(uuid7())}],
}


@no_type_check
def test_the_entity_is_put_in_the_field_of_each_part_that_is_for_it():
    Person, Factoid, _ = declare()
    person_id = uuid7()

    made = companion_create(
        Person,
        person_id,
        "naming_and_gender",
        {
            "label": "Factoid",
            "source": SOURCE,
            "statements": [
                {"type": "Naming", "label": "A naming", "firstName": "John"},
                {"type": "Gendering", "label": "A gendering", "gender": "male"},
            ],
        },
    )

    assert isinstance(made, Factoid.Create)
    naming, gendering = made.statements
    assert naming.named.id == person_id and naming.named.type == "Person"
    assert naming.first_name == "John"
    # (a list relation holds the entity as its one member)
    assert [p.id for p in gendering.among] == [person_id]


@no_type_check
def test_a_companion_without_a_field_has_the_entity_in_its_own():
    Person, _, Note = declare()
    person_id = uuid7()

    made = companion_create(
        Person, person_id, "note", {"label": "N", "text": "about them"}
    )

    assert isinstance(made, Note.Create)
    assert made.about.id == person_id


@no_type_check
def test_the_entity_s_own_reference_may_be_sent_in_its_place():
    Person, _, _ = declare()
    person_id = uuid7()

    made = companion_create(
        Person,
        person_id,
        "note",
        {"label": "N", "text": "t", "about": {"type": "Person", "id": str(person_id)}},
    )
    assert made.about.id == person_id


@no_type_check
@pytest.mark.parametrize(
    "name, document, says, path",
    [
        ("naming", {}, "has no companion called 'naming'", ()),
        (
            "note",
            {"type": "Factoid", "label": "N", "text": "t"},
            "is a Note",
            ("type",),
        ),
        (
            "naming_and_gender",
            {
                "label": "F",
                "source": SOURCE,
                "statements": [{"type": "Note", "label": "x", "text": "t"}],
            },
            "not one of its parts",
            ("statements", 0, "type"),
        ),
        (
            "naming_and_gender",
            {
                "label": "F",
                "source": SOURCE,
                "statements": [
                    {"type": "Naming", "label": "a"},
                    {"type": "Naming", "label": "b"},
                ],
            },
            "given twice",
            ("statements", 1, "type"),
        ),
        (
            "naming_and_gender",
            {"label": "F", "source": SOURCE, "statements": []},
            "no parts",
            ("statements",),
        ),
        (
            "naming_and_gender",
            {
                "label": "F",
                "source": SOURCE,
                "statements": [
                    {
                        "type": "Naming",
                        "label": "a",
                        "named": {"type": "Person", "id": str(uuid7())},
                    }
                ],
            },
            "filled in by the server",
            ("statements", 0, "named"),
        ),
    ],
)
def test_what_the_declaration_does_not_allow_is_refused_at_its_place(
    name, document, says, path
):
    Person, _, _ = declare()

    with pytest.raises(PanglossWriteRefused) as error:
        companion_create(Person, uuid7(), name, document)

    assert says in str(error.value)
    assert tuple(error.value.path or ()) == path


@no_type_check
def test_a_companion_that_is_not_valid_is_a_validation_error_of_its_model():
    Person, _, _ = declare()

    with pytest.raises(ValidationError) as error:
        companion_create(
            Person,
            uuid7(),
            "naming_and_gender",
            {
                "label": "F",
                "source": SOURCE,
                "statements": [{"type": "Gendering", "label": "g"}],
            },
        )

    assert any(e["loc"][-1] == "gender" for e in error.value.errors())
