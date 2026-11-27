"""The second graph part, `"actual"` (implementation_docs/spaces-and-comparison-plan.md, step 5.4), on the backend under
test: the suite every part passes (`pangloss_testing.parts.PartSuite`), weighed by a profile, whose slow way reads the
graph as the graph part does, then every node's stored path with a query of its own, and gives each document the
weight `spaces.signature` says of it, walked path by path (not by shapes, as the part); and the part's own claims: a
statement in a "not" has a vector in `graph` and none in `actual`, after a rebuild and in an overlay; one reported
joins at its weight; unweighed, nothing is written."""

import json
from typing import Any, no_type_check

import pytest
from pangloss_models.spaces import registered_grounds, registered_spaces, signature
from pangloss_testing.live import run
from pangloss_testing.parts import PartSuite, differences, one_turn, stored, writes
from pangloss_testing.parts.suite import drop_vector_indexes

from pangloss_fastrp.cypher_reader import load_all
from pangloss_fastrp.maps import graph_maps
from pangloss_fastrp.maths import STOP
from pangloss_fastrp.settings import degree_weights
from pangloss_fastrp.testing import MemoryReader, oracle
from pangloss_fastrp.walk import weight_of

pytestmark = pytest.mark.asyncio(loop_scope="session")

NAME = "actual"
PROFILES = {
    "default": {"graph": 1, "class": 0.1},
    "who_met": {NAME: 1, "class": 0.1},
}

PATHS_QUERY = """
MATCH (n:PGIndexableNode)
OPTIONAL MATCH (h:HeadNode {id: n.head_node_id})
RETURN n.id AS id, n.type AS type, n.head_node_id AS head, h.type AS head_type, PATH AS path
"""


def weights_now(db_driver) -> dict[str, float]:
    """Each document's weight, by the walk of its stored path read now (a head's of its class)"""
    from pangloss_core import backend

    graph = graph_maps()
    documents = {
        t for t, k in graph.kinds.items() if k == STOP and graph.documents.get(t)
    }
    spaces, grounds = registered_spaces(), registered_grounds()
    weights = degree_weights()
    query = PATHS_QUERY.replace(
        "PATH", backend.current().dialect.meta_property("n", "path")
    )
    found = {}
    for row in run(db_driver, query):
        if row["type"] not in documents:
            continue
        path = row["path"]
        path = json.loads(path) if isinstance(path, str) else list(path or [])
        head = row["type"] if row["head"] is None else None
        found[row["id"]] = weight_of(
            signature(path, spaces, grounds, head=head), weights
        )
    return found


async def walked_oracle(db_driver) -> dict[str, Any]:
    """The slow way: the graph read as the graph part reads it, each document weighed by `weights_now`, and the
    whole rebuild of the pure maths"""
    import dataclasses

    graph = graph_maps()
    read = await load_all(graph)
    weights = weights_now(db_driver)
    return oracle(
        MemoryReader(
            [
                dataclasses.replace(n, weight=weights.get(n.id, 1.0))
                for n in read.node.values()
            ],
            [e for edges in read.out.values() for e in edges],
        ),
        graph,
    )


@pytest.fixture
def weighed(settings, monkeypatch):
    """A profile that weighs the second part (`who_met`), beside the default"""
    monkeypatch.setattr(settings, "VECTORS_PROFILES", PROFILES)


@pytest.mark.usefixtures("weighed")
class TestTheActualPart(PartSuite):
    parts = {NAME: walked_oracle}


# ---------------------------------------------------------------------------
# The part's own
# ---------------------------------------------------------------------------


@pytest.fixture
def database(db_driver, clear_database):
    drop_vector_indexes(db_driver)
    yield db_driver
    drop_vector_indexes(db_driver)


@no_type_check
async def built(database, m) -> dict[str, str]:
    from pangloss_vectors.rebuild import rebuild

    ids = await writes.write_shapes(m, database)
    await rebuild()
    await one_turn(database)
    return ids


@no_type_check
async def test_a_statement_in_a_not_has_a_graph_vector_and_no_actual_one(
    database, weighed
):
    from pangloss_testing.similar_models import declare

    m = declare()
    ids = await built(database, m)
    graph, actual = await stored(database, "graph"), await stored(database, NAME)
    assert ids["denied"] in graph
    assert ids["denied"] not in actual
    # (its head and the transfer beside it asserted, in both)
    assert ids["transfer"] in graph and ids["transfer"] in actual
    assert differences(actual, await walked_oracle(database)) == []


@no_type_check
async def test_an_overlay_of_a_statement_in_a_not_gives_it_a_graph_vector_and_no_actual_one(
    database, weighed
):
    from pangloss_cypher.write_functions import to_db_model, write_head_node
    from pangloss_cypher.write_plan import plan_create
    from pangloss_testing.similar_models import declare
    from pangloss_vectors.parts import part

    m = declare()
    ids = await built(database, m)
    people = writes.people(ids, "Ada", "Ben", "Cy")
    instance = to_db_model(
        m.Factoid.Create(
            label="overlaid, half denied",
            statements=[
                {"type": "Negative", "contents": [writes.transfer(people)]},
                {**writes.transfer(people), "label": "Ada gave to Ben, yes"},
            ],
        )
    )
    plan = plan_create(instance)
    denied = str(instance.statements[0].contents[0].id)
    given = {name: await part(name).overlay(plan) for name in ("graph", NAME)}
    assert denied in given["graph"] and denied not in given[NAME]
    await write_head_node(instance)
    await one_turn(database)
    have = await stored(database, NAME)
    assert denied not in have
    assert differences(given[NAME], {of: have[of] for of in given[NAME]}) == []
    assert differences(have, await walked_oracle(database)) == []


@no_type_check
async def test_a_reported_statement_joins_at_its_weight_and_one_reported_not_to_have_been_is_out(
    database, weighed
):
    """(`declare(compared=True)`: `Reported` neither asserts nor denies, its degree "likely"; `Reported[Negative]`
    leans against)"""
    from pangloss_fastrp import maths
    from pangloss_fastrp.cypher_reader import reading
    from pangloss_fastrp.part import walk_of
    from pangloss_testing.similar_models import declare
    from pangloss_vectors.rebuild import rebuild

    m = declare(compared=True)
    ada = await m.Person.Create(label="Ada").save()
    ben = await m.Person.Create(label="Ben").save()
    cy = await m.Person.Create(label="Cy").save()

    def given(label: str, to) -> dict:
        return {
            "type": "Transfer",
            "label": label,
            "given_by": writes.ref(ada),
            "given_to": writes.ref(to),
        }

    made = await m.Factoid.Create(
        label="said",
        statements=[
            {"type": "Reported", "contents": [given("reported", ben)]},
            {
                "type": "Reported",
                "contents": [
                    {"type": "Negative", "contents": [given("reported not", cy)]}
                ],
            },
        ],
    ).save()
    await rebuild()
    await one_turn(database)
    under = {
        row["label"]: row["id"]
        for row in run(
            database,
            "MATCH (n:Transfer {head_node_id: $head}) RETURN n.id AS id, n.label AS label",
            head=str(made.id),
        )
    }
    graph, actual = await stored(database, "graph"), await stored(database, NAME)
    assert under["reported"] in actual and under["reported not"] not in actual
    assert under["reported not"] in graph
    assert differences(actual, await walked_oracle(database)) == []
    maps = graph_maps()
    ada_id, reported = str(ada.id), under["reported"]
    key = tuple(sorted((ada_id, reported)))
    structural = await reading(maps, lambda r: maths.joins(r, maps, [reported]))
    walked = await reading(
        maps,
        lambda r: maths.joins(r, maps, [reported]),
        walk=walk_of(maps, True),
    )
    assert walked[key] == pytest.approx(0.6 * structural[key])


@no_type_check
async def test_unweighed_the_second_part_writes_no_vector_and_its_refresh_none(
    database,
):
    from pangloss_testing.similar_models import declare
    from pangloss_vectors import store

    m = declare()
    ids = await built(database, m)
    assert ids["transfer"] in await stored(database, "graph")
    state = (await store.states()).parts[NAME]
    assert state.count == 0
    assert (
        run(
            database, "MATCH (v:PGVector {part: $part}) RETURN count(v) AS n", part=NAME
        )[0]["n"]
        == 0
    )
    await writes.create(m, ids)
    await one_turn(database)
    assert await stored(database, NAME) == {}
