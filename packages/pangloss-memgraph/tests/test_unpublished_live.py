"""A document with `published: false` is hidden from a request that may not see it (docs/review.md)"""

from typing import no_type_check

import pytest
from pangloss_models import initialise
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.search import Match
from pangloss_users import see_unpublished

from .conftest import MEMGRAPH_DATABASE

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    class Person(Entity):
        pass

    class Note(Document):
        text: str

    class Letter(Document):
        title: str
        sender: Person
        notes: list[Note]

    initialise()
    return Person, Note, Letter


def titles(found):
    return sorted(item.label for item in found.results)


@no_type_check
async def test_unpublished_documents_are_seen_only_by_those_who_may(
    clear_database, db_driver
):
    Person, Note, Letter = models()
    john = await Person.Create(label="John").save()
    jane = await Person.Create(label="Jane").save()

    async def letter(label, sender=john):
        return await Letter.Create(
            label=label,
            title=label,
            sender=Person.ReferenceSet(id=sender.id),
            notes=[Note.Create(label=f"{label} note", text="x")],
        ).save()

    shown, hidden = await letter("Shown"), await letter("Hidden", jane)
    db_driver.execute_query(
        "MATCH (n:HeadNode {id: $id}) SET n.published = false",
        parameters_={"id": str(hidden.id)},
        database=MEMGRAPH_DATABASE,
    )

    async def everything():
        return {
            "list": titles(await Letter.list()),
            "text": titles(await Letter.list(search_terms="Hidden")),
            "deep": titles(await Letter.list(search_terms="Hidden", deep_search=True)),
            "search": titles(await Letter.search(Match(where={}))),
            "notes": titles(await Note.list()),
            "by_note": titles(
                await Letter.search(
                    Match(where={"notes": {"where": {"text": {"eq": "x"}}}})
                )
            ),
            "incoming": titles(
                await Person.search(
                    Match(where={"$incoming": [{"type": "Letter", "where": {}}]})
                )
            ),
            "got": await Letter.get(id=hidden.id),
            "shown": await Letter.get(id=shown.id),
        }

    token = see_unpublished.set(True)
    try:
        seen = await everything()
        assert seen["list"] == ["Hidden", "Shown"]
        assert seen["search"] == ["Hidden", "Shown"]
        assert seen["got"] is not None
        assert seen["incoming"] == ["Jane", "John"]

        see_unpublished.set(False)
        hiding = await everything()
        assert hiding["list"] == ["Shown"]
        assert hiding["text"] == []
        assert hiding["deep"] == []
        assert hiding["search"] == ["Shown"]
        assert hiding["by_note"] == ["Shown"]
        # (Jane is the sender of a hidden letter only)
        assert hiding["incoming"] == ["John"]
        # (a note is part of its document: it is hidden with it)
        assert hiding["got"] is None
        assert hiding["shown"] is not None

        # published again: no property, or true
        db_driver.execute_query(
            "MATCH (n:HeadNode {id: $id}) SET n.published = true",
            parameters_={"id": str(hidden.id)},
            database=MEMGRAPH_DATABASE,
        )
        assert titles(await Letter.list()) == ["Hidden", "Shown"]
    finally:
        see_unpublished.reset(token)


@no_type_check
async def test_the_api_shows_them_to_users_who_are_logged_in(clear_database, db_driver):
    from pangloss_api.app import create_app

    from .test_api_models import client_for, logged_in

    class Note(Document):
        text: str

    app = create_app()
    async with client_for(app) as client:
        john = await logged_in(client)
        shown = await Note.Create(label="Shown", text="x").save()
        hidden = await Note.Create(label="Hidden", text="x").save()
        db_driver.execute_query(
            "MATCH (n:HeadNode {id: $id}) SET n.published = false",
            parameters_={"id": str(hidden.id)},
            database=MEMGRAPH_DATABASE,
        )

        def labels(response):
            return sorted(r["label"] for r in response.json()["results"])

        anonymous = await client.get("/api/Note")
        assert labels(anonymous) == ["Shown"]
        assert (await client.get(f"/api/Note/{hidden.id}")).status_code == 404
        assert (await client.get(f"/api/Note/{shown.id}")).status_code == 200

        mine = await client.get("/api/Note", headers=john)
        assert labels(mine) == ["Hidden", "Shown"]
        assert (
            await client.get(f"/api/Note/{hidden.id}", headers=john)
        ).status_code == 200

        # a token that is no good is the same as none (reading is open)
        bad = await client.get("/api/Note", headers={"Authorization": "Bearer nope"})
        assert labels(bad) == ["Shown"]
        search = await client.post(
            "/api/search", json={"type": "Note", "where": {}}, headers=john
        )
        assert search.status_code == 200


@no_type_check
async def test_an_update_keeps_published_and_the_review_state_and_ids_of_parts(
    clear_database, db_driver
):
    from uuid import uuid7

    Person, Note, Letter = models()
    john = await Person.Create(label="John").save()
    saved = await Letter.Create(
        label="L",
        title="t",
        sender=Person.ReferenceSet(id=john.id),
        notes=[Note.Create(label="n", text="a")],
    ).save()
    db_driver.execute_query(
        "MATCH (n:HeadNode {id: $id}) SET n.published = false, n.review_status = 'errors_found'",
        parameters_={"id": str(saved.id)},
        database=MEMGRAPH_DATABASE,
    )
    note = (await Letter.get(id=saved.id)).notes[0]

    await Letter.Update(
        id=saved.id,
        label="L",
        title="changed",
        sender=Person.ReferenceSet(id=john.id),
        notes=[
            Note.Update(id=note.id, label="n", text="b"),
            Note.Update(id=uuid7(), label="m", text="c"),
        ],
    ).save()

    record = db_driver.execute_query(
        "MATCH (n:HeadNode {id: $id}) RETURN n.published AS published, n.review_status AS status",
        parameters_={"id": str(saved.id)},
        database=MEMGRAPH_DATABASE,
    ).records[0]
    assert (record["published"], record["status"]) == (False, "errors_found")
    # (still hidden from those who may not see it)
    token = see_unpublished.set(False)
    try:
        assert await Letter.get(id=saved.id) is None
    finally:
        see_unpublished.reset(token)
    # a part that is sent back with its id keeps it
    parts = {n.label: n for n in (await Letter.get(id=saved.id)).notes}
    assert parts["n"].id == note.id and parts["n"].text == "b"
