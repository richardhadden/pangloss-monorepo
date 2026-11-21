"""A vector index as a kind of index (`AddIndex` with `"kind": "vector"`), made and dropped by migrations, and the search
of one that every backend with the capability `vector_index` gives (`Dialect.vector_search`)"""

import math
import random
import sys
import types

import pytest
import pytest_asyncio
from pangloss_core import backend as core_backend
from pangloss_core import settings as core_settings
from pangloss_cypher.migrations import apply_changes
from pangloss_models import PanglossMigrationError
from pangloss_models.migrations import Migration, build_snapshot, data_view, diff
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.files import EMPTY_SNAPSHOT
from pangloss_models.migrations.reverse import reverse_changes
from pangloss_testing.backends import under_test
from pangloss_testing.under_test import migration_backend as backend
from pangloss_testing.under_test.database import current

from .helpers import DATABASE_NAME

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.requires("vector_index"),
]

LABEL = "PgTestVector"
NAME = "pg_test_vectors"
ENTRY = {
    "kind": "vector",
    "name": NAME,
    "label": LABEL,
    "properties": ["vector"],
    "dimension": 4,
    "metric": "cos",
    "capacity": 16,
}


def vector_indexes(db_driver) -> dict[str, tuple[str, str, int]]:
    """The vector indexes of the database, by name: (label, property, dimension), as the backend lists them"""
    with db_driver.session(database=DATABASE_NAME) as session:  # (not in a transaction)
        if under_test().name == "neo4j":
            rows = session.run(
                "SHOW INDEXES YIELD name, type, labelsOrTypes, properties, options WHERE type = 'VECTOR' RETURN *"
            ).data()
            return {
                r["name"]: (
                    r["labelsOrTypes"][0],
                    r["properties"][0],
                    r["options"]["indexConfig"]["vector.dimensions"],
                )
                for r in rows
            }
        rows = session.run("SHOW VECTOR INDEX INFO").data()
        return {
            r["index_name"]: (
                r["label"].removeprefix(":"),
                r["property"],
                r["dimension"],
            )
            for r in rows
        }


def drop_test_indexes(db_driver) -> None:
    with db_driver.session(database=DATABASE_NAME) as session:
        for name in vector_indexes(db_driver):
            if name.startswith("pg_test_"):
                drop = (
                    f"DROP INDEX {name} IF EXISTS"
                    if under_test().name == "neo4j"
                    else f"DROP VECTOR INDEX {name}"
                )
                session.run(drop).consume()


def collect_deleted(db_driver) -> None:
    """(Memgraph's vector index keeps a deleted node until the database collects it, and a search gives it, taking one
    of the `k` places (`vector_search` drops it): the nodes of an earlier test would leave this one's fewer places)"""
    if under_test().name == "memgraph":
        with db_driver.session(database=DATABASE_NAME) as session:
            session.run("FREE MEMORY").consume()


@pytest.fixture
def no_test_indexes(db_driver, clear_database):
    """No vector index of the tests' before the test, nor after it (the database is emptied, its indexes are not)"""
    drop_test_indexes(db_driver)
    collect_deleted(db_driver)
    yield
    drop_test_indexes(db_driver)


def query(db_driver, cypher: str, **parameters) -> list[dict]:
    records, _, _ = db_driver.execute_query(
        cypher, parameters_=parameters, database_=DATABASE_NAME
    )
    return [r.data() for r in records]


def dialect():
    return core_backend.current(under_test().storage).dialect


# ---------------------------------------------------------------------------
# Made and dropped by migrations
# ---------------------------------------------------------------------------


async def test_a_migration_makes_a_vector_index_and_undoing_it_drops_it(
    db_driver, no_test_indexes
):
    await backend.ensure_ready()
    migration = Migration(
        app="pg_test_vectors", name="0001_vectors", changes=(c.AddIndex(index=ENTRY),)
    )
    state = await backend.apply([migration], EMPTY_SNAPSHOT)
    assert vector_indexes(db_driver)[NAME] == (LABEL, "vector", 4)
    assert state["indexes"] == [ENTRY]

    # (made again: nothing is made, and nothing fails)
    await apply_changes(current(), EMPTY_SNAPSHOT, [c.AddIndex(index=ENTRY)])
    assert [n for n in vector_indexes(db_driver) if n.startswith("pg_test_")] == [NAME]

    # undone
    undo = Migration(
        app="pg_test_vectors",
        name="0001_vectors",
        changes=tuple(
            reverse_changes(migration.changes, data_view(EMPTY_SNAPSHOT)).changes
        ),
    )
    after = await backend.unapply([undo], state)
    assert NAME not in vector_indexes(db_driver)
    assert after["indexes"] == []


async def test_remove_index_drops_a_vector_index_and_dropping_it_again_is_harmless(
    db_driver, no_test_indexes
):
    await apply_changes(current(), EMPTY_SNAPSHOT, [c.AddIndex(index=ENTRY)])
    assert NAME in vector_indexes(db_driver)
    state = await apply_changes(
        current(), {**EMPTY_SNAPSHOT, "indexes": [ENTRY]}, [c.RemoveIndex(index=ENTRY)]
    )
    assert NAME not in vector_indexes(db_driver)
    assert state["indexes"] == []
    await apply_changes(current(), EMPTY_SNAPSHOT, [c.RemoveIndex(index=ENTRY)])


async def test_a_vector_index_of_the_same_name_with_another_dimension_is_refused_by_name(
    db_driver, no_test_indexes
):
    await apply_changes(current(), EMPTY_SNAPSHOT, [c.AddIndex(index=ENTRY)])
    wider = {**ENTRY, "dimension": 8}
    with pytest.raises(PanglossMigrationError, match=NAME) as raised:
        await apply_changes(current(), EMPTY_SNAPSHOT, [c.AddIndex(index=wider)])
    assert "dimension 4" in str(raised.value) and "dimension 8" in str(raised.value)
    assert vector_indexes(db_driver)[NAME] == (LABEL, "vector", 4)

    # ... and the models' change of it is a remove and an add, the remove first: that is made
    before, after = (
        {**EMPTY_SNAPSHOT, "indexes": [ENTRY]},
        {**EMPTY_SNAPSHOT, "indexes": [wider]},
    )
    changes = diff(before, after).changes
    assert changes == [c.RemoveIndex(index=ENTRY), c.AddIndex(index=wider)]
    await apply_changes(current(), before, changes)
    assert vector_indexes(db_driver)[NAME] == (LABEL, "vector", 8)


def quantized(db_driver, name: str) -> bool | None:
    """Whether Neo4j keeps the vectors of the index quantized (None: the database has no such setting)"""
    if under_test().name != "neo4j":
        return None
    rows = query(
        db_driver,
        "SHOW INDEXES YIELD name, options WHERE name = $name RETURN options",
        name=name,
    )
    config = rows[0]["options"]["indexConfig"]
    # (Neo4j 2026.10 lists the setting as a type, `NONE` when it is off; the index is made with `enabled`)
    if "vector.quantization.type" in config:
        return config["vector.quantization.type"] != "NONE"
    return config["vector.quantization.enabled"]


async def test_a_vector_index_without_quantization_is_made_so_and_one_with_it_as_the_database_does(
    db_driver, no_test_indexes
):
    """(`"quantization": False` turns Neo4j's quantized storage off, which costs recall; Memgraph has no such setting
    and makes the index as it would without the key)"""
    plain = {**ENTRY, "quantization": False}
    await apply_changes(current(), EMPTY_SNAPSHOT, [c.AddIndex(index=plain)])
    assert vector_indexes(db_driver)[NAME] == (LABEL, "vector", 4)
    assert quantized(db_driver, NAME) in (False, None)
    if under_test().name == "neo4j":
        assert quantized(db_driver, NAME) is False

    # (without the key, or with True: the database's default, which is quantized on Neo4j)
    other = {**ENTRY, "name": "pg_test_vectors_q", "label": "PgTestVectorQ"}
    await apply_changes(current(), EMPTY_SNAPSHOT, [c.AddIndex(index=other)])
    assert quantized(db_driver, "pg_test_vectors_q") in (True, None)
    if under_test().name == "neo4j":
        assert quantized(db_driver, "pg_test_vectors_q") is True


async def test_a_vector_index_on_a_label_and_property_that_have_one_already_says_it_was_not_made(
    db_driver, no_test_indexes
):
    """(both databases make nothing, and say nothing, for a second index on the same label and property)"""
    await apply_changes(current(), EMPTY_SNAPSHOT, [c.AddIndex(index=ENTRY)])
    second = {**ENTRY, "name": "pg_test_vectors_two"}
    with pytest.raises(
        PanglossMigrationError, match=f"pg_test_vectors_two was not made.*{NAME}"
    ):
        await apply_changes(current(), EMPTY_SNAPSHOT, [c.AddIndex(index=second)])
    assert "pg_test_vectors_two" not in vector_indexes(db_driver)


async def test_the_structure_an_app_asks_for_holds_its_vector_index_and_a_missing_one_is_found(
    db_driver, no_test_indexes, monkeypatch
):
    """An app's `structure.INDEXES` may list a vector index: it is in the structure the backend says the database
    needs, so the models are not what migrations come to until one makes it (`migration_problems`), and the change
    that makes it is found"""
    app = types.ModuleType("pg_test_vector_app")
    structure = types.ModuleType("pg_test_vector_app.structure")
    structure.INDEXES = [ENTRY]  # ty: ignore[unresolved-attribute]
    monkeypatch.setitem(sys.modules, "pg_test_vector_app", app)
    monkeypatch.setitem(sys.modules, "pg_test_vector_app.structure", structure)
    settings = core_settings.__dict__["SETTINGS"]
    monkeypatch.setattr(settings, "INSTALLED_APPS", ["pg_test_vector_app"])

    needed = backend.structure()
    assert {**ENTRY, "app": "pg_test_vector_app"} in needed["indexes"]

    without = build_snapshot(
        {
            **needed,
            "indexes": [e for e in needed["indexes"] if e.get("kind") != "vector"],
        }
    )
    wanted = build_snapshot(needed)
    assert data_view(without) != data_view(wanted)
    changes = diff(without, wanted).changes
    assert changes == [c.AddIndex(index=ENTRY)]

    await apply_changes(current(), data_view(without), changes)
    assert vector_indexes(db_driver)[NAME] == (LABEL, "vector", 4)


# ---------------------------------------------------------------------------
# The search (`Dialect.vector_search`)
# ---------------------------------------------------------------------------

QUERY = [0.3, 0.5, 0.1, 0.8]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True)) / (
        math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    )


def known_vectors() -> list[list[float]]:
    found = random.Random(7)
    return [[round(found.uniform(-1, 1), 3) for _ in range(4)] for _ in range(10)]


@pytest_asyncio.fixture(loop_scope="session")
async def ten_nodes(db_driver, no_test_indexes) -> list[tuple[int, float]]:
    """Ten nodes with known vectors, in a vector index made by `AddIndex`: each node's `of` and its cosine with `QUERY`,
    the nearest first"""
    await apply_changes(current(), EMPTY_SNAPSHOT, [c.AddIndex(index=ENTRY)])
    vectors = known_vectors()
    query(
        db_driver,
        f"UNWIND $rows AS row CREATE (n:{LABEL} {{of: row.of, vector: row.vector}})",
        rows=[{"of": i, "vector": v} for i, v in enumerate(vectors)],
    )
    nearest = sorted(
        ((i, cosine(QUERY, v)) for i, v in enumerate(vectors)), key=lambda p: -p[1]
    )
    # (the four nearest are told apart, so the order is the vectors', not the index's)
    assert all(
        a[1] - b[1] > 1e-3 for a, b in zip(nearest[:4], nearest[1:5], strict=True)
    )
    return nearest


def search(k: int = 3, carry=(), before: str = "") -> tuple[str, dict]:
    cypher = (
        f"{before} {dialect().vector_search(NAME, '$k', '$vector', carry)} "
        f"RETURN {''.join(f'{v}, ' for v in carry)}node.of AS of, score"
    )
    return cypher, {"k": k, "vector": QUERY}


async def test_the_nearest_come_back_in_order_with_the_cosine_as_score(
    db_driver, ten_nodes
):
    cypher, parameters = search()
    rows = query(db_driver, cypher, **parameters)
    assert [r["of"] for r in rows] == [i for i, _ in ten_nodes[:3]]
    for row, (_, expected) in zip(rows, ten_nodes, strict=False):
        assert row["score"] == pytest.approx(expected, abs=1e-4)


async def test_a_carried_variable_is_kept_and_no_other(db_driver, ten_nodes):
    cypher, parameters = search(carry=["x"], before="UNWIND [1] AS x")
    rows = query(db_driver, cypher, **parameters)
    assert [(r["x"], r["of"]) for r in rows] == [(1, i) for i, _ in ten_nodes[:3]]

    cypher, parameters = search(before="WITH 1 AS y")
    with pytest.raises(Exception, match="y"):
        query(db_driver, cypher.replace("RETURN ", "RETURN y, "), **parameters)


async def test_a_node_deleted_before_the_search_is_not_found_and_nothing_fails(
    db_driver, ten_nodes
):
    nearest = ten_nodes[0][0]
    query(db_driver, f"MATCH (n:{LABEL} {{of: $of}}) DETACH DELETE n", of=nearest)
    cypher, parameters = search()
    rows = query(db_driver, cypher, **parameters)
    found = [r["of"] for r in rows]
    # (fewer than asked may come: the deleted node may have taken a place)
    assert nearest not in found and found
    assert found == [i for i, _ in ten_nodes[1 : 1 + len(found)]]


async def test_a_node_deleted_in_the_same_transaction_is_not_found_and_nothing_fails(
    db_driver, ten_nodes
):
    nearest = ten_nodes[0][0]
    cypher, parameters = search()
    with db_driver.session(database=DATABASE_NAME) as session:
        with session.begin_transaction() as tx:
            tx.run(
                f"MATCH (n:{LABEL} {{of: $of}}) DETACH DELETE n", of=nearest
            ).consume()
            found = [r["of"] for r in tx.run(cypher, **parameters)]
            tx.commit()
    assert nearest not in found and found
    assert found == [i for i, _ in ten_nodes[1 : 1 + len(found)]]

    # (and in a later transaction too)
    rows = query(db_driver, cypher, **parameters)
    assert nearest not in [r["of"] for r in rows]


async def test_the_index_name_is_checked():
    with pytest.raises(ValueError, match="not the name of an index"):
        dialect().vector_search("x') YIELD node RETURN node //", "$k", "$vector")
    with pytest.raises(ValueError, match="not the name of a variable"):
        dialect().vector_search(NAME, "$k", "$vector", carry=["x, y"])
