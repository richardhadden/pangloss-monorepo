import datetime
from typing import no_type_check
from uuid import uuid7

import pytest
from pangloss_models import initialise
from pangloss_models.exceptions import (
    PanglossConflictError,
    PanglossNotFoundError,
    PanglossReferenceError,
    PanglossUserNotFoundError,
)
from pangloss_models.model_bases.annotated_value import AnnotatedValue
from pangloss_models.model_bases.conjunction import Conjunction
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.edge_model import EdgeModel
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.helpers import ViaEdge
from pangloss_models.model_bases.reified_relation import ReifiedRelation
from pangloss_models.model_bases.semantic_space import SemanticSpace
from pangloss_users import current_request_username
from pydantic import AnyHttpUrl

from pangloss_memgraph.databases.memgraph.initialise_database import (
    initialise_database,
)

from .helpers import count_nodes, labels_of, mg_enum, native, run

from .test_create import Colour, Dimensions, Size  # noqa: E402

pytestmark = pytest.mark.asyncio(loop_scope="session")


def as_user(username: str):
    """Context manager: do things as another user (which must exist)"""

    class AsUser:
        def __enter__(self):
            self.token = current_request_username.set(username)

        def __exit__(self, *args):
            current_request_username.reset(self.token)

    return AsUser()


def make_user(db_driver, username: str) -> None:
    run(db_driver, "MERGE (:PGUser {username: $username})", username=username)


def snapshot(db_driver) -> dict:
    """Everything in the graph other than records of creation and update (and
    when nodes were last updated), to compare before and after"""
    nodes = run(
        db_driver,
        """
        MATCH (n:PGIndexableNode)
        RETURN n.id AS id, labels(n) AS labels, properties(n) AS properties
        ORDER BY id
        """,
    )
    edges = run(
        db_driver,
        """
        MATCH (a:PGIndexableNode)-[r]->(b:PGIndexableNode)
        RETURN a.id AS source, type(r) AS type, b.id AS target,
               properties(r) AS properties
        ORDER BY source, type, target
        """,
    )
    for node in nodes:
        node["labels"] = sorted(node["labels"])
        # Rewritten nodes are, rightly, marked as updated
        if meta := node["properties"].get("meta"):
            meta.pop("updated_when", None)
    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# Head node: properties, records of creation and update
# ---------------------------------------------------------------------------


@no_type_check
async def test_update_replaces_literals_of_head_node(db_driver, clear_database):
    class Statement(Document):
        text: str
        number: int | None
        tags: list[str]

    initialise()

    saved = await Statement.Create(
        label="Original", text="one", number=1, tags=["a"]
    ).save()

    await Statement.Update(id=saved.id, label="Changed", text="two", tags=[]).save()

    nodes = run(db_driver, "MATCH (n:Statement) RETURN n")
    assert len(nodes) == 1
    node = nodes[0]["n"]
    assert node["id"] == str(saved.id)
    assert node["label"] == "Changed"
    assert node["text"] == "two"
    assert node["tags"] == []
    # An optional literal that is left out is removed
    assert "number" not in node
    assert labels_of(db_driver, saved.id) == {
        "Statement",
        "Document",
        "HeadNode",
        "PGIndexableNode",
    }


@no_type_check
async def test_update_keeps_creation_record_and_adds_update_record(
    db_driver, clear_database
):
    class Statement(Document):
        pass

    initialise()

    make_user(db_driver, "editor")

    saved = await Statement.Create(label="Original").save()
    created_when = run(
        db_driver, "MATCH (c:PGCreation) RETURN c.created_when AS when"
    )[0]["when"]

    with as_user("editor"):
        await Statement.Update(id=saved.id, label="Edited").save()

    creations = run(
        db_driver,
        """
        MATCH (u:PGUser)<-[:created_by]-(c:PGCreation)-[:is_creation_of]->(n:Statement)
        RETURN u.username AS username, c.created_when AS when, n.id AS id
        """,
    )
    assert len(creations) == 1
    assert creations[0]["username"] == "pangloss_default_user"
    assert creations[0]["when"] == created_when
    assert creations[0]["id"] == str(saved.id)

    updates = run(
        db_driver,
        """
        MATCH (u:PGUser)<-[:updated_by]-(up:PGUpdate)-[:is_update_of]->(n:Statement)
        RETURN u.username AS username, up.updated_when AS when, n.id AS id
        """,
    )
    assert len(updates) == 1
    assert updates[0]["username"] == "editor"
    assert updates[0]["id"] == str(saved.id)
    assert native(updates[0]["when"]) > native(created_when)

    with as_user("editor"):
        await Statement.Update(id=saved.id, label="Edited again").save()
    assert count_nodes(db_driver, "PGUpdate") == 2
    assert count_nodes(db_driver, "PGCreation") == 1


@no_type_check
async def test_update_return_types_and_meta(db_driver, clear_database):
    class Statement(Document):
        text: str

    initialise()

    make_user(db_driver, "editor")
    saved = await Statement.Create(label="Original", text="one").save()

    with as_user("editor"):
        reference = await Statement.Update(
            id=saved.id, label="Second", text="two"
        ).save()
        full = await Statement.Update(
            id=saved.id, label="Third", text="three"
        ).save(detail=True)

    assert isinstance(reference, Statement.ReferenceView)
    assert reference.id == saved.id
    assert reference.label == "Second"
    assert reference.meta.created_by == "pangloss_default_user"
    assert reference.meta.updated_by == "editor"
    assert reference.meta.updated_when is not None

    assert isinstance(full, Statement.HeadView)
    assert full.label == "Third"
    assert full.text == "three"
    assert full.meta.created_by == "pangloss_default_user"
    assert full.meta.updated_by == "editor"
    assert full.meta.updated_when is not None

    read = await Statement.get(id=saved.id)
    assert read.meta.created_by == "pangloss_default_user"
    assert read.meta.updated_by == "editor"


@no_type_check
async def test_head_view_reports_the_latest_update(db_driver, clear_database):
    class Statement(Document):
        pass

    initialise()

    make_user(db_driver, "first_editor")
    make_user(db_driver, "second_editor")
    saved = await Statement.Create(label="Original").save()

    read = await Statement.get(id=saved.id)
    assert read.meta.updated_by is None

    with as_user("first_editor"):
        await Statement.Update(id=saved.id, label="One").save()
    with as_user("second_editor"):
        await Statement.Update(id=saved.id, label="Two").save()

    read = await Statement.get(id=saved.id)
    assert read.label == "Two"
    assert read.meta.updated_by == "second_editor"


@no_type_check
async def test_update_only_changes_its_own_document(db_driver, clear_database):
    class Statement(Document):
        text: str

    initialise()

    first = await Statement.Create(label="First", text="one").save()
    second = await Statement.Create(label="Second", text="two").save()

    await Statement.Update(id=first.id, label="First, edited", text="uno").save()

    rows = run(
        db_driver, "MATCH (n:Statement) RETURN n.id AS id, n.label AS l, n.text AS t"
    )
    assert {r["id"]: (r["l"], r["t"]) for r in rows} == {
        str(first.id): ("First, edited", "uno"),
        str(second.id): ("Second", "two"),
    }


@no_type_check
async def test_update_with_the_same_data_changes_nothing(db_driver, clear_database):
    class Person(Entity):
        pass

    class Action(Document):
        detail: str
        carried_out_by: Person

    class Statement(Document):
        text: str
        action: Action
        actions: list[Action]

    initialise()

    person = await Person.Create(label="John Smith").save()
    reference = {"type": "Person", "id": person.id}
    saved = await Statement.Create(
        label="A Statement",
        text="text",
        action={
            "type": "Action",
            "label": "One",
            "detail": "d1",
            "carried_out_by": reference,
        },
        actions=[
            {
                "type": "Action",
                "label": "Two",
                "detail": "d2",
                "carried_out_by": reference,
            }
        ],
    ).save()

    before = snapshot(db_driver)
    head = await Statement.get(id=saved.id)

    await Statement.Update(
        id=saved.id,
        label="A Statement",
        text="text",
        action={
            "type": "Action",
            "id": head.action.id,
            "label": "One",
            "detail": "d1",
            "carried_out_by": reference,
        },
        actions=[
            {
                "type": "Action",
                "id": head.actions[0].id,
                "label": "Two",
                "detail": "d2",
                "carried_out_by": reference,
            }
        ],
    ).save()

    assert snapshot(db_driver) == before


# ---------------------------------------------------------------------------
# Nested documents
# ---------------------------------------------------------------------------


@no_type_check
async def test_update_nested_documents_keeps_replaces_removes_and_adds(
    db_driver, clear_database
):
    class Action(Document):
        detail: str

    class Statement(Document):
        action: Action
        actions: list[Action]

    initialise()

    saved = await Statement.Create(
        label="A Statement",
        action={"type": "Action", "label": "Single", "detail": "single"},
        actions=[
            {"type": "Action", "label": "Kept", "detail": "kept"},
            {"type": "Action", "label": "Dropped", "detail": "dropped"},
        ],
    ).save()

    ids = {
        r["label"]: r["id"]
        for r in run(db_driver, "MATCH (a:Action) RETURN a.id AS id, a.label AS label")
    }

    await Statement.Update(
        id=saved.id,
        label="A Statement",
        action={
            "type": "Action",
            "id": ids["Single"],
            "label": "Single",
            "detail": "single, edited",
        },
        actions=[
            {
                "type": "Action",
                "id": ids["Kept"],
                "label": "Kept",
                "detail": "kept, edited",
            },
            {"type": "Action", "label": "Added", "detail": "added"},
        ],
    ).save()

    rows = run(
        db_driver,
        "MATCH (a:Action) RETURN a.id AS id, a.label AS label, a.detail AS detail, "
        "a.head_node_id AS head, a.head_node_type AS head_type",
    )
    by_label = {r["label"]: r for r in rows}
    assert set(by_label) == {"Single", "Kept", "Added"}
    assert by_label["Single"]["detail"] == "single, edited"
    assert by_label["Kept"]["detail"] == "kept, edited"
    assert by_label["Added"]["detail"] == "added"

    # Existing nodes keep their ids; the new one is new; the removed one is gone
    assert by_label["Single"]["id"] == ids["Single"]
    assert by_label["Kept"]["id"] == ids["Kept"]
    assert by_label["Added"]["id"] not in ids.values()
    assert ids["Dropped"] not in {r["id"] for r in rows}

    for row in rows:
        assert row["head"] == str(saved.id)
        assert row["head_type"] == "Statement"

    # Edges: one forward and one reverse per nested node, none left to the removed
    for edge, expected in (("action", 1), ("actions", 2)):
        forward = run(
            db_driver,
            f"MATCH (:Statement)-[r:{edge}]->(:Action) RETURN count(r) AS c",
        )
        reverse = run(
            db_driver,
            f"MATCH (:Statement)<-[r:{edge}_reverse {{reverse: true}}]-(:Action) "
            "RETURN count(r) AS c",
        )
        assert forward[0]["c"] == expected, edge
        assert reverse[0]["c"] == expected, edge


@no_type_check
async def test_update_keeps_creation_meta_of_nested_nodes(db_driver, clear_database):
    class Action(Document):
        pass

    class Statement(Document):
        actions: list[Action]

    initialise()

    make_user(db_driver, "editor")

    saved = await Statement.Create(
        label="A Statement", actions=[{"type": "Action", "label": "An Action"}]
    ).save()
    before = run(db_driver, "MATCH (a:Action) RETURN a.id AS id, a.meta AS meta")[0]

    with as_user("editor"):
        await Statement.Update(
            id=saved.id,
            label="A Statement",
            actions=[
                {"type": "Action", "id": before["id"], "label": "An Action, edited"},
                {"type": "Action", "label": "A new Action"},
            ],
        ).save()

    metas = {
        r["label"]: r["meta"]
        for r in run(
            db_driver, "MATCH (a:Action) RETURN a.label AS label, a.meta AS meta"
        )
    }

    kept = metas["An Action, edited"]
    assert kept["created_by"] == before["meta"]["created_by"] == "pangloss_default_user"
    assert native(kept["created_when"]) == native(before["meta"]["created_when"])
    assert native(kept["updated_when"]) > native(kept["created_when"])

    # Only new nodes are created by the user doing the update
    assert metas["A new Action"]["created_by"] == "editor"


@no_type_check
async def test_update_replaces_deeply_nested_documents(db_driver, clear_database):
    class Leaf(Document):
        value: str

    class Branch(Document):
        leaf: Leaf

    class Root(Document):
        branch: Branch

    initialise()

    saved = await Root.Create(
        label="Root",
        branch={
            "type": "Branch",
            "label": "Branch",
            "leaf": {"type": "Leaf", "label": "Leaf", "value": "old"},
        },
    ).save()

    branch_id = run(db_driver, "MATCH (b:Branch) RETURN b.id AS id")[0]["id"]

    await Root.Update(
        id=saved.id,
        label="Root",
        branch={
            "type": "Branch",
            "id": branch_id,
            "label": "Branch",
            "leaf": {"type": "Leaf", "label": "Leaf", "value": "new"},
        },
    ).save()

    assert count_nodes(db_driver, "Leaf") == 1
    assert count_nodes(db_driver, "Branch") == 1
    leaf = run(db_driver, "MATCH (:Root)-[:branch]->(:Branch)-[:leaf]->(l:Leaf) RETURN l")
    assert leaf[0]["l"]["value"] == "new"
    assert leaf[0]["l"]["head_node_id"] == str(saved.id)


@no_type_check
async def test_update_replaces_wrapper_nodes_rather_than_adding_to_them(
    db_driver, clear_database
):
    class Date(Embedded):
        when: datetime.datetime

    class WithCertainty[T](AnnotatedValue[T]):
        certainty: int

    class Place(Document):
        pass

    class Located[T](ReifiedRelation[T]):
        certainty: int

    class Causes[TCause, TResult](Conjunction):
        cause: TCause
        result: TResult

    class Action(Document):
        pass

    class Statement(Document):
        date: Date
        name: WithCertainty[str]
        located: Located[Place]
        causes: Causes[Action, Action]

    initialise()

    def payload(suffix: str, certainty: int, when: str) -> dict:
        return dict(
            label="A Statement",
            date={"type": "Date", "when": when},
            name={"value": f"name {suffix}", "certainty": certainty},
            located={
                "type": "Located",
                "certainty": certainty,
                "target": [{"type": "Place", "label": f"place {suffix}"}],
            },
            causes={
                "type": "Causes",
                "cause": {"type": "Action", "label": f"cause {suffix}"},
                "result": {"type": "Action", "label": f"result {suffix}"},
            },
        )

    saved = await Statement.Create(**payload("old", 1, "2020-01-01T00:00:00")).save()
    await Statement.Update(id=saved.id, **payload("new", 2, "2021-02-03T04:05:06")).save()

    for label in ("Date", "Located", "Place", "Causes"):
        assert count_nodes(db_driver, label) == 1, label
    assert count_nodes(db_driver, "Action") == 2

    assert native(run(db_driver, "MATCH (d:Date) RETURN d.when AS w")[0]["w"]) == (
        datetime.datetime(2021, 2, 3, 4, 5, 6)
    )
    # (an annotated value is a property of the node, so is replaced with it)
    assert run(db_driver, "MATCH (n:Statement) RETURN n.name AS name")[0]["name"] == {
        "value": "name new",
        "certainty": 2,
    }
    assert count_nodes(db_driver, "WithCertainty") == 0
    assert run(db_driver, "MATCH (n:Located) RETURN n.certainty AS c")[0]["c"] == 2
    assert run(db_driver, "MATCH (n:Place) RETURN n.label AS l")[0]["l"] == "place new"
    assert sorted(r["l"] for r in run(db_driver, "MATCH (n:Action) RETURN n.label AS l")) == [
        "cause new",
        "result new",
    ]


@no_type_check
async def test_update_semantic_spaces_and_context_labels(db_driver, clear_database):
    class Negative[T](SemanticSpace[T]):
        pass

    class Statement(Document):
        pass

    class Factoid(Document):
        statements: list[Statement | Negative[Statement]]

    initialise()

    saved = await Factoid.Create(
        label="A Factoid",
        statements=[{"type": "Statement", "label": "Plain"}],
    ).save()

    await Factoid.Update(
        id=saved.id,
        label="A Factoid",
        statements=[
            {"type": "Statement", "label": "Still plain"},
            {
                "type": "Negative",
                "contents": [{"type": "Statement", "label": "Now negated"}],
            },
        ],
    ).save()

    assert count_nodes(db_driver, "Negative") == 1
    nodes = {
        r["label"]: r
        for r in run(
            db_driver,
            "MATCH (s:Statement) RETURN s.id AS id, s.label AS label, s.meta AS meta",
        )
    }
    assert set(nodes) == {"Still plain", "Now negated"}
    assert nodes["Still plain"]["meta"]["semantic_spaces"] == []
    negated = nodes["Now negated"]
    assert negated["meta"]["semantic_spaces"] == ["Negative"]
    assert negated["meta"]["context_labels"] == [
        {"type": "Negative", "contents": [{"type": "Statement", "id": negated["id"]}]}
    ]

    rows = run(
        db_driver,
        "MATCH (:Factoid)-[:statements]->(:Negative)-[:contents]->(s:Statement) "
        "RETURN s.label AS label",
    )
    assert rows == [{"label": "Now negated"}]


# ---------------------------------------------------------------------------
# Relations to entities
# ---------------------------------------------------------------------------


@no_type_check
async def test_update_replaces_relations_to_existing_entities(
    db_driver, clear_database
):
    class Person(Entity):
        pass

    class Statement(Document):
        concerns_person: Person

    initialise()

    first = await Person.Create(label="First").save()
    second = await Person.Create(label="Second").save()

    updated = await Statement.Create(
        label="Updated", concerns_person={"type": "Person", "id": first.id}
    ).save()
    other = await Statement.Create(
        label="Other", concerns_person={"type": "Person", "id": first.id}
    ).save()

    await Statement.Update(
        id=updated.id,
        label="Updated",
        concerns_person={"type": "Person", "id": second.id},
    ).save()

    def edges(direction_query: str):
        return run(db_driver, direction_query)

    forward = edges(
        "MATCH (s:Statement)-[:concerns_person]->(p:Person) "
        "RETURN s.label AS s, p.label AS p ORDER BY s"
    )
    assert forward == [
        {"s": "Other", "p": "First"},
        {"s": "Updated", "p": "Second"},
    ]
    reverse = edges(
        "MATCH (s:Statement)<-[:concerns_person_reverse {reverse: true}]-(p:Person) "
        "RETURN s.label AS s, p.label AS p ORDER BY s"
    )
    assert reverse == forward

    # The entities themselves are untouched
    assert count_nodes(db_driver, "Person") == 2
    assert other.id


@no_type_check
async def test_update_keeps_reverse_marker_with_edge_properties(
    db_driver, clear_database
):
    class Certainty(EdgeModel):
        number: int

    class Person(Entity):
        pass

    class Statement(Document):
        concerns_person: ViaEdge[Person, Certainty]

    initialise()

    person = await Person.Create(label="John Smith").save()
    saved = await Statement.Create(
        label="A Statement",
        concerns_person={
            "type": "Person",
            "id": person.id,
            "edge_properties": {"number": 1},
        },
    ).save()

    await Statement.Update(
        id=saved.id,
        label="A Statement",
        concerns_person={
            "type": "Person",
            "id": person.id,
            "edge_properties": {"number": 2},
        },
    ).save()

    forward = run(
        db_driver,
        "MATCH (:Statement)-[r:concerns_person]->(:Person) RETURN properties(r) AS p",
    )
    reverse = run(
        db_driver,
        "MATCH (:Statement)<-[r:concerns_person_reverse]-(:Person) RETURN properties(r) AS p",
    )
    assert forward == [{"p": {"number": 2}}]
    assert reverse == [{"p": {"number": 2, "reverse": True}}]


@no_type_check
async def test_update_never_deletes_inline_entities(db_driver, clear_database):
    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Statement(Document):
        concerns_people: list[Person]

    initialise()

    person_id = uuid7()
    first = await Statement.Create(
        label="First",
        concerns_people=[
            {"type": "Person", "id": person_id, "label": "Shared", "create_new": True}
        ],
    ).save()
    second = await Statement.Create(
        label="Second", concerns_people=[{"type": "Person", "id": person_id}]
    ).save()

    # The first statement created the person, then no longer mentions them
    await Statement.Update(id=first.id, label="First", concerns_people=[]).save()

    assert count_nodes(db_driver, "Person") == 1
    rows = run(
        db_driver,
        "MATCH (s:Statement)-[:concerns_people]->(p:Person) "
        "RETURN s.id AS s, p.id AS p",
    )
    assert rows == [{"s": str(second.id), "p": str(person_id)}]
    assert (
        run(
            db_driver,
            "MATCH (:Person)-[r:concerns_people_reverse]->(:Statement) RETURN count(r) AS c",
        )[0]["c"]
        == 1
    )


@no_type_check
async def test_update_can_create_inline_entities(db_driver, clear_database):
    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Statement(Document):
        concerns_people: list[Person]

    initialise()

    saved = await Statement.Create(label="A Statement", concerns_people=[]).save()

    new_id = uuid7()
    await Statement.Update(
        id=saved.id,
        label="A Statement",
        concerns_people=[
            {"type": "Person", "id": new_id, "label": "New Person", "create_new": True}
        ],
    ).save()

    person = run(db_driver, "MATCH (p:Person) RETURN p")[0]["p"]
    assert person["id"] == str(new_id)
    assert person["label"] == "New Person"
    # (an entity of its own, not part of the statement that created it)
    assert "head_node_id" not in person
    assert "HeadNode" in labels_of(db_driver, new_id)
    assert (
        run(db_driver, "MATCH (:Statement)-[r:concerns_people]->(:Person) RETURN count(r) AS c")[0]["c"]
        == 1
    )


# ---------------------------------------------------------------------------
# Updating entities
# ---------------------------------------------------------------------------


@no_type_check
async def test_update_entity_replaces_properties_and_own_relations_only(
    db_driver, clear_database
):
    class Place(Entity):
        pass

    class Person(Entity):
        born: int | None
        lives_in: list[Place]

    class Statement(Document):
        concerns_person: Person

    initialise()

    old_place = await Place.Create(label="Old place").save()
    new_place = await Place.Create(label="New place").save()
    person = await Person.Create(
        label="John Smith",
        born=1900,
        lives_in=[{"type": "Place", "id": old_place.id}],
    ).save()
    await Statement.Create(
        label="A Statement", concerns_person={"type": "Person", "id": person.id}
    ).save()

    result = await Person.Update(
        id=person.id,
        label="John Smith, edited",
        lives_in=[{"type": "Place", "id": new_place.id}],
    ).save()
    assert isinstance(result, Person.ReferenceView)
    assert result.label == "John Smith, edited"

    node = run(db_driver, "MATCH (p:Person) RETURN p")[0]["p"]
    assert node["id"] == str(person.id)
    assert node["label"] == "John Smith, edited"
    assert "born" not in node
    assert labels_of(db_driver, person.id) >= {"Person", "Entity", "HeadNode"}

    # The entity's own relation was replaced...
    lives_in = run(
        db_driver, "MATCH (:Person)-[:lives_in]->(p:Place) RETURN p.label AS l"
    )
    assert lives_in == [{"l": "New place"}]
    assert (
        run(db_driver, "MATCH ()-[r:lives_in_reverse]->(:Person) RETURN count(r) AS c")[
            0
        ]["c"]
        == 1
    )
    # ...but the document's relation to the entity, in both directions, was not
    assert (
        run(
            db_driver,
            "MATCH (:Statement)-[:concerns_person]->(:Person) RETURN count(*) AS c",
        )[0]["c"]
        == 1
    )
    assert (
        run(
            db_driver,
            "MATCH (:Statement)<-[r:concerns_person_reverse {reverse: true}]-(:Person) "
            "RETURN count(r) AS c",
        )[0]["c"]
        == 1
    )
    assert count_nodes(db_driver, "Person") == 1
    assert count_nodes(db_driver, "Place") == 2


@no_type_check
async def test_update_entity_keeps_its_urls(db_driver, clear_database):
    class Person(Entity):
        _meta = Entity.Meta(create_with_id=True)

    initialise()

    url = "http://example.com/people/john-smith"
    saved = await Person.Create(id=AnyHttpUrl(url), create_new=True, label="JS").save()

    await Person.Update(id=saved.id, label="John Smith").save()

    node = run(db_driver, "MATCH (p:Person) RETURN p")[0]["p"]
    assert node["label"] == "John Smith"
    rows = run(db_driver, "MATCH (:Person)-[:has_url]->(u:PGUrl) RETURN u.url AS url")
    assert rows == [{"url": url}]


# ---------------------------------------------------------------------------
# Errors: nothing is changed
# ---------------------------------------------------------------------------


@no_type_check
async def test_update_of_missing_document_raises(db_driver, clear_database):
    class Statement(Document):
        pass

    initialise()

    missing_id = uuid7()
    with pytest.raises(PanglossNotFoundError, match=str(missing_id)):
        await Statement.Update(id=missing_id, label="Nothing here").save()

    assert count_nodes(db_driver, "Statement") == 0
    assert count_nodes(db_driver, "PGUpdate") == 0


@no_type_check
async def test_update_with_id_of_a_different_type_raises(db_driver, clear_database):
    class Statement(Document):
        pass

    class Order(Document):
        pass

    initialise()

    order = await Order.Create(label="An Order").save()
    before = snapshot(db_driver)

    with pytest.raises(PanglossNotFoundError):
        await Statement.Update(id=order.id, label="Not an Order").save()

    assert snapshot(db_driver) == before
    assert count_nodes(db_driver, "PGUpdate") == 0


@no_type_check
async def test_update_with_missing_reference_raises_and_changes_nothing(
    db_driver, clear_database
):
    class Person(Entity):
        pass

    class Action(Document):
        carried_out_by: Person

    class Statement(Document):
        action: Action

    initialise()

    person = await Person.Create(label="John Smith").save()
    saved = await Statement.Create(
        label="Original",
        action={
            "type": "Action",
            "label": "An Action",
            "carried_out_by": {"type": "Person", "id": person.id},
        },
    ).save()
    before = snapshot(db_driver)

    with pytest.raises(PanglossReferenceError):
        await Statement.Update(
            id=saved.id,
            label="Changed",
            action={
                "type": "Action",
                "label": "Changed action",
                "carried_out_by": {"type": "Person", "id": uuid7()},
            },
        ).save()

    # The old tree was not touched, because it is checked before anything is deleted
    assert snapshot(db_driver) == before
    assert count_nodes(db_driver, "PGUpdate") == 0


@no_type_check
async def test_update_with_reference_of_disallowed_type_raises_and_changes_nothing(
    db_driver, clear_database
):
    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class Statement(Document):
        concerns_person: Person

    initialise()

    person = await Person.Create(label="John Smith").save()
    place = await Place.Create(label="A Place").save()
    saved = await Statement.Create(
        label="Original", concerns_person={"type": "Person", "id": person.id}
    ).save()
    before = snapshot(db_driver)

    with pytest.raises(PanglossReferenceError):
        await Statement.Update(
            id=saved.id,
            label="Changed",
            concerns_person={"type": "Person", "id": place.id},
        ).save()

    assert snapshot(db_driver) == before


@no_type_check
async def test_update_with_nested_id_of_another_document_raises_and_changes_nothing(
    db_driver, clear_database
):
    class Action(Document):
        detail: str

    class Statement(Document):
        action: Action

    initialise()

    first = await Statement.Create(
        label="First",
        action={"type": "Action", "label": "First action", "detail": "first"},
    ).save()
    second = await Statement.Create(
        label="Second",
        action={"type": "Action", "label": "Second action", "detail": "second"},
    ).save()
    second_action_id = run(
        db_driver,
        "MATCH (:Statement {id: $id})-[:action]->(a:Action) RETURN a.id AS id",
        id=str(second.id),
    )[0]["id"]
    before = snapshot(db_driver)

    # An id of a node that belongs to a different document
    with pytest.raises(PanglossConflictError, match=second_action_id):
        await Statement.Update(
            id=first.id,
            label="First, edited",
            action={
                "type": "Action",
                "id": second_action_id,
                "label": "Stolen",
                "detail": "stolen",
            },
        ).save()

    assert snapshot(db_driver) == before


@no_type_check
async def test_update_as_unknown_user_raises_and_changes_nothing(
    db_driver, clear_database
):
    class Statement(Document):
        pass

    initialise()

    saved = await Statement.Create(label="Original").save()
    before = snapshot(db_driver)

    with as_user("nobody_by_this_name"):
        with pytest.raises(PanglossUserNotFoundError):
            await Statement.Update(id=saved.id, label="Changed").save()

    assert snapshot(db_driver) == before


@no_type_check
async def test_update_entity_of_missing_id_raises(db_driver, clear_database):
    class Person(Entity):
        pass

    initialise()

    with pytest.raises(PanglossNotFoundError):
        await Person.Update(id=uuid7(), label="Nobody").save()

    assert count_nodes(db_driver, "Person") == 0


@no_type_check
async def test_update_replaces_an_annotated_value(db_driver, clear_database):
    class WithCertainty[T](AnnotatedValue[T]):
        certainty: int

    class Naming(Document):
        name: WithCertainty[str]

    initialise()

    saved = await Naming.Create(
        label="A Naming", name={"value": "Johann", "certainty": 1}
    ).save()
    await Naming.Update(
        id=saved.id, label="A Naming", name={"value": "Giovanni", "certainty": 2}
    ).save()

    node = run(db_driver, "MATCH (n:Naming) RETURN n")[0]["n"]
    assert node["name"] == {"value": "Giovanni", "certainty": 2}

    read = await Naming.get(id=saved.id)
    assert (read.name.value, read.name.certainty) == ("Giovanni", 2)


@no_type_check
async def test_update_replaces_enum_values(db_driver, clear_database):
    class Statement(Document):
        colour: Colour
        colours: list[Colour]
        sizes: Dimensions | None = None

    initialise()
    await initialise_database()

    saved = await Statement.Create(
        label="A Statement", colour=Colour.RED, colours=[Colour.RED], sizes=None
    ).save()

    await Statement.Update(
        id=saved.id,
        label="A Statement",
        colour="blue",
        colours=[Colour.BLUE, Colour.RED],
    ).save()

    node = run(db_driver, "MATCH (n:Statement) RETURN n")[0]["n"]
    assert node["colour"] == mg_enum("Colour::BLUE")
    assert node["colours"] == [mg_enum("Colour::BLUE"), mg_enum("Colour::RED")]

    read = await Statement.get(id=saved.id)
    assert read.colour is Colour.BLUE
    assert read.colours == [Colour.BLUE, Colour.RED]


@no_type_check
async def test_update_with_enums_on_nested_documents_and_edges(db_driver, clear_database):
    class Certainty(EdgeModel):
        colour: Colour

    class Person(Entity):
        pass

    class Action(Document):
        size: Size

    class Statement(Document):
        action: Action
        concerns: ViaEdge[Person, Certainty]

    initialise()
    await initialise_database()

    person = await Person.Create(label="John Smith").save()
    reference = {"type": "Person", "id": person.id}
    saved = await Statement.Create(
        label="A Statement",
        action={"type": "Action", "label": "An Action", "size": 1},
        concerns={**reference, "edge_properties": {"colour": "red"}},
    ).save()
    await Statement.Update(
        id=saved.id,
        label="A Statement",
        action={"type": "Action", "label": "An Action", "size": 2},
        concerns={**reference, "edge_properties": {"colour": "blue"}},
    ).save()

    action = run(db_driver, "MATCH (a:Action) RETURN a")[0]["a"]
    assert action["size"] == mg_enum("Size::LARGE")
    for edge in ("concerns", "concerns_reverse"):
        props = run(db_driver, f"MATCH ()-[r:{edge}]->() RETURN properties(r) AS p")[0]["p"]
        assert props["colour"] == mg_enum("Colour::BLUE"), edge


@no_type_check
async def test_update_switches_the_member_of_a_union_of_embedded_objects(
    db_driver, clear_database
):
    class Date(Embedded):
        when: datetime.date

    class DateRange(Embedded):
        start: datetime.date
        end: datetime.date

    class Statement(Document):
        date: Date | DateRange

    initialise()

    saved = await Statement.Create(
        label="A Statement", date={"type": "Date", "when": "2020-01-01"}
    ).save()
    await Statement.Update(
        id=saved.id,
        label="A Statement",
        date={"type": "DateRange", "start": "2020-01-01", "end": "2020-12-31"},
    ).save()

    assert count_nodes(db_driver, "Date") == 0
    assert count_nodes(db_driver, "DateRange") == 1
    read = await Statement.get(id=saved.id)
    assert read.date.type == "DateRange"
    assert read.date.end == datetime.date(2020, 12, 31)
