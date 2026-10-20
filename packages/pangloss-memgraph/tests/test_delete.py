"""Deleting head documents and entities. Nothing is removed: deleted nodes are
flagged, and left out when reading."""

import datetime
from typing import no_type_check
from uuid import uuid7

import pytest
from pangloss_models import initialise
from pangloss_models.exceptions import (
    PanglossConflictError,
    PanglossEntityInUseError,
    PanglossNotDeletableError,
    PanglossNotDeletedError,
    PanglossNotFoundError,
    PanglossReferenceError,
    PanglossUserNotFoundError,
)
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.reified_relation import ReifiedRelation
from pangloss_users import current_request_username
from pydantic import AnyHttpUrl

from .helpers import count_nodes, run

pytestmark = pytest.mark.asyncio(loop_scope="session")


def node(db_driver, id) -> dict:
    return run(db_driver, "MATCH (n:PGIndexableNode {id: $id}) RETURN n", id=str(id))[
        0
    ]["n"]


def deletions(db_driver) -> list[dict]:
    return run(
        db_driver,
        """
        MATCH (u:PGUser)<-[:deleted_by]-(d:PGDeletion)-[:is_deletion_of]->(n)
        RETURN n.id AS id, u.username AS username, d.deleted_when AS deleted_when
        """,
    )


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


@no_type_check
async def test_delete_head_document(db_driver, clear_database):
    class Person(Entity):
        pass

    class Action(Document):
        carried_out_by: Person

    class Statement(Document):
        text: str
        action: Action

    initialise()

    person = await Person.Create(label="John Smith").save()
    saved = await Statement.Create(
        label="A Statement",
        text="text",
        action={
            "type": "Action",
            "label": "An Action",
            "carried_out_by": {"type": "Person", "id": person.id},
        },
    ).save()
    assert (await Statement.get(id=saved.id)) is not None

    assert await Statement.delete(saved.id) is None

    assert await Statement.get(id=saved.id) is None

    # Nothing was removed: the document is flagged, with a record of who and when
    assert node(db_driver, saved.id)["deleted"] is True
    assert count_nodes(db_driver, "Statement") == 1
    assert count_nodes(db_driver, "Action") == 1
    [deletion] = deletions(db_driver)
    assert deletion["id"] == str(saved.id)
    assert deletion["username"] == "pangloss_default_user"
    assert deletion["deleted_when"] is not None

    # Things nested in it are gone with it, and have no flag of their own
    nested_id = run(db_driver, "MATCH (a:Action) RETURN a.id AS id")[0]["id"]
    assert "deleted" not in node(db_driver, nested_id)
    assert await Action.get(id=nested_id) is None


@no_type_check
async def test_a_deleted_document_cannot_be_deleted_again_or_updated(
    db_driver, clear_database
):
    class Statement(Document):
        pass

    initialise()

    saved = await Statement.Create(label="A Statement").save()
    await Statement.delete(saved.id)

    with pytest.raises(PanglossNotFoundError):
        await Statement.delete(saved.id)
    with pytest.raises(PanglossNotFoundError):
        await Statement.Update(id=saved.id, label="Back again").save()

    assert len(deletions(db_driver)) == 1
    assert await Statement.get(id=saved.id) is None


@no_type_check
async def test_a_document_nested_in_another_cannot_be_deleted(db_driver, clear_database):
    class Action(Document):
        pass

    class Statement(Document):
        action: Action

    initialise()

    saved = await Statement.Create(
        label="A Statement", action={"type": "Action", "label": "An Action"}
    ).save()
    nested_id = run(db_driver, "MATCH (a:Action) RETURN a.id AS id")[0]["id"]

    with pytest.raises(PanglossNotDeletableError, match="nested|part of"):
        await Action.delete(nested_id)

    # Nothing changed
    assert deletions(db_driver) == []
    assert "deleted" not in node(db_driver, nested_id)
    assert (await Statement.get(id=saved.id)).action.label == "An Action"


@no_type_check
async def test_deleting_what_is_not_there_raises(db_driver, clear_database):
    class Statement(Document):
        pass

    class Order(Document):
        pass

    initialise()

    order = await Order.Create(label="An Order").save()

    with pytest.raises(PanglossNotFoundError):
        await Statement.delete(uuid7())
    # (wrong type)
    with pytest.raises(PanglossNotFoundError):
        await Statement.delete(order.id)

    assert deletions(db_driver) == []
    assert (await Order.get(id=order.id)) is not None


@no_type_check
async def test_deleting_as_an_unknown_user_raises(db_driver, clear_database):
    class Statement(Document):
        pass

    initialise()

    saved = await Statement.Create(label="A Statement").save()

    token = current_request_username.set("nobody_by_this_name")
    try:
        with pytest.raises(PanglossUserNotFoundError):
            await Statement.delete(saved.id)
    finally:
        current_request_username.reset(token)

    assert deletions(db_driver) == []
    assert (await Statement.get(id=saved.id)) is not None


@no_type_check
async def test_the_user_who_deleted_is_recorded(db_driver, clear_database):
    class Statement(Document):
        pass

    initialise()

    run(db_driver, "MERGE (:PGUser {username: 'editor'})")
    saved = await Statement.Create(label="A Statement").save()

    token = current_request_username.set("editor")
    try:
        await Statement.delete(saved.id)
    finally:
        current_request_username.reset(token)

    assert deletions(db_driver)[0]["username"] == "editor"


@no_type_check
async def test_the_id_of_a_deleted_document_cannot_be_used_again(
    db_driver, clear_database
):
    class Statement(Document):
        _meta = Document.Meta(create_with_id=True)

    initialise()

    given_id = uuid7()
    await Statement.Create(id=given_id, create_new=True, label="First").save()
    await Statement.delete(given_id)

    with pytest.raises(PanglossConflictError):
        await Statement.Create(id=given_id, create_new=True, label="Second").save()


@no_type_check
async def test_deleting_a_document_leaves_the_others(db_driver, clear_database):
    class Person(Entity):
        pass

    class Statement(Document):
        concerns_person: Person

    initialise()

    person = await Person.Create(label="John Smith").save()
    reference = {"type": "Person", "id": person.id}
    first = await Statement.Create(label="First", concerns_person=reference).save()
    second = await Statement.Create(label="Second", concerns_person=reference).save()

    await Statement.delete(first.id)

    assert (await Statement.get(id=second.id)).label == "Second"
    read_person = await Person.get(id=person.id)
    # (what has been deleted no longer refers to the entity)
    assert [s.id for s in read_person.concerns_person_reverse] == [second.id]


@no_type_check
async def test_deleted_documents_are_not_listed(db_driver, clear_database):
    class Statement(Document):
        pass

    initialise()

    kept = await Statement.Create(label="Gazetteer kept").save()
    other = await Statement.Create(label="Gazetteer other").save()
    gone = await Statement.Create(label="Gazetteer gone").save()
    await Statement.delete(gone.id)

    everything = await Statement.list()
    assert everything.count == 2
    assert {r.id for r in everything.results} == {kept.id, other.id}

    searched = await Statement.list(search_terms="Gazetteer")
    assert searched.count == 2
    assert {r.id for r in searched.results} == {kept.id, other.id}

    deep = await Statement.list(search_terms="Gazetteer", deep_search=True)
    assert deep.count == 2
    assert {r.id for r in deep.results} == {kept.id, other.id}

    # Paging counts what is left
    paged = await Statement.list(page_size=1)
    assert paged.count == 2
    assert len(paged.results) == 1


@no_type_check
async def test_documents_nested_in_a_deleted_document_are_not_listed(
    db_driver, clear_database
):
    class Action(Document):
        pass

    class Statement(Document):
        action: Action

    initialise()

    kept = await Statement.Create(
        label="Kept", action={"type": "Action", "label": "Kept action"}
    ).save()
    gone = await Statement.Create(
        label="Gone", action={"type": "Action", "label": "Gone action"}
    ).save()
    assert (await Action.list()).count == 2

    await Statement.delete(gone.id)

    actions = await Action.list()
    assert actions.count == 1
    assert [a.label for a in actions.results] == ["Kept action"]
    assert (await Action.list(search_terms="action")).count == 1
    assert (await Action.list(search_terms="action", deep_search=True)).count == 1
    assert kept.id


@no_type_check
async def test_deep_search_does_not_find_documents_through_a_deleted_entity(
    db_driver, clear_database
):
    class Person(Entity):
        pass

    class Statement(Document):
        concerns_person: Person

    initialise()

    person = await Person.Create(label="Zebulon Pike").save()
    saved = await Statement.Create(
        label="A Statement", concerns_person={"type": "Person", "id": person.id}
    ).save()
    found = await Statement.list(search_terms="Zebulon", deep_search=True)
    assert [r.id for r in found.results] == [saved.id]

    await Statement.delete(saved.id)

    found = await Statement.list(search_terms="Zebulon", deep_search=True)
    assert found.count == 0
    # (and the entity, no longer referred to, can be deleted)
    await Person.delete(person.id)
    assert (await Person.list(search_terms="Zebulon")).count == 0


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


@no_type_check
async def test_delete_an_entity_that_nothing_refers_to(db_driver, clear_database):
    class Person(Entity):
        pass

    initialise()

    kept = await Person.Create(label="Kept Person").save()
    gone = await Person.Create(label="Gone Person").save()

    await Person.delete(gone.id)

    assert await Person.get(id=gone.id) is None
    assert (await Person.get(id=kept.id)) is not None
    assert node(db_driver, gone.id)["deleted"] is True
    assert count_nodes(db_driver, "Person") == 2
    assert [d["id"] for d in deletions(db_driver)] == [str(gone.id)]

    listed = await Person.list()
    assert listed.count == 1
    assert [p.id for p in listed.results] == [kept.id]
    assert (await Person.list(search_terms="Person")).count == 1

    with pytest.raises(PanglossNotFoundError):
        await Person.delete(gone.id)
    with pytest.raises(PanglossNotFoundError):
        await Person.Update(id=gone.id, label="Back again").save()


@no_type_check
async def test_a_deleted_entity_cannot_be_referred_to(db_driver, clear_database):
    class Person(Entity):
        pass

    class Statement(Document):
        concerns_person: Person

    initialise()

    person = await Person.Create(label="John Smith").save()
    await Person.delete(person.id)

    with pytest.raises(PanglossReferenceError, match="deleted"):
        await Statement.Create(
            label="A Statement", concerns_person={"type": "Person", "id": person.id}
        ).save()
    assert count_nodes(db_driver, "Statement") == 0


@no_type_check
async def test_an_entity_that_is_referred_to_is_marked_not_deleted(
    db_driver, clear_database
):
    class Person(Entity):
        pass

    class Statement(Document):
        concerns_person: Person

    initialise()

    person = await Person.Create(label="John Smith").save()
    statement = await Statement.Create(
        label="A Statement", concerns_person={"type": "Person", "id": person.id}
    ).save()
    assert (await Person.get(id=person.id)).meta.marked_for_deletion is False

    with pytest.raises(PanglossEntityInUseError) as error:
        await Person.delete(person.id)

    assert error.value.entity_id == person.id
    assert [r["id"] for r in error.value.referenced_by] == [str(statement.id)]
    assert error.value.referenced_by[0]["type"] == "Statement"
    assert error.value.referenced_by[0]["label"] == "A Statement"
    assert "marked for deletion" in str(error.value)

    # It was not deleted, but the mark was kept, although the delete failed
    assert deletions(db_driver) == []
    assert "deleted" not in node(db_driver, person.id)
    stored = node(db_driver, person.id)
    assert stored["marked_for_deletion"] is True
    assert stored["marked_for_deletion_by"] == "pangloss_default_user"
    assert stored["marked_for_deletion_when"] is not None

    read = await Person.get(id=person.id)
    assert read is not None
    assert read.meta.marked_for_deletion is True
    assert [s.id for s in read.concerns_person_reverse] == [statement.id]
    assert (await Person.list()).count == 1

    # The document is as it was
    assert (await Statement.get(id=statement.id)).concerns_person.id == person.id

    # Trying again changes nothing
    with pytest.raises(PanglossEntityInUseError):
        await Person.delete(person.id)
    assert (await Person.get(id=person.id)).meta.marked_for_deletion is True


@no_type_check
async def test_a_marked_entity_can_be_deleted_once_nothing_refers_to_it(
    db_driver, clear_database
):
    class Person(Entity):
        pass

    class Statement(Document):
        concerns_person: list[Person]

    initialise()

    person = await Person.Create(label="John Smith").save()
    statement = await Statement.Create(
        label="A Statement", concerns_person=[{"type": "Person", "id": person.id}]
    ).save()
    with pytest.raises(PanglossEntityInUseError):
        await Person.delete(person.id)

    await Statement.Update(
        id=statement.id, label="A Statement", concerns_person=[]
    ).save()
    await Person.delete(person.id)

    assert await Person.get(id=person.id) is None
    stored = node(db_driver, person.id)
    assert stored["deleted"] is True
    # (the mark is cleared)
    assert not any(key.startswith("marked_for_deletion") for key in stored)


@no_type_check
async def test_what_has_been_deleted_does_not_keep_an_entity(db_driver, clear_database):
    class Person(Entity):
        pass

    class Statement(Document):
        concerns_person: Person

    initialise()

    person = await Person.Create(label="John Smith").save()
    statement = await Statement.Create(
        label="A Statement", concerns_person={"type": "Person", "id": person.id}
    ).save()
    with pytest.raises(PanglossEntityInUseError):
        await Person.delete(person.id)

    await Statement.delete(statement.id)
    await Person.delete(person.id)

    assert await Person.get(id=person.id) is None
    assert len(deletions(db_driver)) == 2


@no_type_check
async def test_references_through_nested_documents_embedded_objects_and_reified_relations(
    db_driver, clear_database
):
    class Identification[T](ReifiedRelation[T]):
        certainty: int

    class Person(Entity):
        pass

    class Date(Embedded):
        about: Person

    class Action(Document):
        carried_out_by: Person

    class NestedStatement(Document):
        action: Action

    class EmbeddedStatement(Document):
        date: Date

    class ReifiedStatement(Document):
        involves: Identification[Person]

    initialise()

    nested = await Person.Create(label="Via nested document").save()
    embedded = await Person.Create(label="Via embedded object").save()
    reified = await Person.Create(label="Via reified relation").save()

    await NestedStatement.Create(
        label="Nested",
        action={
            "type": "Action",
            "label": "An Action",
            "carried_out_by": {"type": "Person", "id": nested.id},
        },
    ).save()
    await EmbeddedStatement.Create(
        label="Embedded",
        date={"type": "Date", "about": {"type": "Person", "id": embedded.id}},
    ).save()
    await ReifiedStatement.Create(
        label="Reified",
        involves={
            "type": "Identification",
            "certainty": 1,
            "target": [{"type": "Person", "id": reified.id}],
        },
    ).save()

    for person in (nested, embedded, reified):
        with pytest.raises(PanglossEntityInUseError) as error:
            await Person.delete(person.id)
        assert len(error.value.referenced_by) == 1, person.label
        # (the head document that holds the reference, which is what can be deleted)
        assert error.value.referenced_by[0]["type"] in (
            "NestedStatement",
            "EmbeddedStatement",
            "ReifiedStatement",
        )
        assert (await Person.get(id=person.id)).meta.marked_for_deletion is True


@no_type_check
async def test_an_entity_referred_to_by_another_entity_is_in_use(
    db_driver, clear_database
):
    class Place(Entity):
        pass

    class Person(Entity):
        lives_in: list[Place]

    initialise()

    place = await Place.Create(label="Vienna").save()
    person = await Person.Create(
        label="John Smith", lives_in=[{"type": "Place", "id": place.id}]
    ).save()

    with pytest.raises(PanglossEntityInUseError) as error:
        await Place.delete(place.id)
    assert [r["id"] for r in error.value.referenced_by] == [str(person.id)]

    # ... until that one is deleted (it has nothing referring to it)
    await Person.delete(person.id)
    await Place.delete(place.id)
    assert await Place.get(id=place.id) is None


@no_type_check
async def test_entity_created_inline_by_a_document(db_driver, clear_database):
    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Statement(Document):
        concerns_person: Person

    initialise()

    person_id = uuid7()
    statement = await Statement.Create(
        label="A Statement",
        concerns_person={
            "type": "Person",
            "id": person_id,
            "label": "John Smith",
            "create_new": True,
        },
    ).save()

    # While the document that created it is there, it is in use...
    with pytest.raises(PanglossEntityInUseError):
        await Person.delete(person_id)

    # ... and once that is deleted, it is not
    await Statement.delete(statement.id)
    await Person.delete(person_id)
    assert await Person.get(id=person_id) is None


@no_type_check
async def test_delete_an_entity_by_url(db_driver, clear_database):
    class Person(Entity):
        _meta = Entity.Meta(create_with_id=True)

    initialise()

    url = AnyHttpUrl("http://example.com/people/john-smith")
    saved = await Person.Create(id=url, create_new=True, label="JS").save()

    with pytest.raises(PanglossNotFoundError):
        await Person.delete(AnyHttpUrl("http://example.com/nobody"))

    await Person.delete(url)
    assert await Person.get(id=saved.id) is None
    assert await Person.get(id=url) is None


@no_type_check
async def test_documents_are_not_marked_for_deletion(db_driver, clear_database):
    class Statement(Document):
        pass

    initialise()

    saved = await Statement.Create(label="A Statement").save()

    read = await Statement.get(id=saved.id)
    assert read.meta.marked_for_deletion is False
    assert datetime.datetime.now(datetime.UTC) > read.meta.created_when


@no_type_check
async def test_entity_deep_search_does_not_find_entities_through_a_deleted_document(
    db_driver, clear_database
):
    class Person(Entity):
        pass

    class Statement(Document):
        concerns_person: Person

    initialise()

    person = await Person.Create(label="John Smith").save()
    statement = await Statement.Create(
        label="Quirinal treaty", concerns_person={"type": "Person", "id": person.id}
    ).save()

    found = await Person.list(search_terms="Quirinal", deep_search=True)
    assert [p.id for p in found.results] == [person.id]

    await Statement.delete(statement.id)

    assert (await Person.list(search_terms="Quirinal", deep_search=True)).count == 0
    # (the entity itself is not deleted)
    assert (await Person.get(id=person.id)) is not None


@no_type_check
async def test_undelete_document(db_driver, clear_database):
    class Statement(Document):
        pass

    initialise()

    saved = await Statement.Create(label="A Statement").save()

    with pytest.raises(PanglossNotDeletedError):
        await Statement.undelete(saved.id)

    await Statement.delete(saved.id)
    assert await Statement.get(id=saved.id) is None

    assert await Statement.undelete(saved.id) is None
    assert await Statement.get(id=saved.id) is not None
    assert "deleted" not in node(db_driver, saved.id)
    # The history is kept
    assert len(deletions(db_driver)) == 1
    assert count_nodes(db_driver, "PGUndeletion") == 1

    # It can be deleted again
    await Statement.delete(saved.id)
    assert await Statement.get(id=saved.id) is None


@no_type_check
async def test_undelete_entity_by_id_and_url(db_driver, clear_database):
    class Person(Entity):
        _meta = Entity.Meta(create_with_id=True)

    initialise()

    url = AnyHttpUrl("https://example.com/john")
    person = await Person.Create(id=url, create_new=True, label="John Smith").save()
    await Person.delete(url)
    assert await Person.get(id=url) is None

    await Person.undelete(url)
    assert await Person.get(id=url) is not None

    await Person.delete(person.id)
    await Person.undelete(person.id)
    assert await Person.get(id=person.id) is not None


@no_type_check
async def test_undelete_missing_or_nested(db_driver, clear_database):
    class Action(Document):
        pass

    class Statement(Document):
        action: Action

    initialise()

    with pytest.raises(PanglossNotFoundError):
        await Statement.undelete(uuid7())

    saved = await Statement.Create(
        label="A Statement", action={"type": "Action", "label": "An Action"}
    ).save()
    nested_id = run(db_driver, "MATCH (a:Action) RETURN a.id AS id")[0]["id"]
    with pytest.raises(PanglossNotDeletableError):
        await Action.undelete(nested_id)

    # A nested document comes back with its head document
    await Statement.delete(saved.id)
    assert await Action.get(id=nested_id) is None
    await Statement.undelete(saved.id)
    assert await Action.get(id=nested_id) is not None
