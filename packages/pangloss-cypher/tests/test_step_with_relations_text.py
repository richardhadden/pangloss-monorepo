"""The text a `through` step compiles to when it asks a relation of the wrapper's own (`InRole.role`;
implementation_docs/relation-steps-plan.md, step 2), with no database: each wrapper of the path is named by an
`UNWIND` in a subquery, and its relation is a pattern from that name"""

from typing import no_type_check

import pytest
from pangloss_models import (
    Document,
    EdgeModel,
    Entity,
    Match,
    ModelRegistry,
    ReifiedRelation,
    ViaEdge,
    initialise,
)
from pangloss_models.search import check_match

BAKER = "0194a1b2-0000-7000-8000-000000000001"


@pytest.fixture
@no_type_check
def doc(monkeypatch):
    import pangloss_cypher.search_query
    from pangloss_memgraph.databases.memgraph.dialect import MemgraphDialect

    dialect = MemgraphDialect()
    monkeypatch.setattr(pangloss_cypher.search_query, "dialect", lambda: dialect)
    ModelRegistry._reset()

    class Certainty(EdgeModel):
        value: int

    class RoleType(Entity):
        pass

    class Person(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        role: RoleType | None = None
        n: int = 0

    class Doc(Document):
        role: list[InRole[ViaEdge[Person, Certainty]]]

    initialise(bind_database=False)
    yield Doc
    ModelRegistry._reset()


def compiled(doc, step) -> tuple[str, dict]:
    from pangloss_cypher.search_query import Compiler

    checked = check_match(doc, Match(where={"role": {"through": [step]}}))
    params: dict = {}
    return Compiler(params).all_of(checked, "n"), params


def test_a_step_with_a_relation_of_the_wrapper_names_each_wrapper_by_an_unwind(doc):
    text, params = compiled(
        doc,
        {
            "type": "InRole",
            "where": {"role": {"is": BAKER}, "n": {"eq": 1}},
            "edge": {"type": "Certainty", "where": {"value": {"gte": 8}}},
        },
    )
    assert (
        "EXISTS { UNWIND range(1, size(nodes(p8)) - 2) AS i9 "
        "WITH nodes(p8)[i9] AS nd10, relationships(p8)[i9] AS ed11 "
        "WHERE $p1 IN labels(nd10) "
        "AND EXISTS { MATCH (nd10)-[e12:`role`]->(w13) WHERE true AND w13.id IN $p2 } "
        "AND nd10.`n` = $p3 AND ed11.`value` >= $p4 RETURN 1 AS found }"
    ) in text
    assert params["p1"] == "InRole" and params["p2"] == [BAKER]
    # (not as a list predicate, as a step of values only is)
    assert "any(nd10 IN [nodes(p8)" not in text

    values_only, _ = compiled(doc, {"type": "InRole", "where": {"n": {"eq": 1}}})
    assert "UNWIND" not in values_only
    assert (
        "any(i9 IN range(1, size(nodes(p8)) - 2) WHERE any(nd10 IN [nodes(p8)[i9]] "
        "WHERE $p1 IN labels(nd10) AND nd10.`n` = $p2))"
    ) in values_only
