"""Unreconciled mentions (`pangloss-review`): written in a document in the place of an entity, found again by their
labels, and reconciled with an entity by an update of the document"""

import importlib
from types import SimpleNamespace
from typing import Annotated, no_type_check
from uuid import uuid4

import pytest
from pangloss_models import (
    Document,
    EdgeModel,
    Entity,
    ReifiedRelation,
    Trait,
    ViaEdge,
    initialise,
)
from pangloss_review import (
    NoUnreconciled,
    PanglossNoSuchTaskError,
    PanglossReconcileError,
    ReviewMeta,
    reconcile,
)
from pangloss_users import current_request_username
from pydantic import ValidationError

from .helpers import DATABASE_NAME, run

pytestmark = pytest.mark.asyncio(loop_scope="session")


def same_place(mine, other) -> bool:
    return mine.place == other.place


def models(rule=("source",)):
    # (the registry was reset, and a module is only run once: the model of review is declared again)
    import pangloss_review.models

    importlib.reload(pangloss_review.models)

    class Agent(Trait):
        pass

    class Person(Entity, Agent):
        _review_meta = ReviewMeta(allow_unreconciled=True)

    class Group(Entity, Agent):
        pass

    class Source(Entity):
        pass

    class Certainty(EdgeModel):
        certainty: int

    class InRole[T](ReifiedRelation[T]):
        role: str

    class Activity(Document):
        _meta = Document.Meta(create_directly=False)
        by: list[Agent]
        witness: InRole[Person] | None = None
        with_certainty: ViaEdge[Person, Certainty] | None = None
        strictly: Annotated[Person, NoUnreconciled()] | None = None

    class Factoid(Document):
        _review_meta = ReviewMeta(reviewable=True, reconcile_together=rule)
        source: Source | None = None
        place: str = ""
        statements: list[Activity]

    initialise()
    return SimpleNamespace(
        Person=Person,
        Group=Group,
        Source=Source,
        Activity=Activity,
        Factoid=Factoid,
        Unreconciled=pangloss_review.models.Unreconciled,
    )


def mention(label: str, type: str = "Person", **more) -> dict:
    return {"type": "Unreconciled", "unreconciled_type": type, "label": label, **more}


async def factoid(m, label: str, *names: str, source=None, place="", **activity):
    """A factoid with one activity, carried out by an unreconciled person of each name"""
    made = await m.Factoid.Create(
        label=label,
        source=source,
        place=place,
        statements=[
            {
                "type": "Activity",
                "label": f"{label}: activity",
                "by": [mention(name) for name in names],
                **activity,
            }
        ],
    ).save(detail=True)
    return made


def by_label(found) -> list[str]:
    return [item.label for item in found]


@no_type_check
async def test_an_unreconciled_mention_is_written_where_an_entity_goes(
    clear_database, db_driver
):
    m = models()
    made = await factoid(m, "F", "John  SMÍTH.")
    held = made.statements[0].by[0]
    assert (held.type, held.label, held.unreconciled_type) == (
        "Unreconciled",
        "John  SMÍTH.",
        "Person",
    )
    # (it is a node of the document, with its label folded for comparing; not an entity)
    rows = run(db_driver, "MATCH (u:Unreconciled) RETURN u, labels(u) AS labels")
    assert rows[0]["u"]["label_key"] == "john smith"
    assert rows[0]["u"]["head_node_id"] == str(made.id)
    assert "Entity" not in rows[0]["labels"] and "Document" in rows[0]["labels"]
    assert (await m.Person.list()).count == 0

    # what it says it is must be a class of the relation that allows it; a field may refuse it
    with pytest.raises(ValidationError, match="stands for Person, not 'Group'"):
        m.Factoid.Create(
            label="G",
            statements=[
                {
                    "type": "Activity",
                    "label": "a",
                    "by": [mention("The guild", "Group")],
                }
            ],
        )
    with pytest.raises(ValidationError):
        m.Factoid.Create(
            label="S",
            statements=[
                {"type": "Activity", "label": "a", "by": [], "strictly": mention("J")}
            ],
        )
    # (and it is not made on its own)
    with pytest.raises(Exception, match="only as part of another document"):
        await m.Unreconciled.Create(label="J", unreconciled_type="Person").save()


@no_type_check
async def test_the_mentions_are_listed_with_the_documents_they_are_in(
    clear_database, db_driver
):
    m = models()
    first = await factoid(m, "First", "John Smith", "Mary Jones")
    await factoid(
        m,
        "Second",
        witness={"type": "InRole", "role": "w", "target": [mention("Anne")]},
    )
    listed = await reconcile.list_mentions()
    assert by_label(listed.results) == ["Anne", "John Smith", "Mary Jones"]
    assert listed.count == 3
    john = listed.results[1]
    assert (john.unreconciled_type, john.head.label, john.head.type) == (
        "Person",
        "First",
        "Factoid",
    )
    # (the document it is directly in, through a wrapper too)
    assert (john.holder.type, john.holder.label) == ("Activity", "First: activity")
    assert listed.results[0].holder.label == "Second: activity"
    assert john.holder.id == first.statements[0].id

    assert by_label((await reconcile.list_mentions(q="JONES")).results) == [
        "Mary Jones"
    ]
    assert (await reconcile.list_mentions(type="Group")).count == 0
    page = await reconcile.list_mentions(page=2, page_size=2)
    assert by_label(page.results) == ["Mary Jones"]
    assert (page.previous_page, page.next_page) == (1, None)
    assert reconcile.unreconciled_types() == ["Person"]

    # of the documents given to someone to review
    from pangloss_review import service

    db_driver.execute_query("MERGE (:PGUser {username: 'ann'})", database=DATABASE_NAME)
    await service.assign(first.id, "ann", "ann", admin=False)
    assert by_label((await reconcile.list_mentions(assigned_to="ann")).results) == [
        "John Smith",
        "Mary Jones",
    ]
    assert by_label((await reconcile.list_mentions(assigned_to="")).results) == ["Anne"]

    # a deleted document's are not tasks
    await m.Factoid.delete(first.id)
    assert by_label((await reconcile.list_mentions()).results) == ["Anne"]
    with pytest.raises(PanglossNoSuchTaskError):
        await reconcile.get_mention(john.id)


@no_type_check
async def test_similar_mentions_have_the_same_label_or_one_much_like_it(
    clear_database, db_driver
):
    m = models(rule=None)
    one = await factoid(m, "One", "John Smith")
    await factoid(m, "Two", "john  smith.", "Jon Smith", "J. Smith", "Mary Smith")
    await factoid(m, "Three", "Johannes Schmidt", "JOHN SMÍTH")
    id = one.statements[0].by[0].id

    found = await reconcile.similar(id)
    assert sorted(s.label for s in found if s.exact) == ["JOHN SMÍTH", "john  smith."]
    near = {s.label: s.score for s in found if not s.exact}
    assert set(near) == {"Jon Smith", "J. Smith"}
    assert all(0.75 <= score < 1 for score in near.values())
    # (the most alike first; each with where it is)
    assert [s.score for s in found] == sorted((s.score for s in found), reverse=True)
    assert {s.head.label for s in found} == {"Two", "Three"}
    assert found[0].holder.type == "Activity"


@no_type_check
async def test_a_rule_of_the_model_says_which_mentions_go_together(
    clear_database, db_driver
):
    m = models(rule=("source",))
    register = (await m.Source.Create(label="Register").save()).id
    letters = (await m.Source.Create(label="Letters").save()).id
    ref = lambda id: {"type": "Source", "id": id}  # noqa: E731
    one = await factoid(m, "One", "John Smith", "John Smith", source=ref(register))
    await factoid(m, "Same source", "John Smith", source=ref(register))
    await factoid(m, "Other source", "John Smith", source=ref(letters))
    await factoid(m, "No source", "John Smith")

    found = await reconcile.similar(one.statements[0].by[0].id)
    # (the other in its own document, and that of the document with the same source)
    assert sorted(s.head.label for s in found) == ["One", "Same source"]


@no_type_check
async def test_a_rule_can_be_a_function_of_the_two_documents(clear_database, db_driver):
    m = models(rule=same_place)
    one = await factoid(m, "One", "John Smith", place="Paris")
    await factoid(m, "There too", "John Smith", place="Paris")
    await factoid(m, "Elsewhere", "John Smith", place="Rome")
    found = await reconcile.similar(one.statements[0].by[0].id)
    assert [s.head.label for s in found] == ["There too"]


@no_type_check
async def test_reconciling_puts_an_entity_in_the_place_of_the_mention(
    clear_database, db_driver
):
    m = models()
    db_driver.execute_query("MERGE (:PGUser {username: 'ann'})", database=DATABASE_NAME)
    john = await m.Person.Create(
        label="John Smith (1570-1630)", urls=["http://example.org/known"]
    ).save()
    other = await m.Person.Create(
        label="Other", urls=["http://example.org/taken"]
    ).save()
    made = await m.Factoid.Create(
        label="F",
        statements=[
            {
                "type": "Activity",
                "label": "a",
                "by": [
                    mention(
                        "John Smith",
                        uris=[
                            "http://example.org/known",
                            "http://example.org/new",
                            "http://example.org/taken",
                        ],
                    ),
                    mention("Mary"),
                ],
                "with_certainty": {
                    **mention("John Smith"),
                    "edge_properties": {"certainty": 3},
                },
            }
        ],
    ).save(detail=True)
    activity = made.statements[0]
    first, certain = activity.by[0].id, activity.with_certainty.id

    token = current_request_username.set("ann")
    try:
        done = await reconcile.reconcile(first, "Person", john.id)
    finally:
        current_request_username.reset(token)
    assert (done.entity.label, done.head.label, done.queued) == (
        "John Smith (1570-1630)",
        "F",
        0,
    )
    # (its URIs are the entity's now: not one it had, not one another entity has)
    assert done.uris_added == ["http://example.org/new"]
    assert done.uris_taken == ["http://example.org/taken"]
    assert sorted(str(u) for u in (await m.Person.get(john.id)).urls) == [
        "http://example.org/known",
        "http://example.org/new",
    ]
    assert [str(u) for u in (await m.Person.get(other.id)).urls] == [
        "http://example.org/taken"
    ]

    # the document was updated by the user, in the ordinary way: a version more, the same parts
    read = await m.Factoid.get(made.id)
    assert (read.meta.version, read.meta.updated_by) == (2, "ann")
    after = read.statements[0]
    assert after.id == activity.id
    assert [(a.type, a.label) for a in after.by] == [
        ("Person", "John Smith (1570-1630)"),
        ("Unreconciled", "Mary"),
    ]
    assert by_label((await reconcile.list_mentions()).results) == ["John Smith", "Mary"]
    # (the entity says what refers to it)
    assert len((await m.Person.get(john.id)).by_reverse) == 1

    # the properties of the relation stay with it
    await reconcile.reconcile(certain, "Person", john.id)
    read = await m.Factoid.get(made.id)
    kept = read.statements[0].with_certainty
    assert (kept.type, kept.id, kept.edge_properties.certainty) == (
        "Person",
        john.id,
        3,
    )

    # what cannot be done
    with pytest.raises(PanglossNoSuchTaskError):
        await reconcile.reconcile(first, "Person", john.id)
    mary = read.statements[0].by[1].id
    group = await m.Group.Create(label="A guild").save()
    with pytest.raises(PanglossReconcileError, match="cannot take the place"):
        await reconcile.reconcile(mary, "Group", group.id)
    with pytest.raises(PanglossReconcileError, match="There is no Person"):
        await reconcile.reconcile(mary, "Person", uuid4())
    assert (await m.Factoid.get(made.id)).meta.version == 3


@no_type_check
async def test_the_others_chosen_are_reconciled_in_the_background(
    clear_database, db_driver
):
    m = models(rule=None)
    john = await m.Person.Create(label="John Smith (1570-1630)").save()
    one = await factoid(m, "One", "John Smith", "John Smith")
    two = await m.Factoid.Create(
        label="Two",
        statements=[
            {
                "type": "Activity",
                "label": "a",
                "by": [mention("john smith", uris=["http://example.org/two"])],
            }
        ],
    ).save(detail=True)
    three = await factoid(m, "Three", "Jon Smith")
    left = await factoid(m, "Left", "John Smith")
    first = one.statements[0].by[0].id
    offered = await reconcile.similar(first)
    assert len(offered) == 4
    chosen = [s.id for s in offered if s.head.label != "Left"]

    # (one that is gone by then is passed over)
    done = await reconcile.reconcile(first, "Person", john.id, also=[*chosen, uuid4()])
    assert done.queued == 4
    await reconcile.background_done()

    for head in (one, two, three):
        read = await m.Factoid.get(head.id)
        assert {a.type for a in read.statements[0].by} == {"Person"}, head.label
    # (two in one document: each an update of it)
    assert (await m.Factoid.get(one.id)).meta.version == 3
    assert by_label((await reconcile.list_mentions()).results) == ["John Smith"]
    assert (await m.Factoid.get(left.id)).meta.version == 1
    assert [str(u) for u in (await m.Person.get(john.id)).urls] == [
        "http://example.org/two"
    ]
    assert len((await m.Person.get(john.id)).by_reverse) == 4


@no_type_check
async def test_reconciled_in_a_form_its_own_document_is_left_to_the_form(
    clear_database, db_driver
):
    """The form of the document puts the entity in the mention's place and saves it: here the entity is given the
    URIs, and the others in other documents are done"""
    m = models(rule=None)
    john = await m.Person.Create(label="John Smith (1570-1630)").save()
    one = await m.Factoid.Create(
        label="One",
        statements=[
            {
                "type": "Activity",
                "label": "a",
                "by": [
                    mention("John Smith", uris=["http://example.org/one"]),
                    mention("John Smith"),
                ],
            }
        ],
    ).save(detail=True)
    two = await factoid(m, "Two", "john smith")
    first = one.statements[0].by[0].id
    offered = await reconcile.similar(first)
    assert len(offered) == 2

    done = await reconcile.reconcile(
        first, "Person", john.id, also=[s.id for s in offered], in_form=True
    )
    # (only the one in another document)
    assert (done.queued, done.uris_added) == (1, ["http://example.org/one"])
    await reconcile.background_done()

    read = await m.Factoid.get(one.id)
    assert read.meta.version == 1
    assert [a.type for a in read.statements[0].by] == ["Unreconciled"] * 2
    assert {a.type for a in (await m.Factoid.get(two.id)).statements[0].by} == {
        "Person"
    }
    assert [str(u) for u in (await m.Person.get(john.id)).urls] == [
        "http://example.org/one"
    ]


@no_type_check
async def test_reconciling_over_the_api(clear_database, db_driver):
    from pangloss_api import create_app
    from pangloss_review import api

    from .test_api_models import client_for, logged_in

    m = models(rule=None)
    john = await m.Person.Create(label="John Smith (1570-1630)").save()
    one = await factoid(m, "One", "John Smith")
    await factoid(m, "Two", "John Smith")
    id = str(one.statements[0].by[0].id)

    app = create_app()
    app.include_router(api.router)
    api.configure_app(app, None)
    async with client_for(app) as client:
        assert (await client.get("/api/review/unreconciled")).status_code == 401
        ann = await logged_in(client, "ann")
        listed = (await client.get("/api/review/unreconciled", headers=ann)).json()
        assert listed["count"] == 2
        assert listed["results"][0]["unreconciledType"] == "Person"
        assert listed["results"][0]["holder"]["type"] == "Activity"
        types = await client.get("/api/review/unreconciled/types", headers=ann)
        assert types.json() == ["Person"]
        one_read = await client.get(f"/api/review/unreconciled/{id}", headers=ann)
        assert one_read.json()["head"]["label"] == "One"

        similar = (
            await client.get(f"/api/review/unreconciled/{id}/similar", headers=ann)
        ).json()
        assert [(s["head"]["label"], s["exact"], s["score"]) for s in similar] == [
            ("Two", True, 1.0)
        ]

        refused = await client.post(
            f"/api/review/unreconciled/{id}/reconcile",
            headers=ann,
            json={"entity": {"type": "Source", "id": str(john.id)}},
        )
        assert refused.status_code == 422, refused.text
        done = await client.post(
            f"/api/review/unreconciled/{id}/reconcile",
            headers=ann,
            json={
                "entity": {"type": "Person", "id": str(john.id)},
                "also": [similar[0]["id"]],
            },
        )
        assert done.status_code == 200, done.text
        assert done.json()["queued"] == 1
        assert done.json()["entity"]["label"] == "John Smith (1570-1630)"
        await reconcile.background_done()
        assert (await client.get("/api/review/unreconciled", headers=ann)).json()[
            "count"
        ] == 0
        gone = await client.get(f"/api/review/unreconciled/{id}", headers=ann)
        assert gone.status_code == 404
        # (each document was updated by the user who asked)
        read = (await client.get(f"/api/Factoid/{one.id}", headers=ann)).json()
        assert read["meta"]["updatedBy"] == "ann"
