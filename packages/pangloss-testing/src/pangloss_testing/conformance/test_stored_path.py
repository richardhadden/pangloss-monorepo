"""The path of each node of a document, as it is stored and as it is read back (`pangloss_models.context`;
implementation_docs/spaces-and-comparison-plan.md, step 1.1): on a create and on an update, in the shapes the lists
that came before the path got wrong."""

from types import SimpleNamespace as ns
from typing import no_type_check

import pytest
from pangloss_models import Conjunction, Document, SemanticSpace

from .helpers import run
from .migration_support import declare

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
def models():
    class P(Document):
        pass

    class Not[T](SemanticSpace[T]):
        pass

    class Ordered[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing: Ordered[P]
        witnesses: list[P]

    class Causes(Conjunction):
        cause: P | Not[P] | Order
        result: P

    class Factoid(Document):
        statements: list[P | Not[P | Not[P]] | Order | Causes]

    return ns(Factoid=Factoid)


def doc(type: str, label: str, **fields) -> dict:
    return {"type": type, "label": label, **fields}


def space(type: str, *contents) -> dict:
    return {"type": type, "contents": list(contents)}


def statements() -> list[dict]:
    return [
        doc("P", "plain"),
        space("Not", space("Not", doc("P", "twice"))),
        doc(
            "Order",
            "order",
            thing=space("Ordered", doc("P", "ordered")),
            witnesses=[doc("P", "witness")],
        ),
        {
            "type": "Causes",
            "cause": space("Not", doc("P", "cause")),
            "result": doc("P", "result"),
        },
    ]


def stored(db_driver, head_id) -> dict[str, dict]:
    """What is stored of each labelled node below the head: its semantic spaces and its path"""
    rows = run(
        db_driver,
        """
        MATCH (n) WHERE n.head_node_id = $id
        RETURN n.id AS id, n.type AS type, n.label AS label, n.meta.semantic_spaces AS spaces, n.meta.path AS path
        """,
        id=str(head_id),
    )
    return {row["label"] or row["id"]: row for row in rows}


def trail(path: list[dict]) -> list[str]:
    return [f"{entry['kind']}:{entry['type']}.{entry['field']}" for entry in path]


def check(nodes: dict[str, dict], head_id) -> None:
    assert trail(nodes["plain"]["path"]) == ["document:Factoid.statements"]
    assert nodes["plain"]["spaces"] == []

    assert trail(nodes["twice"]["path"]) == [
        "document:Factoid.statements",
        "space:Not.contents",
        "space:Not.contents",
    ]
    assert nodes["twice"]["spaces"] == ["Not", "Not"]

    assert trail(nodes["ordered"]["path"]) == [
        "document:Factoid.statements",
        "document:Order.thing",
        "space:Ordered.contents",
    ]
    assert nodes["ordered"]["spaces"] == ["Ordered"]
    # (after a single relation that holds a space: not in it)
    assert trail(nodes["witness"]["path"]) == [
        "document:Factoid.statements",
        "document:Order.witnesses",
    ]
    assert nodes["witness"]["spaces"] == []

    assert nodes["cause"]["spaces"] == ["Not"]
    assert trail(nodes["result"]["path"]) == [
        "document:Factoid.statements",
        "conjunction:Causes.result",
    ]
    assert nodes["result"]["spaces"] == []

    by_id = {row["id"]: row for row in nodes.values()}
    for row in nodes.values():
        # (each entry names a node of the document by its id, the head first; a node is not in its own path)
        assert row["path"][0]["id"] == str(head_id)
        assert all(entry["id"] in by_id for entry in row["path"][1:])
        assert all(entry["id"] != row["id"] for entry in row["path"])
        assert [by_id[entry["id"]]["type"] for entry in row["path"][1:]] == [
            entry["type"] for entry in row["path"][1:]
        ]
        assert row["spaces"] == [e["type"] for e in row["path"] if e["kind"] == "space"]
    # (a space has a path too, and is in the spaces above it)
    spaces = [row for row in nodes.values() if row["type"] == "Not"]
    assert sorted(len(row["path"]) for row in spaces) == [1, 2, 2]
    assert sorted(row["spaces"] for row in spaces) == [[], [], ["Not"]]


@no_type_check
async def test_the_path_of_each_node_is_written_on_a_create_and_read_back(
    db_driver, clear_database
):
    made, _ = declare(models)
    factoid = await made.Factoid.Create(label="F", statements=statements()).save()
    check(stored(db_driver, factoid.id), factoid.id)

    read = await made.Factoid.get(factoid.id)
    assert read.meta.path == []
    order = next(s for s in read.statements if s.type == "Order")
    assert trail(order.meta.path) == ["document:Factoid.statements"]
    ordered = order.thing.contents[0]
    assert trail(ordered.meta.path) == [
        "document:Factoid.statements",
        "document:Order.thing",
        "space:Ordered.contents",
    ]
    assert ordered.meta.path[1]["id"] == str(order.id)
    assert ordered.meta.semantic_spaces == ["Ordered"]
    assert order.witnesses[0].meta.semantic_spaces == []


@no_type_check
async def test_the_path_of_each_node_is_written_again_on_an_update(
    db_driver, clear_database
):
    made, _ = declare(models)
    factoid = await made.Factoid.Create(
        label="F", statements=[doc("P", "plain")]
    ).save()
    await made.Factoid.Update(id=factoid.id, label="F", statements=statements()).save()
    check(stored(db_driver, factoid.id), factoid.id)

    # (and a statement moved out of a space is no longer in it)
    await made.Factoid.Update(
        id=factoid.id, label="F", statements=[doc("P", "twice")]
    ).save()
    nodes = stored(db_driver, factoid.id)
    assert list(nodes) == ["twice"]
    assert nodes["twice"]["spaces"] == []
    assert trail(nodes["twice"]["path"]) == ["document:Factoid.statements"]


@no_type_check
async def test_a_nested_document_listed_or_read_alone_has_its_path(clear_database):
    made, _ = declare(models)
    factoid = await made.Factoid.Create(label="F", statements=statements()).save()
    from pangloss_models import ModelRegistry

    P = ModelRegistry._model_dict["P"]
    listed = {item.label: item for item in (await P.list(page_size=50)).results}
    assert trail(listed["cause"].meta.path) == [
        "document:Factoid.statements",
        "conjunction:Causes.cause",
        "space:Not.contents",
    ]
    assert listed["cause"].meta.path[0]["id"] == str(factoid.id)
    assert listed["result"].meta.semantic_spaces == []

    alone = await P.get(listed["ordered"].id)
    assert trail(alone.meta.path) == [
        "document:Factoid.statements",
        "document:Order.thing",
        "space:Ordered.contents",
    ]


@pytest.mark.stored_by_hand
@no_type_check
async def test_the_check_of_paths_finds_a_node_whose_path_is_not_its_place(
    db_driver, clear_database
):
    """`assert_paths_true` runs after every test that looks underneath (`conftest.paths_are_true`): it has to
    notice a path that is wrong, here one moved by hand"""
    from .helpers import assert_paths_true, memgraph_meta

    made, _ = declare(models)
    factoid = await made.Factoid.Create(label="F", statements=statements()).save()
    assert_paths_true(db_driver)

    before = stored(db_driver, factoid.id)
    # (the witness given the path of what is ordered: the fault the path replaced)
    wrong = before["ordered"]["path"]
    if "meta.path#json" in memgraph_meta("n.meta.path AS path"):
        import json

        db_driver.execute_query(
            "MATCH (n {id: $id}) SET n.`meta.path#json` = $path",
            id=before["witness"]["id"],
            path=json.dumps(wrong),
        )
    else:
        db_driver.execute_query(
            "MATCH (n {id: $id}) SET n.meta = $meta",
            id=before["witness"]["id"],
            meta={"created_by": "x", "semantic_spaces": [], "path": wrong},
        )
    with pytest.raises(AssertionError, match="has the path"):
        assert_paths_true(db_driver)
