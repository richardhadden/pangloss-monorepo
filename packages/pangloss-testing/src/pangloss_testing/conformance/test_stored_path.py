"""The path of each node of a document, as it is stored and as it is read back (`pangloss_models.context`;
implementation_docs/spaces-and-comparison-plan.md, step 1.1): on a create and on an update, in the shapes the lists
that came before the path got wrong."""

from types import SimpleNamespace as ns
from typing import Annotated, no_type_check

import pytest
from pangloss_models import (
    Conjunction,
    Degree,
    DegreeStep,
    Document,
    Match,
    Modal,
    SemanticSpace,
)

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


@no_type_check
async def test_a_node_written_now_has_no_context_labels(db_driver, clear_database):
    """The older record of a node's place, `meta.context_labels` (on Neo4j `meta.context_labels#json` and
    `meta.context_label_types` beside it), is no longer written: the path is the only one, on a create and on an
    update"""
    made, _ = declare(models)

    def stored_keys(head_id) -> list[set[str]]:
        rows = run(
            db_driver,
            "MATCH (n) WHERE n.head_node_id = $id RETURN keys(n) AS keys, n.meta AS meta",
            id=str(head_id),
        )
        assert rows
        return [set(row["keys"]) | set(row["meta"] or {}) for row in rows]

    factoid = await made.Factoid.Create(label="F", statements=statements()).save()
    for keys in stored_keys(factoid.id):
        assert not any("context_label" in key for key in keys), keys

    await made.Factoid.Update(id=factoid.id, label="F", statements=statements()).save()
    for keys in stored_keys(factoid.id):
        assert not any("context_label" in key for key in keys), keys


# --- the degree entered on a space (`Degree()`, step 2.7): in the space's entry of the path of what it holds --------


@no_type_check
def degree_models():
    class P(Document):
        pass

    class Service(Document):
        parts: list[P]

    class Hypothetical[T](SemanticSpace[T]):
        # (the class's default is not written into the path: only what is entered on the space)
        _meta = SemanticSpace.Meta(
            logical=Modal("possibility", "epistemic"), degree="possible"
        )
        how_likely: Annotated[DegreeStep | None, Degree()] = None

    class Factoid(Document):
        statements: list[P | Hypothetical[Service | Hypothetical[P]]]

    return ns(Factoid=Factoid, Service=Service)


def hypothetical(degree: str | None, *contents) -> dict:
    found = space("Hypothetical", *contents)
    if degree is not None:
        found["how_likely"] = degree
    return found


def in_hypothetical(degree: str | None) -> list[dict]:
    return [
        doc("P", "plain"),
        hypothetical(degree, doc("Service", "service", parts=[doc("P", "part")])),
    ]


def degrees(path: list[dict]) -> list[tuple[str, str | None]]:
    return [(entry["type"], entry.get("degree")) for entry in path]


def stored_degree(db_driver, head_id) -> list:
    """The field itself, as it is stored on each space of the document"""
    rows = run(
        db_driver,
        "MATCH (n) WHERE n.head_node_id = $id AND n.type = 'Hypothetical' RETURN n.how_likely AS degree",
        id=str(head_id),
    )
    return sorted((row["degree"] for row in rows), key=str)


def check_degree(nodes: dict[str, dict], degree: str | None) -> None:
    assert degrees(nodes["service"]["path"]) == [
        ("Factoid", None),
        ("Hypothetical", degree),
    ]
    # (in the space's entry alone: not in the entry of the statement that holds the part)
    assert degrees(nodes["part"]["path"]) == [
        ("Factoid", None),
        ("Hypothetical", degree),
        ("Service", None),
    ]
    if degree is None:
        assert all("degree" not in e for e in nodes["part"]["path"])
    assert "degree" not in nodes["part"]["path"][2]
    assert nodes["part"]["spaces"] == ["Hypothetical"]
    assert degrees(nodes["plain"]["path"]) == [("Factoid", None)]


@no_type_check
async def test_a_degree_entered_on_a_space_is_in_its_entry_stored_and_read_back(
    db_driver, clear_database
):
    made, _ = declare(degree_models)
    factoid = await made.Factoid.Create(
        label="F", statements=in_hypothetical("likely")
    ).save()
    check_degree(stored(db_driver, factoid.id), "likely")
    assert stored_degree(db_driver, factoid.id) == ["likely"]

    read = await made.Factoid.get(factoid.id)
    held = next(s for s in read.statements if s.type == "Hypothetical")
    assert held.how_likely == "likely"
    service = held.contents[0]
    assert service.meta.path[1] == {
        "kind": "space",
        "type": "Hypothetical",
        "id": str(held.id),
        "field": "contents",
        "degree": "likely",
    }
    assert degrees(service.parts[0].meta.path) == [
        ("Factoid", None),
        ("Hypothetical", "likely"),
        ("Service", None),
    ]
    # (a nested document read alone, or listed, has it too)
    alone = await made.Service.get(service.id)
    assert alone.meta.path[1]["degree"] == "likely"
    (listed,) = (await made.Service.list()).results
    assert listed.meta.path[1]["degree"] == "likely"
    assert listed.meta.semantic_spaces == ["Hypothetical"]


@no_type_check
async def test_a_space_in_a_space_each_has_its_own_degree_and_none_has_no_key(
    db_driver, clear_database
):
    made, _ = declare(degree_models)
    factoid = await made.Factoid.Create(
        label="F",
        statements=[
            hypothetical("unlikely", hypothetical("expected", doc("P", "twice"))),
            hypothetical(None, doc("Service", "bare", parts=[])),
        ],
    ).save()
    nodes = stored(db_driver, factoid.id)
    assert degrees(nodes["twice"]["path"]) == [
        ("Factoid", None),
        ("Hypothetical", "unlikely"),
        ("Hypothetical", "expected"),
    ]
    assert nodes["twice"]["spaces"] == ["Hypothetical", "Hypothetical"]
    # (not the class's default, "possible": nothing was entered)
    assert all("degree" not in entry for entry in nodes["bare"]["path"])
    assert stored_degree(db_driver, factoid.id) == [None, "expected", "unlikely"]


@no_type_check
async def test_an_update_that_changes_or_clears_the_degree_changes_the_entry(
    db_driver, clear_database
):
    made, _ = declare(degree_models)
    factoid = await made.Factoid.Create(
        label="F", statements=in_hypothetical("likely")
    ).save()

    await made.Factoid.Update(
        id=factoid.id, label="F", statements=in_hypothetical("unlikely")
    ).save()
    check_degree(stored(db_driver, factoid.id), "unlikely")
    assert stored_degree(db_driver, factoid.id) == ["unlikely"]
    read = await made.Factoid.get(factoid.id)
    held = next(s for s in read.statements if s.type == "Hypothetical")
    assert held.how_likely == "unlikely"
    assert held.contents[0].meta.path[1]["degree"] == "unlikely"

    await made.Factoid.Update(
        id=factoid.id, label="F", statements=in_hypothetical(None)
    ).save()
    nodes = stored(db_driver, factoid.id)
    check_degree(nodes, None)
    assert stored_degree(db_driver, factoid.id) == [None]
    read = await made.Factoid.get(factoid.id)
    held = next(s for s in read.statements if s.type == "Hypothetical")
    assert held.how_likely is None
    assert "degree" not in held.contents[0].meta.path[1]


@no_type_check
async def test_a_search_by_semantic_spaces_still_finds_what_a_space_with_a_degree_holds(
    clear_database,
):
    made, _ = declare(degree_models)
    await made.Factoid.Create(label="F", statements=in_hypothetical("likely")).save()
    await made.Factoid.Create(label="Other", statements=[doc("P", "elsewhere")]).save()

    async def found(**condition):
        return sorted(
            item.label
            for item in (
                await made.Factoid.search(
                    Match(where={"statements": {"type": "Service", "where": condition}})
                )
            ).results
        )

    assert await found(**{"$spaces": ["Hypothetical"]}) == ["F"]
