"""The class part on the backend under test (implementation_docs/similarity-build-plan.md, step 2.3): a rebuild reads
every head document and entity that is not deleted nor merged into another, and a refresh the heads written, with
the labels of what they fulfil"""

from typing import Annotated, no_type_check

import pytest
from pangloss_models import (
    Document,
    Entity,
    FieldSubclassing,
    Fulfils,
    RelationConfig,
    initialise,
)
from pangloss_vectors import Changed, Item, store
from pangloss_vectors import class_part as class_part_module
from pangloss_vectors.class_part import PART
from vectors_live_support import build, drop_vector_indexes

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture
def class_part(db_driver, clear_database, parts_of_the_test):
    """The class part alone (the default profile is it, at its weight)"""
    parts_of_the_test(PART)
    drop_vector_indexes(db_driver)
    yield PART
    drop_vector_indexes(db_driver)


@no_type_check
def models():
    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class Statement(Document):
        pass

    class Birth(Statement):
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

    initialise()
    return Person, Place, Statement, Birth, Meeting


async def class_vector(of) -> list[float] | None:
    return (await store.read(str(of))).get("class")


@no_type_check
async def test_a_rebuild_gives_each_head_the_vector_of_its_class_and_none_to_what_is_deleted_or_merged_away(
    class_part,
):
    Person, Place, Statement, Birth, Meeting = models()
    kept = await Person.Create(label="Kept").save()
    absorbed = await Person.Create(label="Absorbed").save()
    statement = await Statement.Create(label="A statement").save()
    birth = await Birth.Create(label="A birth").save()
    gone = await Statement.Create(label="Gone").save()
    await Statement.delete(gone.id)
    await Person.merge(absorbed.id, into=kept.id)

    await build("class")

    assert await class_vector(kept.id) == pytest.approx(PART.vector("Person"))
    assert await class_vector(statement.id) == pytest.approx(PART.vector("Statement"))
    assert await class_vector(birth.id) == pytest.approx(PART.vector("Birth"))
    assert await class_vector(gone.id) is None
    assert await class_vector(absorbed.id) is None
    found = await store.states()
    assert found.parts["class"].count == 3
    assert found.parts["class"].signature == PART.signature()
    # (and the profile's vector of each: the class part alone, scaled by the square root of its weight)
    vector, _ = await store.read_profile(str(birth.id), "default")
    assert vector == pytest.approx([x * 0.1**0.5 for x in PART.vector("Birth")])


@no_type_check
async def test_a_rebuild_reads_the_heads_in_pages(class_part, monkeypatch):
    Person, *_ = models()
    monkeypatch.setattr(class_part_module, "PAGE", 2)
    saved = [await Person.Create(label=f"P{i}").save() for i in range(5)]
    pages = []

    async def write(rows) -> None:
        pages.append([row.of for row in rows])

    assert await PART.rebuild(write) == 5
    assert [len(page) for page in pages] == [2, 2, 1]
    assert sorted(of for page in pages for of in page) == sorted(
        str(p.id) for p in saved
    )


@no_type_check
async def test_a_refresh_after_a_save_writes_the_vector_with_what_the_head_now_fulfils(
    class_part,
):
    Person, Place, Statement, Birth, Meeting = models()
    person = await Person.Create(label="P").save()
    place = await Place.Create(label="Pl").save()
    await build("class")

    meeting = await Meeting.Create(
        label="M", attendee={"type": "Person", "id": person.id}
    ).save()
    assert await class_vector(meeting.id) is None

    async def write(rows) -> None:
        await store.set_vectors("class", rows)

    refreshed = await PART.refresh(
        Changed(written=(Item(str(meeting.id), "Meeting"),)), write
    )
    assert refreshed.written == 1
    assert await class_vector(meeting.id) == pytest.approx(PART.vector("Meeting"))

    # (it fulfils `Dated` once it holds a place: the label is on the node, and the vector follows)
    await Meeting.Update(
        id=meeting.id,
        label="M",
        attendee={"type": "Person", "id": person.id},
        place={"type": "Place", "id": place.id},
    ).save()
    await PART.refresh(Changed(written=(Item(str(meeting.id), "Meeting"),)), write)
    assert await class_vector(meeting.id) == pytest.approx(
        PART.vector("Meeting", ["Meeting", "Dated"])
    )
    assert PART.vector("Meeting", ["Dated"]) != PART.vector("Meeting")

    # (a head deleted since is not written)
    await Meeting.delete(meeting.id)
    refreshed = await PART.refresh(
        Changed(written=(Item(str(meeting.id), "Meeting"),)), write
    )
    assert refreshed.written == 0
