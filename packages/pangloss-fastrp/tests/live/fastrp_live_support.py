"""What the live tests of the graph part share: a document of every shape of `pangloss_testing.similar_models` written
and its payloads (`write_shapes`, `transfer`, `described`: from the suite of the parts, `pangloss_testing.parts`),
the graph vectors stored and the oracle's, the indexes of the models and of the vectors made as a project's
migrations would make them, and the plan of a query"""

from typing import Any

import numpy as np
from pangloss_cypher.migrations import apply_changes
from pangloss_models.indexes import model_indexes
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.files import EMPTY_SNAPSHOT
from pangloss_testing.backends import under_test
from pangloss_testing.live import run

# (the suite's, imported from here by the tests of the graph part)
from pangloss_testing.parts import differences, drop_vector_indexes  # noqa: F401
from pangloss_testing.parts.writes import (  # noqa: F401
    NAMES,
    alternatives,
    described,
    meeting,
    ref,
    transfer,
    write_shapes,
)
from pangloss_testing.under_test.database import current
from pangloss_vectors import VectorRow, meta, store, structure
from pangloss_vectors.parts import profiles

from pangloss_fastrp.cypher_reader import load_all
from pangloss_fastrp.maps import graph_maps
from pangloss_fastrp.testing import oracle

# ---------------------------------------------------------------------------
# Vectors
# ---------------------------------------------------------------------------


async def stored(db_driver) -> dict[str, list[float]]:
    """The graph vectors in use, by item"""
    found = await store.states()
    state = found.parts.get("graph")
    if state is None:
        return {}
    return {
        row["of"]: row["vector"]
        for row in run(
            db_driver,
            "MATCH (v:PGVector {part: 'graph', generation: $generation}) RETURN v.of AS of, v.vector AS vector",
            generation=state.generation,
        )
    }


async def fresh_oracle() -> dict[str, np.ndarray]:
    """What a whole rebuild would give now"""
    graph = graph_maps()
    return oracle(await load_all(graph), graph)


async def set_in_use(rows) -> None:
    """The writer of a refresh: the vectors in use, in place"""
    await store.set_vectors("graph", list(rows))


def rows_of(vectors: dict[str, Any], types: dict[str, str]) -> list[VectorRow]:
    return [
        VectorRow(of, types[of], [float(x) for x in vector])
        for of, vector in sorted(vectors.items())
    ]


# ---------------------------------------------------------------------------
# Indexes, as the migrations make them (the database is emptied between tests; its indexes are not)
# ---------------------------------------------------------------------------


async def make_vector_indexes() -> list[str]:
    """The vector index of each profile, and of each profile and group, as the project's migrations would make
    them (`pangloss-vectors`' `vectors_live_support.make_vector_indexes`)"""
    entries = []
    for name, weights in profiles().items():
        if not weights:
            continue
        lay = store.layout(name, weights)
        entries.append(
            structure.vector_entry(lay.index_name, lay.label, lay.dimension, "test")
        )
        for group in meta.groups():
            entries.append(
                structure.vector_entry(
                    lay.group_index_name(group),
                    lay.group_label(group),
                    lay.dimension,
                    "test",
                )
            )
    await apply_changes(
        current(),
        EMPTY_SNAPSHOT,
        [
            c.AddIndex(index={k: v for k, v in entry.items() if k != "app"})
            for entry in entries
        ],
    )
    return [entry["name"] for entry in entries]


async def make_model_indexes(db_driver) -> None:
    """The indexes of the registered models (a label of each class, `PGCitation(target_id)` and the like), as the
    migrations make them; those there already are left"""
    there = existing_indexes(db_driver)
    wanted = [
        entry
        for entry in model_indexes()
        if (entry["label"], tuple(entry["properties"])) not in there
    ]
    if wanted:
        await apply_changes(
            current(), EMPTY_SNAPSHOT, [c.AddIndex(index=entry) for entry in wanted]
        )


def existing_indexes(db_driver) -> set[tuple[str, tuple[str, ...]]]:
    with db_driver.session(database=under_test().database) as session:
        if under_test().name == "neo4j":
            rows = session.run(
                "SHOW INDEXES YIELD labelsOrTypes, properties, entityType "
                "WHERE entityType = 'NODE' RETURN labelsOrTypes AS labels, properties"
            ).data()
            return {
                (row["labels"][0], tuple(row["properties"] or ()))
                for row in rows
                if row["labels"]
            }
        rows = session.run("SHOW INDEX INFO").data()
        found = set()
        for row in rows:
            properties = row.get("property")
            if isinstance(properties, str):
                properties = [properties]
            found.add((row.get("label"), tuple(properties or ())))
        return found


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------


def plan_of(db_driver, query: str, **parameters: Any) -> list[str]:
    """The operators of the plan of a query (`EXPLAIN`), each with what it says of itself, from the top"""
    with db_driver.session(database=under_test().database) as session:
        if under_test().name == "neo4j":
            plan = session.run("EXPLAIN " + query, **parameters).consume().plan
            found: list[str] = []

            def walk(step: dict, depth: int) -> None:
                arguments = step.get("args") or step.get("arguments") or {}
                details = arguments.get("Details", "")
                found.append(
                    f"{'  ' * depth}{step.get('operatorType', step.get('operator_type'))} {details}".rstrip()
                )
                for child in step.get("children", []):
                    walk(child, depth + 1)

            walk(plan, 0)
            return found
        rows = session.run("EXPLAIN " + query, **parameters).data()
        return [list(row.values())[0] for row in rows]


# Operators that read every node, or every node of a label
SCANS = {
    "memgraph": {"ScanAll", "ScanAllByLabel"},
    "neo4j": {"AllNodesScan", "NodeByLabelScan"},
}


def operator(step: str) -> str:
    """The name of a step's operator (Memgraph's `| * Expand (n)-[e]->(m)`, Neo4j's `NodeIndexSeek@neo4j ...`)"""
    words = step.replace("|", " ").replace("*", " ").split()
    return words[0].split("@")[0] if words else ""


def scans_in(plan: list[str]) -> list[str]:
    """The steps of a plan that scan all nodes, or a label"""
    bad = SCANS[under_test().name]
    return [step for step in plan if operator(step) in bad]
