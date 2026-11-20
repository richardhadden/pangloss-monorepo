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
        "AND nd10.`n` = $p3 AND (ed11.pg_edge_model = $p4 AND ed11.`value` >= $p5) RETURN 1 AS found }"
    ) in text
    assert params["p1"] == "InRole" and params["p2"] == [BAKER]
    # (the edge onwards is of the edge model, as well as having its values)
    assert params["p4"] == "Certainty"
    # (not as a list predicate, as a step of values only is)
    assert "any(nd10 IN [nodes(p8)" not in text

    values_only, _ = compiled(doc, {"type": "InRole", "where": {"n": {"eq": 1}}})
    assert "UNWIND" not in values_only
    assert (
        "any(i9 IN range(1, size(nodes(p8)) - 2) WHERE any(nd10 IN [nodes(p8)[i9]] "
        "WHERE $p1 IN labels(nd10) AND nd10.`n` = $p2))"
    ) in values_only


def via(doc, *items, backwards=False) -> str:
    from pangloss_cypher.search_query import Compiler

    (condition,) = check_match(doc, Match(where={"role": {"via": list(items)}}))
    return Compiler({}).way_test(condition.via, "p", backwards)


SURE = {"type": "Certainty", "where": {"value": {"gte": 8}}}


def test_a_via_is_list_predicates_inside_one_another_each_from_the_place_before(doc):
    """(relation-steps step 4: a wrapper item starts at 1, and the edge after wrapper `i` at edge `i`)"""
    text = via(doc, {"type": "InRole", "where": {"n": {"eq": 1}}}, SURE)
    assert text == (
        "any(i1 IN range(1, size(nodes(p)) - 2) WHERE any(nd3 IN [nodes(p)[i1]] "
        "WHERE $p2 IN labels(nd3) AND nd3.`n` = $p3) "
        "AND any(i2 IN range(i1, size(nodes(p)) - 2) WHERE any(ed4 IN [relationships(p)[i2]] "
        "WHERE (ed4.pg_edge_model = $p0 AND ed4.`value` >= $p1))))"
    )
    # (an edge item starts at the field's own edge; what comes after an edge is one further on)
    text = via(doc, SURE, {"type": "InRole"})
    assert text.startswith("any(i1 IN range(0, size(nodes(p)) - 2) WHERE ")
    assert "any(i2 IN range(i1 + 1, size(nodes(p)) - 2) WHERE " in text
    # (written from what the relation is to, the places are counted from the other end)
    text = via(doc, {"type": "InRole"}, SURE, backwards=True)
    assert "[nodes(p)[size(nodes(p)) - 1 - i1]]" in text
    assert "[relationships(p)[size(nodes(p)) - 2 - i2]]" in text


def test_a_via_with_a_relation_of_a_wrapper_names_its_places_by_unwind(doc):
    text = via(doc, {"type": "InRole", "where": {"role": {"is": BAKER}}}, SURE)
    assert text == (
        "EXISTS { UNWIND range(1, size(nodes(p)) - 2) AS i1 UNWIND range(i1, size(nodes(p)) - 2) AS i2 "
        "WITH nodes(p)[i1] AS nd3, relationships(p)[i2] AS ed4 "
        "WHERE $p0 IN labels(nd3) AND EXISTS { MATCH (nd3)-[e5:`role`]->(w6) WHERE true AND w6.id IN $p1 } "
        "AND (ed4.pg_edge_model = $p2 AND ed4.`value` >= $p3) RETURN 1 AS found }"
    )
