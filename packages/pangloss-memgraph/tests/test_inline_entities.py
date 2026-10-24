"""Entities written in a document (with an id or URL of their own, `create_new`).

They are entities like any other, not part of the document: it is only that they
can be made in the same payload as the document that needs them. One that exists is
used; one that does not is created exactly as `Entity.Create(...).save()` would."""

import asyncio
from typing import no_type_check
from uuid import uuid7

import pytest
from pangloss_models import initialise
from pangloss_models.exceptions import PanglossConflictError
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.semantic_space import SemanticSpace
from pydantic import AnyHttpUrl

from .helpers import count_nodes, labels_of, run

pytestmark = pytest.mark.asyncio(loop_scope="session")


def person_payload(id, label="Inline Person", **fields) -> dict:
    return {"type": "Person", "id": id, "label": label, "create_new": True, **fields}


@no_type_check
async def test_an_inline_entity_is_created_like_any_other_entity(
    db_driver, clear_database
):
    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Statement(Document):
        concerns_person: Person

    initialise()

    person_id = uuid7()
    await Statement.Create(
        label="A Statement", concerns_person=person_payload(person_id)
    ).save()

    # A head node with its own record of creation...
    assert labels_of(db_driver, person_id) == {
        "Person",
        "Entity",
        "HeadNode",
        "PGIndexableNode",
    }
    creations = run(
        db_driver,
        """
        MATCH (u:PGUser)<-[:created_by]-(c:PGCreation)-[:is_creation_of]->(p:Person)
        RETURN u.username AS username, c.created_when AS created_when
        """,
    )
    assert len(creations) == 1
    assert creations[0]["username"] == "pangloss_default_user"

    # ... and nothing to do with the statement
    node = run(db_driver, "MATCH (p:Person) RETURN p")[0]["p"]
    assert node["id"] == str(person_id)
    assert node["label"] == "Inline Person"
    for field in ("head_node_id", "head_node_type", "meta", "semantic_spaces"):
        assert field not in node, field

    # It reads as an entity that was created by itself
    read = await Person.get(id=person_id)
    assert read.meta.head_node_id == person_id
    assert read.meta.head_node_type == "Person"
    assert read.meta.created_by == "pangloss_default_user"
    assert read.meta.semantic_spaces == []
    assert [s.label for s in read.concerns_person_reverse] == ["A Statement"]


@no_type_check
async def test_an_inline_entity_can_be_updated_as_an_entity(db_driver, clear_database):
    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Statement(Document):
        concerns_person: Person

    initialise()

    person_id = uuid7()
    statement = await Statement.Create(
        label="A Statement", concerns_person=person_payload(person_id)
    ).save()

    await Person.Update(id=person_id, label="Renamed").save()

    read = await Person.get(id=person_id)
    assert read.label == "Renamed"
    assert read.meta.updated_by == "pangloss_default_user"
    # (its relation to the statement is as it was)
    assert [s.id for s in read.concerns_person_reverse] == [statement.id]


@no_type_check
async def test_an_inline_entity_has_nothing_of_the_semantic_space_it_is_written_in(
    db_driver, clear_database
):
    class Negative[T](SemanticSpace[T]):
        pass

    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Statement(Document):
        concerns_person: Person

    class Factoid(Document):
        statements: list[Negative[Statement]]

    initialise()

    person_id = uuid7()
    await Factoid.Create(
        label="A Factoid",
        statements=[
            {
                "type": "Negative",
                "contents": [
                    {
                        "type": "Statement",
                        "label": "Not so",
                        "concerns_person": person_payload(person_id),
                    }
                ],
            }
        ],
    ).save()

    node = run(db_driver, "MATCH (p:Person) RETURN p")[0]["p"]
    assert "meta" not in node
    read = await Person.get(id=person_id)
    assert read.meta.semantic_spaces == []
    assert read.meta.context_labels == []
    # (the statement that refers to it is in the space, as it should be)
    [statement] = read.concerns_person_reverse
    assert statement.meta.semantic_spaces == ["Negative"]


@no_type_check
async def test_an_inline_entity_in_a_nested_document(db_driver, clear_database):
    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Action(Document):
        carried_out_by: Person

    class Statement(Document):
        action: Action

    initialise()

    person_id = uuid7()
    await Statement.Create(
        label="A Statement",
        action={
            "type": "Action",
            "label": "An Action",
            "carried_out_by": person_payload(person_id),
        },
    ).save()

    assert "HeadNode" in labels_of(db_driver, person_id)
    read = await Person.get(id=person_id)
    assert [a.label for a in read.carried_out_by_reverse] == ["An Action"]


@no_type_check
async def test_an_inline_entity_can_have_relations_of_its_own(
    db_driver, clear_database
):
    class Place(Entity):
        pass

    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)
        lives_in: list[Place]

    class Statement(Document):
        concerns_person: Person

    initialise()

    place = await Place.Create(label="Vienna").save()
    person_id = uuid7()
    await Statement.Create(
        label="A Statement",
        concerns_person=person_payload(
            person_id, lives_in=[{"type": "Place", "id": place.id}]
        ),
    ).save()

    read = await Person.get(id=person_id)
    assert [p.id for p in read.lives_in] == [place.id]
    assert [p.id for p in (await Place.get(id=place.id)).lives_in_reverse] == [
        person_id
    ]


# ---------------------------------------------------------------------------
# Found if it exists, by its id or by its URL
# ---------------------------------------------------------------------------


@no_type_check
async def test_an_inline_entity_given_by_url_is_found_when_it_exists(
    db_driver, clear_database
):
    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Statement(Document):
        concerns_person: Person

    initialise()

    url = AnyHttpUrl("http://example.com/people/john-smith")
    first = await Statement.Create(
        label="First", concerns_person=person_payload(url, "John Smith")
    ).save()
    second = await Statement.Create(
        label="Second", concerns_person=person_payload(url, "Another label")
    ).save()

    # One entity, with the URL, however many documents give it
    people = run(db_driver, "MATCH (p:Person) RETURN p")
    assert len(people) == 1
    assert people[0]["p"]["label"] == "John Smith"
    assert run(
        db_driver, "MATCH (:Person)-[:has_url]->(u:PGUrl) RETURN u.url AS url"
    ) == [{"url": str(url)}]

    read = await Person.get(id=url)
    assert {s.id for s in read.concerns_person_reverse} == {first.id, second.id}


@no_type_check
async def test_an_inline_entity_given_by_url_that_exists_already(
    db_driver, clear_database
):
    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Statement(Document):
        concerns_person: Person

    initialise()

    url = AnyHttpUrl("http://example.com/people/john-smith")
    person = await Person.Create(id=url, create_new=True, label="John Smith").save()

    statement = await Statement.Create(
        label="A Statement", concerns_person=person_payload(url, "Not used")
    ).save()

    assert count_nodes(db_driver, "Person") == 1
    read = await Person.get(id=person.id)
    assert read.label == "John Smith"
    assert [s.id for s in read.concerns_person_reverse] == [statement.id]


@no_type_check
async def test_the_same_inline_entity_twice_in_a_document_is_one_entity(
    db_driver, clear_database
):
    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Order(Document):
        order_given_by: Person
        order_received_by: Person

    initialise()

    by_url = AnyHttpUrl("http://example.com/people/same")
    by_uuid = uuid7()
    await Order.Create(
        label="Orders by URL",
        order_given_by=person_payload(by_url),
        order_received_by=person_payload(by_url),
    ).save()
    await Order.Create(
        label="Orders by id",
        order_given_by=person_payload(by_uuid),
        order_received_by=person_payload(by_uuid),
    ).save()

    assert count_nodes(db_driver, "Person") == 2
    assert (
        run(
            db_driver,
            "MATCH (:Order)-[r:order_given_by]->(:Person) RETURN count(r) AS c",
        )[0]["c"]
        == 2
    )
    assert (
        run(
            db_driver,
            "MATCH (:Order)-[r:order_received_by]->(:Person) RETURN count(r) AS c",
        )[0]["c"]
        == 2
    )
    # (each was created once: one record of creation each)
    assert count_nodes(db_driver, "PGCreation") == 4  # 2 orders, 2 people


@no_type_check
async def test_an_inline_entity_given_by_id_that_exists_is_not_changed(
    db_driver, clear_database
):
    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Statement(Document):
        concerns_person: Person

    initialise()

    person_id = uuid7()
    await Person.Create(id=person_id, create_new=True, label="Original").save()
    await Statement.Create(
        label="A Statement", concerns_person=person_payload(person_id, "Changed")
    ).save()

    assert run(db_driver, "MATCH (p:Person) RETURN p.label AS label") == [
        {"label": "Original"}
    ]
    assert count_nodes(db_driver, "PGCreation") == 2  # the person, the statement


@no_type_check
async def test_an_inline_entity_in_an_update_is_found_or_created(
    db_driver, clear_database
):
    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Statement(Document):
        concerns_person: list[Person]

    initialise()

    url = AnyHttpUrl("http://example.com/people/john-smith")
    saved = await Statement.Create(label="A Statement", concerns_person=[]).save()

    for label in ("Updated once", "Updated twice"):
        await Statement.Update(
            id=saved.id, label=label, concerns_person=[person_payload(url)]
        ).save()

    assert count_nodes(db_driver, "Person") == 1
    assert count_nodes(db_driver, "PGCreation") == 2  # the statement, the person


# ---------------------------------------------------------------------------
# Conflicts
# ---------------------------------------------------------------------------


@no_type_check
async def test_an_inline_entity_cannot_be_the_id_of_something_that_is_not_an_entity(
    db_driver, clear_database
):
    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Note(Document):
        pass

    class Statement(Document):
        concerns_person: Person

    initialise()

    note = await Note.Create(label="A Note").save()

    with pytest.raises(PanglossConflictError, match="not an entity"):
        await Statement.Create(
            label="A Statement", concerns_person=person_payload(note.id)
        ).save()

    assert count_nodes(db_driver, "Statement") == 0
    assert count_nodes(db_driver, "Person") == 0


@no_type_check
async def test_an_inline_entity_cannot_be_a_deleted_entity(db_driver, clear_database):
    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Statement(Document):
        concerns_person: Person

    initialise()

    person_id = uuid7()
    await Person.Create(id=person_id, create_new=True, label="Gone").save()
    await Person.delete(person_id)

    with pytest.raises(PanglossConflictError, match="deleted"):
        await Statement.Create(
            label="A Statement", concerns_person=person_payload(person_id)
        ).save()
    assert count_nodes(db_driver, "Statement") == 0


@no_type_check
async def test_an_inline_entity_must_be_of_an_allowed_type_if_it_exists(
    db_driver, clear_database
):
    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Place(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Statement(Document):
        concerns_person: Person

    initialise()

    place_id = uuid7()
    await Place.Create(id=place_id, create_new=True, label="Vienna").save()

    with pytest.raises(PanglossConflictError, match="another type"):
        await Statement.Create(
            label="A Statement", concerns_person=person_payload(place_id)
        ).save()
    assert count_nodes(db_driver, "Statement") == 0


# ---------------------------------------------------------------------------
# The same URL more than once
# ---------------------------------------------------------------------------


@no_type_check
async def test_the_same_url_in_a_list_in_different_fields_and_nested_documents(
    db_driver, clear_database
):
    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Action(Document):
        carried_out_by: Person
        helped_by: list[Person]

    class Statement(Document):
        concerns: list[Person]
        also_concerns: Person
        action: Action

    initialise()

    url = AnyHttpUrl("http://example.com/people/everywhere")
    await Statement.Create(
        label="A Statement",
        # Written differently each time: the first is used
        concerns=[person_payload(url, "First"), person_payload(url, "Second")],
        also_concerns=person_payload(url, "Third"),
        action={
            "type": "Action",
            "label": "An Action",
            "carried_out_by": person_payload(url, "Fourth"),
            "helped_by": [person_payload(url, "Fifth")],
        },
    ).save()

    # One entity, with one URL node, and one record of creation
    assert run(db_driver, "MATCH (p:Person) RETURN p.label AS label") == [
        {"label": "First"}
    ]
    assert count_nodes(db_driver, "PGUrl") == 1
    assert count_nodes(db_driver, "PGCreation") == 2  # the statement, the person

    # ... related to as often as it was written
    for relation, expected in (
        ("concerns", 2),
        ("also_concerns", 1),
        ("carried_out_by", 1),
        ("helped_by", 1),
    ):
        count = run(
            db_driver,
            f"MATCH ()-[r:{relation}]->(:Person) RETURN count(r) AS c",
        )[0]["c"]
        assert count == expected, relation


@no_type_check
async def test_the_same_url_by_a_uuid_and_a_url_are_different_things(
    db_driver, clear_database
):
    """An entity written with a UUID has no URL: it is not the entity of any URL"""

    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Order(Document):
        order_given_by: Person
        order_received_by: Person

    initialise()

    await Order.Create(
        label="An Order",
        order_given_by=person_payload(uuid7()),
        order_received_by=person_payload(AnyHttpUrl("http://example.com/p")),
    ).save()

    assert count_nodes(db_driver, "Person") == 2
    assert count_nodes(db_driver, "PGUrl") == 1


@no_type_check
async def test_a_url_is_a_node_the_entity_has(db_driver, clear_database):
    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Statement(Document):
        concerns_person: Person

    initialise()

    url = AnyHttpUrl("http://example.com/people/john-smith")
    await Statement.Create(
        label="A Statement", concerns_person=person_payload(url)
    ).save()

    node = run(db_driver, "MATCH (p:Person) RETURN p")[0]["p"]
    assert "urls" not in node
    rows = run(
        db_driver,
        "MATCH (p:Person)-[:has_url]->(u:PGUrl) RETURN p.id AS id, u.url AS url",
    )
    assert rows == [{"id": node["id"], "url": str(url)}]

    # (and the entity reads, and is updated, as an entity: the URL is not part of it)
    read = await Person.get(id=url)
    assert read.id.hex == node["id"].replace("-", "")
    await Person.Update(id=read.id, label="Renamed").save()
    assert count_nodes(db_driver, "PGUrl") == 1
    assert (await Person.get(id=url)).label == "Renamed"


@no_type_check
async def test_a_url_cannot_be_the_url_of_two_entities(db_driver, clear_database):
    class Person(Entity):
        _meta = Entity.Meta(create_with_id=True)

    initialise()

    url = AnyHttpUrl("http://example.com/people/john-smith")
    await Person.Create(id=url, create_new=True, label="First").save()

    with pytest.raises(PanglossConflictError, match="already in use"):
        await Person.Create(id=url, create_new=True, label="Second").save()

    assert count_nodes(db_driver, "Person") == 1
    assert count_nodes(db_driver, "PGUrl") == 1


@no_type_check
async def test_the_url_of_a_deleted_entity_stays_taken(db_driver, clear_database):
    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Statement(Document):
        concerns_person: Person

    initialise()

    url = AnyHttpUrl("http://example.com/people/gone")
    saved = await Person.Create(id=url, create_new=True, label="Gone").save()
    await Person.delete(saved.id)

    with pytest.raises(PanglossConflictError, match="deleted"):
        await Statement.Create(
            label="A Statement", concerns_person=person_payload(url)
        ).save()
    with pytest.raises(PanglossConflictError):
        await Person.Create(id=url, create_new=True, label="Again").save()


@no_type_check
async def test_documents_written_at_the_same_time_with_the_same_new_url(
    db_driver, clear_database
):
    """Whichever of the writes creates the entity, the others find it and use it:
    the URL is one entity, and every document is written"""

    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Statement(Document):
        concerns_person: Person

    initialise()

    url = AnyHttpUrl("http://example.com/people/race")
    results = await asyncio.gather(
        *[
            Statement.Create(
                label=f"Statement {i}", concerns_person=person_payload(url)
            ).save()
            for i in range(8)
        ],
        return_exceptions=True,
    )

    assert not [r for r in results if isinstance(r, Exception)], results
    assert count_nodes(db_driver, "Person") == 1
    assert count_nodes(db_driver, "PGUrl") == 1
    assert count_nodes(db_driver, "Statement") == 8
    read = await Person.get(id=url)
    assert len(read.concerns_person_reverse) == 8


@no_type_check
async def test_documents_written_at_the_same_time_with_the_same_new_id(
    db_driver, clear_database
):
    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Statement(Document):
        concerns_person: Person

    initialise()

    person_id = uuid7()
    results = await asyncio.gather(
        *[
            Statement.Create(
                label=f"Statement {i}", concerns_person=person_payload(person_id)
            ).save()
            for i in range(8)
        ],
        return_exceptions=True,
    )

    assert not [r for r in results if isinstance(r, Exception)], results
    assert count_nodes(db_driver, "Person") == 1
    assert count_nodes(db_driver, "Statement") == 8


@no_type_check
async def test_documents_written_at_the_same_time_with_the_same_id_are_a_conflict(
    db_driver, clear_database
):
    """(Something that cannot be shared: exactly one is written)"""

    class Statement(Document):
        _meta = Document.Meta(create_with_id=True)

    initialise()

    given_id = uuid7()
    results = await asyncio.gather(
        *[
            Statement.Create(
                id=given_id, create_new=True, label=f"Statement {i}"
            ).save()
            for i in range(5)
        ],
        return_exceptions=True,
    )

    written = [r for r in results if not isinstance(r, Exception)]
    failed = [r for r in results if isinstance(r, Exception)]
    assert len(written) == 1
    assert all(isinstance(r, PanglossConflictError) for r in failed), failed
    assert count_nodes(db_driver, "Statement") == 1
