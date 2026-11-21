"""The graph part without a database (implementation_docs/similarity-build-plan.md, step 3.3): what it is, its cap,
what a write plan is laid out as for an overlay, and that numpy waits until it is wanted"""

import subprocess
import sys
import uuid
from types import SimpleNamespace
from typing import no_type_check

import pytest
from pangloss_cypher.write_functions import to_db_model
from pangloss_cypher.write_plan import plan_create
from pangloss_fastrp.maps import graph_maps
from pangloss_fastrp.maths import Edge, Node
from pangloss_fastrp.memory import MemoryReader
from pangloss_fastrp.part import PART, _AsIfIn, laid_out
from pangloss_fastrp.settings import refresh_cap
from pangloss_models.exceptions import PanglossInitialisationError
from pangloss_testing.similar_models import declare
from pangloss_vectors.parts import part


def test_the_part_is_registered_as_graph_and_refreshes_after_a_write():
    assert part("graph") is PART
    assert (PART.name, PART.local, PART.requires, PART.weight) == (
        "graph",
        True,
        frozenset(),
        1.0,
    )


def test_its_dimension_and_signature_are_those_of_the_settings_and_the_maps():
    declare()
    assert PART.dimension() == 128
    from pangloss_fastrp.maps import signature

    assert PART.signature() == signature()


def test_the_cap_of_a_refresh_is_50_000_nodes_unless_the_settings_say():
    assert refresh_cap(SimpleNamespace()) == 50_000
    assert refresh_cap(SimpleNamespace(FASTRP_REFRESH_CAP=10)) == 10


@pytest.mark.parametrize("value", [0, -1, 2.5, True, "100"])
def test_a_cap_that_is_not_a_whole_number_of_1_or_more_is_refused(value):
    with pytest.raises(
        PanglossInitialisationError, match="FASTRP_REFRESH_CAP is a whole number"
    ):
        refresh_cap(SimpleNamespace(FASTRP_REFRESH_CAP=value))


def test_numpy_is_not_imported_with_the_package():
    found = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, pangloss_fastrp, pangloss_fastrp.part; print('numpy' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert found.stdout.strip() == "False"


def test_a_reader_as_if_in_gives_its_nodes_in_and_the_others_as_they_are():
    base = MemoryReader(
        [
            Node("a", "Factoid", deleted=True, published=False),
            Node("b", "Person", merged_into="c"),
            Node("c", "Person", deleted=True),
        ],
        [Edge("a", "b", "of")],
    )
    found = {n.id: n for n in _AsIfIn(base, ["a", "b"]).nodes(["a", "b", "c"])}
    assert found["a"] == Node("a", "Factoid")
    assert found["b"] == Node("b", "Person")
    assert found["c"] == Node("c", "Person", deleted=True)
    assert list(_AsIfIn(base, ["a"]).out_edges(["a"])) == [Edge("a", "b", "of")]


@no_type_check
def test_a_plan_is_laid_out_as_its_nodes_and_the_forward_edges_of_each_name_of_a_relation():
    m = declare()
    ada, dee, york, cited = (str(uuid.uuid4()) for _ in range(4))
    instance = to_db_model(
        m.Factoid.Create(
            label="a meeting",
            statements=[
                {
                    "type": "Activity",
                    "label": "Ada met Dee",
                    "carried_out_by": {"type": "Person", "id": ada},
                    "participants": [
                        {
                            "type": "InRole",
                            "role": "guest",
                            "at": {"type": "Place", "id": york},
                            "target": [{"type": "Person", "id": dee}],
                        }
                    ],
                },
                {
                    "type": "Inference",
                    "label": "so",
                    "evidence": [{"type": "Transfer", "id": cited}],
                },
                {
                    "type": "Transfer",
                    "label": "someone gave to Ada",
                    "given_by": {
                        "type": "MatchesCriteria",
                        "criteria": {"type": "Person", "where": {}},
                    },
                    "given_to": {"type": "Person", "id": ada},
                },
            ],
        )
    )
    graph = graph_maps()
    nodes, edges = laid_out(plan_create(instance), {}, {}, False, graph.citations)
    by_type = {}
    for node in nodes:
        by_type.setdefault(node.type, []).append(node)
    activity, inference, transfer = (str(s.id) for s in instance.statements)
    [role] = by_type["InRole"]
    [citation] = by_type["PGCitation"]
    [described] = by_type["MatchesCriteria"]
    # (every node of the document takes the head's `published`)
    assert {n.published for n in nodes} == {False}
    assert citation.cites == cited
    found = {(e.source, e.target, e.field) for e in edges}
    assert {
        (str(instance.id), activity, "statements"),
        (activity, ada, "carried_out_by"),
        # (the parent field it subclasses: an edge of each name)
        (activity, ada, "involves"),
        (activity, role.id, "participants"),
        (role.id, dee, "target"),
        (role.id, york, "at"),
        (inference, citation.id, "evidence"),
        (transfer, described.id, "given_by"),
        (transfer, ada, "given_to"),
    } <= found
    # (a description has no candidates until its worker has run)
    assert not [e for e in edges if e.source == described.id]
