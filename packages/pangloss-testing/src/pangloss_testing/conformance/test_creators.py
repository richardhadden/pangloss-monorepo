"""Who made an item: `meta.created_by` is a list (one person, or several, and perhaps a toolchain at a version and on
a date), and an admin may write in the name of others (`pangloss_models.creators`)"""

import datetime

from typing import no_type_check

import pytest
from pangloss_models import (
    Document,
    Entity,
    PanglossWriteRefused,
    ToolchainRun,
    initialise,
)
from pangloss_models.creators import writing_as, creators_asked
from pangloss_users import current_request_username, service

from .helpers import DATABASE_NAME, run

pytestmark = pytest.mark.asyncio(loop_scope="session")

RUN = ToolchainRun("extractor", version="1.2", date=datetime.date(2026, 11, 1))


async def people_and_a_toolchain(db_driver) -> None:
    for name in ("ann", "bob"):
        db_driver.execute_query(
            "MERGE (:PGUser {username: $username})",
            parameters_={"username": name},
            database=DATABASE_NAME,
        )
    await service.create_toolchain("extractor", "The extractor")


def models():
    class Person(Entity):
        _meta = Entity.Meta(create_with_id=True, create_inline=True)

    class Note(Document):
        text: str

    class Letter(Document):
        about: list[Person]
        notes: list[Note]

    initialise()
    return Person, Note, Letter


def named(creators) -> list[tuple]:
    return [(c.username, c.kind, c.version, c.date) for c in creators]


@no_type_check
async def test_one_creator_is_a_list_of_one(clear_database, db_driver):
    Person, _, Letter = models()
    made = await Letter.Create(label="L", about=[], notes=[]).save()
    assert named(made.meta.created_by) == [
        ("pangloss_default_user", "user", None, None)
    ]
    read = await Person.get((await Person.Create(label="P").save()).id)
    assert named(read.meta.created_by) == [
        ("pangloss_default_user", "user", None, None)
    ]
    assert read.meta.uploaded_by is None


@no_type_check
async def test_an_item_is_made_by_several_people_and_a_toolchain_in_the_order_given(
    clear_database, db_driver
):
    Person, _, Letter = models()
    await people_and_a_toolchain(db_driver)
    made = await Letter.Create(label="L", about=[], notes=[]).save(
        created_by=["bob", "ann"], toolchain=RUN
    )
    expected = [
        ("bob", "user", None, None),
        ("ann", "user", None, None),
        ("extractor", "toolchain", "1.2", datetime.date(2026, 11, 1)),
    ]
    assert named(made.meta.created_by) == expected
    assert made.meta.uploaded_by == "pangloss_default_user"

    read = await Letter.get(made.id)
    assert named(read.meta.created_by) == expected
    assert read.meta.uploaded_by == "pangloss_default_user"
    # (in a list, and in a search)
    listed = (await Letter.list()).results
    assert named(listed[0].meta.created_by) == expected
    found = (await Letter.search(Letter.Where())).results
    assert named(found[0].meta.created_by) == expected
    # (each creator has one edge, and the record says who wrote it)
    rows = run(
        db_driver,
        """
        MATCH (:Letter)<-[:is_creation_of]-(c:PGCreation)-[e:created_by]->(u:PGUser)
        RETURN u.username AS username, e.position AS position, c.uploaded_by AS uploaded_by
        ORDER BY position
        """,
    )
    assert [(r["username"], r["uploaded_by"]) for r in rows] == [
        ("bob", "pangloss_default_user"),
        ("ann", "pangloss_default_user"),
        ("extractor", "pangloss_default_user"),
    ]


@no_type_check
async def test_what_is_written_with_the_item_has_its_creators(
    clear_database, db_driver
):
    Person, Note, Letter = models()
    await people_and_a_toolchain(db_driver)
    made = await Letter.Create(
        label="L",
        about=[
            {
                "type": "Person",
                "label": "New",
                "id": "01a1c564-7def-70f0-bd21-410a35c82ab1",
                "create_new": True,
            }
        ],
        notes=[{"type": "Note", "label": "N", "text": "t"}],
    ).save(created_by="ann", toolchain="extractor")
    read = await Letter.get(made.id)
    # (an entity made with the document is a head node of its own, made by the same)
    person = await Person.get(read.about[0].id)
    assert [c.username for c in person.meta.created_by] == ["ann", "extractor"]
    assert [c.kind for c in person.meta.created_by] == ["user", "toolchain"]
    # (and a part of the document says so in its own `meta`)
    rows = run(db_driver, "MATCH (n:Note) RETURN n.meta AS meta")
    assert "extractor" in rows[0]["meta"]["created_by"]
    # (a part added by a later update is made by who updated it; the first keeps its creators)
    edit = (await Letter.get(made.id)).model_dump()
    token = current_request_username.set("bob")
    try:
        await Letter.Update(
            id=made.id,
            label="L",
            about=[{"type": "Person", "id": person.id}],
            notes=[
                {
                    "type": "Note",
                    "id": edit["notes"][0]["id"],
                    "label": "N",
                    "text": "t",
                },
                {"type": "Note", "label": "Later", "text": "t"},
            ],
        ).save()
    finally:
        current_request_username.reset(token)
    rows = run(db_driver, "MATCH (n:Note) RETURN n.label AS label, n.meta AS meta")
    by_label = {r["label"]: r["meta"]["created_by"] for r in rows}
    assert by_label["Later"] == "bob"
    assert "extractor" in by_label["N"] and "ann" in by_label["N"]
    assert [c.username for c in (await Letter.get(made.id)).meta.created_by] == [
        "ann",
        "extractor",
    ]


@no_type_check
async def test_the_creators_named_around_a_write_are_used(clear_database, db_driver):
    _, _, Letter = models()
    await people_and_a_toolchain(db_driver)
    with writing_as(creators_asked(["ann"])):
        made = await Letter.Create(label="L", about=[], notes=[]).save()
    assert [c.username for c in made.meta.created_by] == ["ann"]
    assert made.meta.uploaded_by == "pangloss_default_user"


@no_type_check
async def test_a_creator_must_be_a_user_of_the_kind_it_is_named_as(
    clear_database, db_driver
):
    _, _, Letter = models()
    await people_and_a_toolchain(db_driver)
    new = Letter.Create(label="L", about=[], notes=[])
    with pytest.raises(PanglossWriteRefused, match="no user 'nobody'"):
        await new.save(created_by=["nobody"])
    with pytest.raises(PanglossWriteRefused, match="toolchain"):
        await new.save(created_by=["extractor"])
    with pytest.raises(PanglossWriteRefused, match="cannot be named as a toolchain"):
        await new.save(toolchain="ann")
    with pytest.raises(ValueError, match="twice"):
        await new.save(created_by=["ann", "ann"])
    assert (await Letter.list()).count == 0


@no_type_check
async def test_a_toolchain_is_a_user_that_cannot_log_in(clear_database, db_driver):
    models()
    made = await service.create_toolchain("extractor", "The extractor")
    assert (made.kind, made.email, made.admin) == ("toolchain", None, False)
    assert await service.authenticate("extractor", "") is None
    assert [
        u.kind for u in await service.list_users() if u.username == "extractor"
    ] == ["toolchain"]
    assert {u.username: u.kind for u in await service.list_user_summaries()}[
        "extractor"
    ] == "toolchain"
    with pytest.raises(Exception, match="toolchain"):
        await service.set_password("extractor", "a long password")


@no_type_check
async def test_only_an_admin_names_the_creators_over_the_api(clear_database, db_driver):
    from pangloss_api import create_app

    from .test_api_models import PASSWORD, client_for, logged_in

    models()
    await service.create_toolchain("extractor", "The extractor")
    await service.create_user("root", "root@example.com", PASSWORD, admin=True)
    async with client_for(create_app()) as client:
        ann = await logged_in(client, "ann")
        await logged_in(client, "bob")
        root = await logged_in(client, "root")
        body = {"type": "Letter", "label": "L", "about": [], "notes": []}
        refused = await client.post(
            "/api/Letter", params={"created_by": "bob"}, json=body, headers=ann
        )
        assert refused.status_code == 403, refused.text
        unknown = await client.post(
            "/api/Letter", params={"created_by": "nobody"}, json=body, headers=root
        )
        assert unknown.status_code == 422, unknown.text
        orphan = await client.post(
            "/api/Letter", params={"toolchainVersion": "1"}, json=body, headers=root
        )
        assert orphan.status_code == 422, orphan.text

        made = await client.post(
            "/api/Letter",
            params={
                "created_by": ["ann", "bob"],
                "toolchain": "extractor",
                "toolchain_version": "1.2",
                "toolchainDate": "2026-11-01",
                "detail": "true",
            },
            json=body,
            headers=root,
        )
        assert made.status_code == 201, made.text
        meta = made.json()["meta"]
        assert meta["createdBy"] == [
            {"username": "ann", "kind": "user", "version": None, "date": None},
            {"username": "bob", "kind": "user", "version": None, "date": None},
            {
                "username": "extractor",
                "kind": "toolchain",
                "version": "1.2",
                "date": "2026-11-01",
            },
        ]
        assert meta["uploadedBy"] == "root"

        # (a toolchain is made by an admin, and listed with its kind)
        assert (
            await client.post(
                "/api/users/toolchains", json={"username": "other"}, headers=ann
            )
        ).status_code == 403
        new = await client.post(
            "/api/users/toolchains",
            json={"username": "other", "fullName": "Another"},
            headers=root,
        )
        assert new.status_code == 201, new.text
        assert new.json()["kind"] == "toolchain"
