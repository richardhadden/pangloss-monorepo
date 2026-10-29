"""A node that fulfils a class (`Fulfils`) carries that class's labels: when it is written, when
it is nested in another document, and again when it is updated"""

from typing import Annotated, no_type_check

import pytest
from pangloss_models import initialise
from pangloss_models.field_definitions import FieldSubclassing
from pangloss_models.model_bases.configs import RelationConfig
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.helpers import Fulfils

from .helpers import run

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class Dated(Document):
        who: Person
        place: Place

    class Meeting(Document, Fulfils[Dated]):
        attendee: Annotated[
            Person,
            RelationConfig(
                subclasses_parent_fields=[FieldSubclassing("who", field_on_model=Dated)]
            ),
        ]

    class Minutes(Document):
        meetings: list[Meeting]

    return Person, Place, Dated, Meeting, Minutes


def labels_of(db_driver, label: str) -> set[str]:
    rows = run(
        db_driver,
        "MATCH (n:Meeting {label: $label}) RETURN labels(n) AS labels",
        label=label,
    )
    assert len(rows) == 1
    return set(rows[0]["labels"])


@no_type_check
async def test_a_node_that_fulfils_a_class_has_its_labels(db_driver, clear_database):
    Person, Place, Dated, Meeting, Minutes = models()
    initialise()
    person = await Person.Create(label="P").save()
    place = await Place.Create(label="Pl").save()
    ref = {"type": "Person", "id": person.id}
    where = {"type": "Place", "id": place.id}

    await Meeting.Create(label="With", attendee=ref, place=where).save()
    await Meeting.Create(label="Without", attendee=ref).save()

    assert {"Meeting", "Dated", "Document"} <= labels_of(db_driver, "With")
    assert "Dated" not in labels_of(db_driver, "Without")
    # (Memgraph keeps the labels in the order they were given, so the first is the class; Neo4j keeps no order, and nothing
    # here reads one: `labels(n)[0]` is not used)
    assert labels_of(db_driver, "With")


@no_type_check
async def test_a_nested_node_has_them_too(db_driver, clear_database):
    Person, Place, Dated, Meeting, Minutes = models()
    initialise()
    person = await Person.Create(label="P").save()
    place = await Place.Create(label="Pl").save()
    ref = {"type": "Person", "id": person.id}
    where = {"type": "Place", "id": place.id}

    await Minutes.Create(
        label="M",
        meetings=[
            {"type": "Meeting", "label": "NestedWith", "attendee": ref, "place": where},
            {"type": "Meeting", "label": "NestedWithout", "attendee": ref},
        ],
    ).save()

    assert "Dated" in labels_of(db_driver, "NestedWith")
    assert "Dated" not in labels_of(db_driver, "NestedWithout")


@no_type_check
async def test_an_update_puts_the_labels_on_and_takes_them_off(
    db_driver, clear_database
):
    Person, Place, Dated, Meeting, Minutes = models()
    initialise()
    person = await Person.Create(label="P").save()
    place = await Place.Create(label="Pl").save()
    ref = {"type": "Person", "id": person.id}
    where = {"type": "Place", "id": place.id}
    meeting = await Meeting.Create(label="Meeting", attendee=ref).save()
    assert "Dated" not in labels_of(db_driver, "Meeting")

    await Meeting.Update(
        id=meeting.id, label="Meeting", attendee=ref, place=where
    ).save()
    assert {"Meeting", "Dated"} <= labels_of(db_driver, "Meeting")

    await Meeting.Update(id=meeting.id, label="Meeting", attendee=ref).save()
    assert "Dated" not in labels_of(db_driver, "Meeting")
    assert {"Meeting", "Document", "HeadNode"} <= labels_of(db_driver, "Meeting")
