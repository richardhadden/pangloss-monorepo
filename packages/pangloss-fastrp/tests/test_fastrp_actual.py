"""The second graph part, `"actual"` (implementation_docs/spaces-and-comparison-plan.md, step 5.4; the rule "by-walk"
of 5.3): what the walk makes of a document's path (`pangloss_fastrp.walk`), the joins that follow on small graphs in
memory, a refresh equal to a rebuild with weighted documents and documents out, `FASTRP_DEGREE_WEIGHTS`, and the part
idle while no profile weighs it. No database."""

import asyncio
import dataclasses
import json
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from pangloss_models.exceptions import PanglossInitialisationError
from pangloss_vectors import Changed, Item

from pangloss_fastrp import maths
from pangloss_fastrp.maps import graph_maps
from pangloss_fastrp.maths import Edge, Node
from pangloss_fastrp.part import ACTUAL_PART, PART
from pangloss_fastrp.settings import DEFAULT_DEGREE_WEIGHTS, degree_weights
from pangloss_fastrp.testing import WORLD_MAPS, MemoryReader, World, oracle
from pangloss_fastrp.walk import Walk, shape_of

CLOSE = 1e-5


def compared() -> Any:
    from pangloss_testing.similar_models import declare

    return declare(compared=True)


def entry(kind: str, type: str, field: str, id: str = "x", **more: str) -> dict:
    return {"kind": kind, "type": type, "id": id, "field": field, **more}


def under_factoid(*spaces: dict, id: str = "f") -> list[dict]:
    """The path of a statement of the factoid `id` held by these entries"""
    return [entry("document", "Factoid", "statements", id), *spaces]


def space(type: str, id: str = "s", **more: str) -> dict:
    return entry("space", type, "contents", id, **more)


def ordered(space_type: str) -> list[dict]:
    """The path of what an order (a statement of a factoid) orders, in the space `space_type`"""
    return under_factoid(
        entry("document", "Order", "thing_ordered", "o"), space(space_type)
    )


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------

CASES = {
    "asserted": (under_factoid(), 1.0),
    "denied": (under_factoid(space("Negative")), 0.0),
    "reported, its class's degree (likely)": (under_factoid(space("Reported")), 0.6),
    "believed, its class's degree (possible)": (
        under_factoid(space("Believed")),
        0.4,
    ),
    "possible, a degree entered (expected)": (
        under_factoid(space("Hypothetical", degree="expected")),
        0.8,
    ),
    "possible, no degree": (under_factoid(space("Hypothetical")), 0.5),
    "reported not to have been: leaning against": (
        under_factoid(space("Reported"), space("Negative")),
        0.0,
    ),
    "it cannot have been: denied": (
        under_factoid(space("Negative"), space("Hypothetical")),
        0.0,
    ),
    "ordered (expected)": (ordered("Ordered"), 0.8),
    "forbidden: leaning against": (ordered("Forbidden"), 0.0),
    "permitted, no degree": (ordered("Permitted"), 0.5),
}


@pytest.mark.parametrize("case", list(CASES))
def test_a_nested_document_weighs_what_the_walk_says_of_its_path(case):
    compared()
    path, weight = CASES[case]
    walk = Walk(graph_maps(), DEFAULT_DEGREE_WEIGHTS)
    assert walk.weight("Transfer", path, "Factoid") == pytest.approx(weight)
    # (the same of the path as JSON text, as Neo4j keeps it)
    again = Walk(graph_maps(), DEFAULT_DEGREE_WEIGHTS)
    assert again.weight("Transfer", json.dumps(path), "Factoid") == pytest.approx(
        weight
    )


def test_a_head_an_entity_and_a_wrapper_weigh_one_whatever_the_path():
    compared()
    walk = Walk(graph_maps(), DEFAULT_DEGREE_WEIGHTS)
    denied = under_factoid(space("Negative"))
    assert walk.weight("Factoid", None) == 1.0
    assert walk.weight("Factoid", []) == 1.0
    assert walk.weight("Person", denied, "Factoid") == 1.0
    assert walk.weight("InRole", denied, "Factoid") == 1.0
    # (nothing was walked: a head whose ground asserts, and what is no document)
    assert walk.shapes == {}


def test_a_path_with_no_space_under_an_asserted_ground_is_not_walked():
    compared()
    walk = Walk(graph_maps(), DEFAULT_DEGREE_WEIGHTS)
    path = under_factoid(entry("reified", "InRole", "target"))
    assert walk.weight("Transfer", path, "Factoid") == 1.0
    assert walk.weight("Transfer", json.dumps(path), "Factoid") == 1.0
    # (the head's class not known: the path's first entry says)
    assert walk.weight("Transfer", path) == 1.0
    assert walk.shapes == {}


def test_the_walk_is_asked_once_for_each_shape_of_path():
    compared()
    walk = Walk(graph_maps(), DEFAULT_DEGREE_WEIGHTS)
    for n in range(20):
        assert walk.weight(
            "Transfer", under_factoid(space("Reported", f"r{n}"), id=f"f{n}")
        ) == pytest.approx(0.6)
        assert walk.weight(
            "Transfer", under_factoid(space("Negative", f"n{n}"), id=f"f{n}")
        ) == pytest.approx(0.0)
    assert len(walk.shapes) == 2
    assert shape_of(under_factoid(space("Reported", "a"))) == shape_of(
        under_factoid(space("Reported", "b"), id="g")
    )


def grounds_with(**changed: dict) -> dict:
    from pangloss_models.spaces import registered_grounds

    return {**registered_grounds(), **changed}


RUMOUR = {
    "veridical": 0,
    "fit": "describes",
    "degree": "possible",
    "by": None,
    "standing": "claim",
}


def test_under_a_head_whose_ground_is_0_the_head_and_what_it_holds_lean_for_at_its_degree():
    compared()
    walk = Walk(
        graph_maps(), DEFAULT_DEGREE_WEIGHTS, grounds=grounds_with(Factoid=RUMOUR)
    )
    assert walk.weight("Factoid", None) == pytest.approx(0.4)
    assert walk.weight("Transfer", under_factoid(), "Factoid") == pytest.approx(0.4)
    # (a "not" under a ground of 0 leans against: out)
    assert walk.weight(
        "Transfer", under_factoid(space("Negative")), "Factoid"
    ) == pytest.approx(0.0)
    # (a ground of 0 with no degree: "none")
    plain = Walk(
        graph_maps(),
        DEFAULT_DEGREE_WEIGHTS,
        grounds=grounds_with(Factoid={**RUMOUR, "degree": None}),
    )
    assert plain.weight("Factoid", None) == pytest.approx(0.5)


def test_the_degree_weights_of_the_settings_are_the_walk_s():
    compared()
    weights = {**DEFAULT_DEGREE_WEIGHTS, "likely": 0.9, "none": 0.0}
    walk = Walk(graph_maps(), weights)
    assert walk.weight("Transfer", under_factoid(space("Reported"))) == 0.9
    assert walk.weight("Transfer", under_factoid(space("Hypothetical"))) == 0.0


# ---------------------------------------------------------------------------
# The joins, on small graphs in memory
# ---------------------------------------------------------------------------


def factoid_graph(walk: Walk | None) -> MemoryReader:
    """A factoid of four transfers from Ann: to Bob asserted, to Cy denied, to Dee reported, to Eve forbidden (in an
    order Ann gave Fay). With `walk`, each node weighed by its path"""
    paths = {
        "f": None,
        "to bob": under_factoid(),
        "no": under_factoid(),
        "to cy": under_factoid(space("Negative", "no")),
        "said": under_factoid(),
        "to dee": under_factoid(space("Reported", "said")),
        "order": under_factoid(),
        "forbade": under_factoid(entry("document", "Order", "thing_ordered", "order")),
        "to eve": ordered("Forbidden"),
    }
    types = {
        "f": "Factoid",
        "no": "Negative",
        "said": "Reported",
        "order": "Order",
        "forbade": "Forbidden",
    }
    nodes = [Node(p, "Person") for p in ("ann", "bob", "cy", "dee", "eve", "fay")]
    for id, path in paths.items():
        node = Node(id, types.get(id, "Transfer"))
        nodes.append(node if walk is None else walk.weighed(node, path, "Factoid"))
    edges = [
        Edge("f", "to bob", "statements"),
        Edge("f", "no", "statements"),
        Edge("no", "to cy", "contents"),
        Edge("f", "said", "statements"),
        Edge("said", "to dee", "contents"),
        Edge("f", "order", "statements"),
        Edge("order", "ann", "ordered_by"),
        Edge("order", "fay", "ordered_to"),
        Edge("order", "forbade", "thing_ordered"),
        Edge("forbade", "to eve", "contents"),
    ]
    for statement, to in (
        ("to bob", "bob"),
        ("to cy", "cy"),
        ("to dee", "dee"),
        ("to eve", "eve"),
    ):
        edges += [
            Edge(statement, "ann", "given_by"),
            Edge(statement, to, "given_to"),
        ]
    return MemoryReader(nodes, edges)


def test_denied_and_leaning_against_are_out_leaning_for_joins_at_its_weight_and_asserted_as_before():
    compared()
    graph = graph_maps()
    structural = maths.joins(factoid_graph(None), graph)
    actual = maths.joins(factoid_graph(Walk(graph, DEFAULT_DEGREE_WEIGHTS)), graph)
    for key, weight in structural.items():
        if {"to cy", "to eve"} & set(key):
            assert key not in actual, key
        elif "to dee" in key:
            assert actual[key] == pytest.approx(0.6 * weight), key
        else:
            assert actual[key] == pytest.approx(weight), key
    # (what is out was joined in the structural network: to its factoid and its people)
    assert ("cy", "to cy") in structural and ("eve", "to eve") in structural
    assert set(actual) < set(structural)
    # (and has no vector; what is reported has one)
    vectors = oracle(factoid_graph(Walk(graph, DEFAULT_DEGREE_WEIGHTS)), graph)
    assert "to cy" not in vectors and "to eve" not in vectors
    assert {"to bob", "to dee", "order", "f"} <= set(vectors)
    # (an order forbidden and kept: the order still ties the giver and the receiver, by the order itself)
    assert ("ann", "order") in actual and ("fay", "order") in actual


def test_a_head_whose_class_has_a_ground_of_0_joins_at_its_weight_and_its_statements_too():
    compared()
    graph = graph_maps()
    structural = maths.joins(factoid_graph(None), graph)
    walk = Walk(graph, DEFAULT_DEGREE_WEIGHTS, grounds=grounds_with(Factoid=RUMOUR))
    actual = maths.joins(factoid_graph(walk), graph)
    # (the factoid and its asserted statement at 0.4 each; the join between them is the statement's, 0.4)
    assert actual[("f", "to bob")] == pytest.approx(0.4 * structural[("f", "to bob")])
    assert actual[("ann", "to bob")] == pytest.approx(
        0.4 * structural[("ann", "to bob")]
    )
    # (reported under a ground of 0: leaning for at the degree of the innermost space that leaves it neither)
    assert actual[("ann", "to dee")] == pytest.approx(
        0.6 * structural[("ann", "to dee")]
    )
    assert not any("to cy" in key for key in actual)


def test_a_node_of_weight_0_is_out_of_the_graph_and_one_of_weight_1_as_it_was():
    graph = MemoryReader(
        [Node("d", "Event"), Node("ann", "Person"), Node("out", "Event", weight=0.0)],
        [Edge("d", "ann", "by"), Edge("out", "ann", "by")],
    )
    assert not WORLD_MAPS.is_in(graph.node["out"])
    assert maths.joins(graph, WORLD_MAPS) == {("ann", "d"): pytest.approx(1.0)}


# ---------------------------------------------------------------------------
# A refresh equals a rebuild, with weights
# ---------------------------------------------------------------------------


def changed_between(before: dict, after: dict) -> set[str]:
    return {
        i
        for key in set(before) | set(after)
        if before.get(key) != after.get(key)
        for i in key
    }


def assert_same(found: dict, wanted: dict, said: str) -> None:
    assert set(found) == set(wanted), f"{said}: {sorted(set(found) ^ set(wanted))[:5]}"
    for id, vector in wanted.items():
        gap = float(np.abs(found[id] - vector).max())
        assert gap < CLOSE, f"{said}: {id} differs by {gap}"


def test_a_weighted_world_has_documents_out_and_at_a_weight_and_an_unweighted_one_is_as_before():
    weighted = World(1, weighted=True)
    weights = {n.weight for n in weighted.graph.node.values()}
    assert {0.0, 1.0} < weights and len(weights) > 3
    plain, again = World(1), World(1)
    assert {n.weight for n in plain.graph.node.values()} == {1.0}
    assert [repr(n) for n in plain.graph.node.values()] == [
        repr(n) for n in again.graph.node.values()
    ]


@pytest.mark.parametrize("seed", range(4))
def test_a_refresh_after_any_edit_of_a_weighted_world_equals_a_rebuild(seed):
    world = World(seed, weighted=True)
    vectors = oracle(world.graph, WORLD_MAPS)
    joins = maths.joins(world.graph, WORLD_MAPS)
    edits = []
    for round in range(30):
        edit = world.edit()
        edits.append(edit.split()[0])
        after = maths.joins(world.graph, WORLD_MAPS)
        made = maths.refresh(world.graph, WORLD_MAPS, changed_between(joins, after))
        for id in made.gone:
            vectors.pop(id, None)
        vectors.update(made.vectors)
        assert_same(
            vectors,
            oracle(world.graph, WORLD_MAPS),
            f"seed {seed}, round {round}, {edit}",
        )
        joins = after
    assert "reweigh" in edits


@pytest.mark.parametrize("groups", [2, 5])
@pytest.mark.parametrize("seed", range(2))
def test_a_batch_of_a_weighted_world_refreshed_in_groups_equals_a_rebuild(seed, groups):
    """(as `test_fastrp_exactness`'s, the units of each batch divided into groups, shuffled)"""
    from test_fastrp_exactness import (
        WithBelow,
        divided,
        heads_as_they_stand,
        units_of_a_batch,
    )

    from pangloss_fastrp.part import BEFORE, changed_stops

    world = World(seed + 100 * groups, weighted=True)
    reader = WithBelow(world)
    vectors = oracle(world.graph, WORLD_MAPS)
    joins = maths.joins(world.graph, WORLD_MAPS)
    for round in range(10):
        was = heads_as_they_stand(world)
        edits = [world.edit() for _ in range(world.random.randint(1, 4))]
        after = maths.joins(world.graph, WORLD_MAPS)
        units = units_of_a_batch(world, was, joins)
        said = f"seed {seed}, {groups} groups, round {round}, {edits}"
        centres = [
            changed_stops(
                reader,
                WORLD_MAPS,
                [u.id for u in group if u.kind != BEFORE],
                [u.id for u in group if u.kind == BEFORE],
            )
            for group in divided(units, groups, "shuffled", world.random)
            if group
        ]
        assert changed_between(joins, after) <= set().union(*centres), said
        for centre in centres:
            made = maths.refresh(world.graph, WORLD_MAPS, centre)
            for id in made.gone:
                vectors.pop(id, None)
            vectors.update(made.vectors)
        assert_same(vectors, oracle(world.graph, WORLD_MAPS), said)
        joins = after


@pytest.mark.parametrize("seed", range(4))
def test_an_overlay_of_a_weighted_world_equals_the_same_nodes_written(seed):
    world = World(seed, people=150, documents=150, weighted=True)
    before, known = world.graph.copy(), set(world.graph.node)
    for _ in range(5):
        document = world.document(published=True)
        nodes = [n for i, n in world.graph.node.items() if i not in known]
        edges = [e for n in nodes for e in world.graph.out.get(n.id, [])]
        found = maths.overlay(before, WORLD_MAPS, nodes, edges)
        wanted = oracle(world.graph, WORLD_MAPS)
        stops = [n.id for n in nodes if WORLD_MAPS.is_in(n)]
        assert_same(
            found,
            {i: wanted[i] for i in stops if i in wanted},
            f"seed {seed}, overlay of {document}",
        )
        before, known = world.graph.copy(), set(world.graph.node)


# ---------------------------------------------------------------------------
# The setting
# ---------------------------------------------------------------------------


def test_the_degree_weights_default_to_the_first_guess_with_every_step_named():
    from pangloss_models import DEGREE_STEPS

    assert degree_weights(SimpleNamespace()) == DEFAULT_DEGREE_WEIGHTS
    assert set(DEFAULT_DEGREE_WEIGHTS) == {*DEGREE_STEPS, "none"}
    given = {**DEFAULT_DEGREE_WEIGHTS, "likely": 1, "possible": 0}
    assert degree_weights(SimpleNamespace(FASTRP_DEGREE_WEIGHTS=given)) == {
        k: float(v) for k, v in given.items()
    }


@pytest.mark.parametrize(
    "value, said",
    [
        ({k: v for k, v in DEFAULT_DEGREE_WEIGHTS.items() if k != "none"}, "leaves out 'none'"),
        ({**DEFAULT_DEGREE_WEIGHTS, "certain": 1.0}, "names 'certain', which is no degree"),
        ({**DEFAULT_DEGREE_WEIGHTS, "likely": 1.5}, "not"),
        ({**DEFAULT_DEGREE_WEIGHTS, "likely": -0.1}, "not"),
        ({**DEFAULT_DEGREE_WEIGHTS, "likely": True}, "not"),
        ({**DEFAULT_DEGREE_WEIGHTS, "likely": "0.6"}, "not"),
        ([0.8, 0.6], "not"),
    ],
)  # fmt: skip
def test_degree_weights_that_do_not_name_every_step_with_a_number_from_0_to_1_are_refused(
    value, said
):
    with pytest.raises(
        PanglossInitialisationError,
        match="FASTRP_DEGREE_WEIGHTS is a weight from 0 to 1",
    ) as raised:
        degree_weights(SimpleNamespace(FASTRP_DEGREE_WEIGHTS=value))
    assert said in str(raised.value)


def test_bad_degree_weights_are_refused_at_initialise_when_the_app_is_installed(
    project_settings,
):
    import pangloss_core.settings as core_settings

    # (the tests' apps; not imported from the conftest, whose name another conftest of the package shares)
    apps = list(core_settings.SETTINGS.INSTALLED_APPS)
    bad = {**DEFAULT_DEGREE_WEIGHTS, "likely": 2}
    project_settings(FASTRP_DEGREE_WEIGHTS=bad)
    compared()
    project_settings(
        INSTALLED_APPS=[*apps, "pangloss_fastrp"], FASTRP_DEGREE_WEIGHTS=bad
    )
    with pytest.raises(PanglossInitialisationError, match="FASTRP_DEGREE_WEIGHTS"):
        compared()


# ---------------------------------------------------------------------------
# Idle unless weighed
# ---------------------------------------------------------------------------

WHO_MET = {"who_met": {"actual": 1, "class": 0.1}}


def test_no_profile_weighs_the_second_part_unless_the_settings_say_so(project_settings):
    from pangloss_vectors.parts import profiles

    compared()
    assert "actual" not in profiles()["default"]
    assert ACTUAL_PART.idle() and not PART.idle()
    project_settings(VECTORS_PROFILES=WHO_MET)
    assert not ACTUAL_PART.idle()


def test_unweighed_the_second_part_reads_and_writes_nothing():
    """(with no database: a read would fail)"""
    compared()
    written: list = []

    async def write(rows) -> None:
        written.extend(rows)

    async def everything() -> tuple:
        return (
            await ACTUAL_PART.rebuild(write),
            await ACTUAL_PART.refresh(
                Changed(written=(Item("a", "Factoid"),), removed=("b",), before=("c",)),
                write,
            ),
            await ACTUAL_PART.overlay(object()),
            await ACTUAL_PART.unknown(object(), []),
        )

    rebuilt, refreshed, overlaid, unknown = asyncio.run(everything())
    assert (rebuilt, refreshed.written, refreshed.stale, overlaid, unknown) == (
        0,
        0,
        0,
        {},
        {},
    )
    assert written == []


def test_the_second_part_s_signature_changes_when_a_profile_first_weighs_it_and_with_what_the_walk_reads(
    project_settings,
):
    compared()
    idle = ACTUAL_PART.signature()
    assert ACTUAL_PART.signature() == idle
    project_settings(VECTORS_PROFILES=WHO_MET)
    weighed = ACTUAL_PART.signature()
    assert weighed != idle
    project_settings(
        VECTORS_PROFILES=WHO_MET,
        FASTRP_DEGREE_WEIGHTS={**DEFAULT_DEGREE_WEIGHTS, "likely": 0.7},
    )
    assert ACTUAL_PART.signature() not in (idle, weighed)
    # (and the models' spaces: without the compared models' spaces, another)
    project_settings(VECTORS_PROFILES=WHO_MET)
    from pangloss_testing.similar_models import declare

    declare()
    assert ACTUAL_PART.signature() != weighed
    # (the graph part's is the maps' alone, weighed or not)
    from pangloss_fastrp.maps import signature

    assert PART.signature() == signature()


def test_the_second_part_has_its_own_name_and_weight_0_and_the_graph_part_is_as_it_was():
    from pangloss_vectors.parts import parts

    registered = parts()
    assert registered["actual"] is ACTUAL_PART and registered["graph"] is PART
    assert (ACTUAL_PART.weight, PART.weight) == (0.0, 1.0)
    assert (ACTUAL_PART.walked, PART.walked) == (True, False)
    assert dataclasses.fields(Node)[-1].name == "weight"
