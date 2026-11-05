"""Changing the class of an entity in place: `New.Update(...).save(changing_class_from=Old)`.

The node keeps its id, its URLs and everything that refers to it; its labels and `type` become those of the new
class. It is refused if something refers to it by a relation that cannot hold the new class, and if the node is not
of the class it is said to be changed from."""

from typing import no_type_check
from uuid import uuid7

import pytest
from pangloss_models import (
    Document,
    Entity,
    PanglossClassChangeError,
    PanglossVersionConflictError,
    PanglossWriteError,
    ReifiedRelation,
    hooks,
    initialise,
)
from pydantic import AnyHttpUrl

from .helpers import labels_of, run

pytestmark = pytest.mark.asyncio(loop_scope="session")

URL = "https://example.org/texts/1"


def declare():
    class Person(Entity):
        pass

    class Text(Entity):
        _meta = Entity.Meta(abstract=True, create_with_id=True, accept_url_as_id=True)
        title: str | None = None

    class Plain(Text):
        _meta = Entity.Meta(create_with_id=True, accept_url_as_id=True)

    class Book(Text):
        _meta = Entity.Meta(create_with_id=True, accept_url_as_id=True)
        pages: int | None = None
        written_by: list[Person]

    class AtPage[T](ReifiedRelation[T]):
        page: int | None = None

    class Citation(Document):
        source: Text

    class PageCitation(Document):
        source: AtPage[Text]

    class Note(Document):
        about: Plain

    initialise()
    return Person, Text, Plain, Book, Citation, PageCitation, Note


@no_type_check
async def test_an_entity_changes_class_and_keeps_its_id_urls_and_references(
    db_driver, clear_database
):
    Person, Text, Plain, Book, Citation, PageCitation, _ = declare()
    await Plain.Create(
        id=AnyHttpUrl(URL), create_new=True, label="A text", title="A text"
    ).save()
    plain_id = (await Plain.get(AnyHttpUrl(URL))).id
    cited = await Citation.Create(
        label="Cites it", source={"type": "Plain", "id": plain_id}
    ).save()
    await PageCitation.Create(
        label="Cites a page",
        source={
            "type": "AtPage",
            "target": [{"type": "Plain", "id": plain_id}],
            "page": 3,
        },
    ).save()
    person = await Person.Create(label="An author").save()
    events = []
    hooks.after_write.append(events.append)
    try:
        edit = await Plain.get_for_edit(plain_id)
        await Book.Update(
            id=plain_id,
            label="A book",
            title="A text",
            pages=200,
            written_by=[{"type": "Person", "id": person.id}],
            urls=edit.urls,
        ).save(expected_version=edit.meta.version, changing_class_from=Plain)
    finally:
        hooks.after_write.remove(events.append)

    labels = labels_of(db_driver, plain_id)
    assert {"Book", "Text", "Entity", "HeadNode"} <= labels
    assert "Plain" not in labels
    assert await Plain.get(plain_id) is None
    book = await Book.get(AnyHttpUrl(URL))
    assert book.id == plain_id
    assert book.type == "Book"
    assert book.pages == 200
    assert book.meta.version == 2
    assert [p.id for p in book.written_by] == [person.id]
    # what referred to it still does, as the class it is now
    assert [c.id for c in book.source_reverse if c.type == "Citation"] == [cited.id]
    assert len(book.source_reverse) == 2
    citation = await Citation.get(cited.id)
    assert citation.source.type == "Book"
    # read by the parent class, it is a Book
    assert (await Text.get(plain_id)).type == "Book"
    # and the write says what it was before
    assert [e.changed_class_from for e in events] == [Plain]


@no_type_check
async def test_a_class_change_is_refused_if_a_relation_cannot_hold_the_new_class(
    db_driver, clear_database
):
    _, _, Plain, Book, _, _, Note = declare()
    plain = await Plain.Create(label="A text").save()
    await Note.Create(label="About it", about={"type": "Plain", "id": plain.id}).save()

    with pytest.raises(PanglossClassChangeError, match="Note"):
        await Book.Update(id=plain.id, label="A book", written_by=[]).save(
            changing_class_from=Plain
        )

    # nothing changed
    assert "Plain" in labels_of(db_driver, plain.id)
    assert "Book" not in labels_of(db_driver, plain.id)
    found = await Plain.get(plain.id)
    assert found.label == "A text"
    assert found.meta.version == 1


@no_type_check
async def test_a_class_change_needs_the_node_to_be_of_the_class_it_is_changed_from(
    db_driver, clear_database
):
    _, _, Plain, Book, _, _, _ = declare()
    book = await Book.Create(label="A book", written_by=[]).save()

    with pytest.raises(PanglossClassChangeError, match="is a Book, not a Plain"):
        await Book.Update(id=book.id, label="Again", written_by=[]).save(
            changing_class_from=Plain
        )
    with pytest.raises(PanglossWriteError):
        await Book.Update(id=uuid7(), label="None", written_by=[]).save(
            changing_class_from=Plain
        )


@no_type_check
async def test_a_class_change_checks_the_version(db_driver, clear_database):
    _, _, Plain, Book, _, _, _ = declare()
    plain = await Plain.Create(label="A text").save()
    await Plain.Update(id=plain.id, label="Edited").save()

    with pytest.raises(PanglossVersionConflictError):
        await Book.Update(id=plain.id, label="A book", written_by=[]).save(
            expected_version=1, changing_class_from=Plain
        )
    assert (await Plain.get(plain.id)).label == "Edited"


@no_type_check
async def test_without_a_class_change_an_update_cannot_change_the_class(
    db_driver, clear_database
):
    _, _, Plain, Book, _, _, _ = declare()
    plain = await Plain.Create(label="A text").save()
    with pytest.raises(PanglossWriteError):
        await Book.Update(id=plain.id, label="A book", written_by=[]).save()
    assert "Book" not in labels_of(db_driver, plain.id)


@no_type_check
async def test_only_an_entity_changes_class(db_driver, clear_database):
    class Old(Document):
        pass

    class New(Document):
        pass

    initialise()
    old = await Old.Create(label="A document").save()
    with pytest.raises(PanglossClassChangeError, match="entity"):
        await New.Update(id=old.id, label="Again").save(changing_class_from=Old)
    assert run(db_driver, "MATCH (n:New) RETURN count(n) AS c")[0]["c"] == 0
