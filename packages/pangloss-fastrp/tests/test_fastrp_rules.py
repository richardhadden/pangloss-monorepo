"""Each rule of the joined graph on its own (implementation_docs/graph-embeddings.md, "The joined graph, as now
proposed", and "Weighting by the type of document"; implementation_docs/similarity-build-plan.md, step 3.2), on
small graphs in memory, with the joins each should give written out from the rules. No database."""

import dataclasses

import pytest

from pangloss_fastrp import maths
from pangloss_fastrp.maths import Edge, GraphMaps, Node
from pangloss_fastrp.testing import MemoryReader

# The shapes of `pangloss_testing.similar_models`, as `pangloss_fastrp.maps` gives them
MAPS = GraphMaps(
    kinds={
        "Factoid": "stop",
        "Transfer": "stop",
        "Activity": "stop",
        "Inference": "stop",
        "Person": "stop",
        "Place": "stop",
        "DerivedFactoid": "out",
        "InRole": "through",
        "Sworn": "through",
        "Identification": "through",
        "WeightedAlternative": "through",
        "MatchesCriteria": "through",
        "SameEntity": "through",
        "Negative": "end",
    },
    held={
        "InRole": ["target"],
        "Sworn": ["target"],
        "Identification": ["target"],
        "WeightedAlternative": ["alternatives"],
        "MatchesCriteria": ["target"],
        "SameEntity": ["target"],
        "Negative": ["contents"],
    },
    shares={"WeightedAlternative.alternatives": ["percent", 100]},
    citations={"PGCitation": True, "PGUnprotectedCitation": True},
    documents={"Factoid": True, "Transfer": True, "Activity": True, "Inference": True},
    dimension=16,
)


def with_rules(**changes) -> GraphMaps:
    return dataclasses.replace(MAPS, **changes)


def graph(nodes: list[Node], edges: list[tuple]) -> MemoryReader:
    """Edges as `(source, target, field)` or `(source, target, field, {properties})`"""
    return MemoryReader(
        nodes, [Edge(e[0], e[1], e[2], e[3] if len(e) > 3 else {}) for e in edges]
    )


def joins(reader: MemoryReader, maps: GraphMaps = MAPS, starts=None) -> dict:
    return {
        key: pytest.approx(weight)
        for key, weight in maths.joins(reader, maps, starts).items()
    }


def people(*names: str) -> list[Node]:
    return [Node(name, "Person") for name in names]


# -- 3. wrappers are hopped over, to any depth: a chain is one join ---------------------------------------------------


def chain(depth: int) -> MemoryReader:
    """A factoid with a transfer from ada to ben, ben through `depth` wrappers (InRole, Identification, then an
    alternative of one at 100%)"""
    nodes = [
        Node("factoid", "Factoid"),
        Node("transfer", "Transfer"),
        *people("ada", "ben"),
    ]
    edges: list[tuple] = [
        ("factoid", "transfer", "statements"),
        ("transfer", "ada", "given_by"),
    ]
    source, field = "transfer", "given_to"
    for wrapper in ["InRole", "Identification", "WeightedAlternative"][:depth]:
        nodes.append(Node(wrapper.lower(), wrapper))
        edges.append((source, wrapper.lower(), field))
        source = wrapper.lower()
        field = "alternatives" if wrapper == "WeightedAlternative" else "target"
    edges.append((source, "ben", field, {"percent": 100} if depth == 3 else {}))
    return graph(nodes, edges)


@pytest.mark.parametrize("depth", [0, 1, 2, 3])
def test_the_joins_are_the_same_for_0_to_3_wrappers(depth):
    assert joins(chain(depth)) == {
        ("factoid", "transfer"): 1,
        ("ada", "transfer"): 1,
        ("ben", "transfer"): 1,
    }


# -- 4. the share of each edge of a `SumsTo` field --------------------------------------------------------------------


def test_the_alternatives_of_a_weighted_alternative_count_their_shares():
    reader = graph(
        [
            Node("transfer", "Transfer"),
            Node("identification", "Identification"),
            Node("alternative", "WeightedAlternative"),
            *people("ada", "ben", "cy"),
        ],
        [
            ("transfer", "ada", "given_by"),
            ("transfer", "identification", "given_to"),
            ("identification", "alternative", "target"),
            (
                "alternative",
                "ben",
                "alternatives",
                {"percent": 70, "pg_edge_model": "Likelihood"},
            ),
            (
                "alternative",
                "cy",
                "alternatives",
                {"percent": 30, "pg_edge_model": "Likelihood"},
            ),
        ],
    )
    # (the two alternatives are not joined to each other: neither is a stop a chain starts from)
    assert joins(reader) == {
        ("ada", "transfer"): 1,
        ("ben", "transfer"): 0.7,
        ("cy", "transfer"): 0.3,
    }


# -- 4. a computed field's edges at one over their number ------------------------------------------------------------


def candidates() -> MemoryReader:
    return graph(
        [
            Node("transfer", "Transfer"),
            Node("criteria", "MatchesCriteria"),
            *people("ada", "fay", "gus", "hal"),
        ],
        [
            ("transfer", "ada", "given_to"),
            ("transfer", "criteria", "given_by"),
            ("criteria", "fay", "target", {"computed": True}),
            ("criteria", "gus", "target", {"computed": True}),
            ("criteria", "hal", "target", {"computed": True, "seen_by": "logged_in"}),
        ],
    )


def test_the_candidates_of_a_computed_field_share_one_weight_among_those_everyone_may_see():
    assert joins(candidates()) == {
        ("ada", "transfer"): 1,
        ("fay", "transfer"): 0.5,
        ("gus", "transfer"): 0.5,
    }


def test_the_candidates_of_a_computed_field_share_one_weight_among_all_when_the_graph_sees_what_a_logged_in_reader_does():
    assert joins(candidates(), with_rules(sees="logged_in")) == {
        ("ada", "transfer"): 1,
        ("fay", "transfer"): 1 / 3,
        ("gus", "transfer"): 1 / 3,
        ("hal", "transfer"): 1 / 3,
    }


# -- 6. one join for each pair of ends, at the largest weight of the ways between them --------------------------------


def test_a_field_that_narrows_a_parent_s_gives_one_join_at_the_larger_weight():
    reader = graph(
        [Node("activity", "Activity"), *people("ada")],
        [
            ("activity", "ada", "carried_out_by"),
            ("activity", "ada", "involves"),
        ],
    )
    maps = with_rules(
        field_weight={"Activity.carried_out_by": 0.4, "Activity.involves": 0.8}
    )
    assert joins(reader, maps) == {("activity", "ada"): 0.8}


def test_two_ways_through_different_wrappers_give_one_join_at_the_larger_weight():
    reader = graph(
        [
            Node("activity", "Activity"),
            Node("role", "InRole"),
            Node("sworn", "Sworn"),
            *people("dee"),
        ],
        [
            ("activity", "role", "participants"),
            ("activity", "sworn", "participants"),
            ("role", "dee", "target"),
            ("sworn", "dee", "target"),
        ],
    )
    maps = with_rules(class_weight={"InRole": 0.3, "Sworn": 0.5})
    assert joins(reader, maps) == {("activity", "dee"): 0.5}


# -- 5. a wrapper's own relations ------------------------------------------------------------------------------------


def in_role_at() -> MemoryReader:
    return graph(
        [
            Node("activity", "Activity"),
            Node("role", "InRole"),
            *people("dee"),
            Node("york", "Place"),
        ],
        [
            ("activity", "role", "participants"),
            ("role", "dee", "target"),
            ("role", "york", "at"),
        ],
    )


def test_a_wrapper_s_own_relation_is_joined_to_the_stop_the_chain_started_from_at_its_field_s_weight():
    maps = with_rules(field_weight={"InRole.at": 0.7})
    # (not to the person it holds)
    assert joins(in_role_at(), maps) == {
        ("activity", "dee"): 1,
        ("activity", "york"): 0.7,
    }


def test_a_wrapper_s_own_relation_is_not_joined_with_own_false():
    maps = with_rules(own={"InRole": False})
    assert joins(in_role_at(), maps) == {("activity", "dee"): 1}


# -- 7. a stop ends the chain with no join ---------------------------------------------------------------------------


def test_a_stop_ends_the_chain_with_no_join():
    reader = graph(
        [
            Node("factoid", "Factoid"),
            Node("negative", "Negative"),
            Node("denied", "Transfer"),
            Node("said", "Transfer"),
            *people("ada", "ben"),
        ],
        [
            ("factoid", "negative", "statements"),
            ("negative", "denied", "contents"),
            ("factoid", "said", "statements"),
            ("denied", "ada", "given_by"),
            ("said", "ben", "given_by"),
        ],
    )
    # (what is inside the space is still a document with joins of its own; the factoid is not joined to it)
    assert joins(reader) == {
        ("factoid", "said"): 1,
        ("ben", "said"): 1,
        ("ada", "denied"): 1,
    }


# -- 2. forward edges only: not reverse, not derived ------------------------------------------------------------------


def test_reverse_and_derived_edges_and_the_nodes_of_derived_edges_are_not_followed():
    reader = graph(
        [
            Node("transfer", "Transfer"),
            Node("same_group", "SameGroup"),
            *people("ada", "ben", "cy"),
        ],
        [
            ("transfer", "ada", "given_by"),
            # (a reverse edge with no forward edge beside it, as a reader should never give)
            ("ben", "transfer", "given_to_reverse", {"reverse": True}),
            # (a shortcut of a derived edge, and the node of the derived edge, which points at its people)
            ("ada", "cy", "SameGroup", {"derived": True}),
            ("same_group", "ada", "first"),
            ("same_group", "cy", "second"),
        ],
    )
    assert joins(reader) == {("ada", "transfer"): 1}
    assert joins(reader, starts=["ada"]) == {("ada", "transfer"): 1}


# -- 8. a citation joins the citing document to the cited one ---------------------------------------------------------


def citation() -> MemoryReader:
    return graph(
        [
            Node("factoid", "Factoid"),
            Node("inference", "Inference"),
            Node("citation", "PGCitation", cites="cited"),
            Node("other", "Factoid"),
            Node("cited", "Transfer"),
            *people("ada"),
        ],
        [
            ("factoid", "inference", "statements"),
            ("inference", "citation", "evidence"),
            ("other", "cited", "statements"),
            ("cited", "ada", "given_by"),
        ],
    )


def test_a_citation_joins_the_citing_document_to_the_cited_one():
    assert joins(citation()) == {
        ("factoid", "inference"): 1,
        ("cited", "inference"): 1,
        ("cited", "other"): 1,
        ("ada", "cited"): 1,
    }


def test_a_citation_is_found_from_the_cited_end():
    found = joins(citation(), starts=["cited"])
    assert found == {
        ("cited", "inference"): 1,
        ("cited", "other"): 1,
        ("ada", "cited"): 1,
    }


def test_a_citation_is_found_from_the_citing_end():
    assert joins(citation(), starts=["inference"]) == {
        ("factoid", "inference"): 1,
        ("cited", "inference"): 1,
    }


def test_an_unprotected_citation_joins_as_a_citation_does():
    reader = graph(
        [
            Node("inference", "Inference"),
            Node("citation", "PGUnprotectedCitation", cites="cited"),
            Node("cited", "Transfer"),
        ],
        [("inference", "citation", "evidence")],
    )
    assert joins(reader) == {("cited", "inference"): 1}


# -- 1. deleted and merged nodes are out -------------------------------------------------------------------------------


def test_deleted_and_merged_nodes_are_out():
    reader = graph(
        [
            Node("factoid", "Factoid"),
            Node("transfer", "Transfer"),
            Node("ada", "Person", deleted=True),
            Node("ben", "Person", merged_into="cy"),
            Node("cy", "Person"),
            Node("gone", "Factoid", deleted=True),
            Node("gone_transfer", "Transfer", deleted=True),
        ],
        [
            ("factoid", "transfer", "statements"),
            ("transfer", "ada", "given_by"),
            ("transfer", "ben", "given_to"),
            ("gone", "gone_transfer", "statements"),
            ("gone_transfer", "cy", "given_by"),
        ],
    )
    assert joins(reader) == {("factoid", "transfer"): 1}
    assert joins(reader, starts=["ada", "ben", "gone"]) == {}


# -- 1. an unpublished document, by `sees` ---------------------------------------------------------------------------


def unpublished() -> MemoryReader:
    return graph(
        [
            Node("factoid", "Factoid", published=False),
            Node("transfer", "Transfer", published=False),
            Node("role", "InRole", published=False),
            *people("ada", "ben"),
        ],
        [
            ("factoid", "transfer", "statements"),
            ("transfer", "ada", "given_by"),
            ("transfer", "role", "given_to"),
            ("role", "ben", "target"),
        ],
    )


def test_an_unpublished_document_is_out_when_the_graph_sees_what_everyone_does():
    assert joins(unpublished()) == {}


def test_an_unpublished_document_is_in_when_the_graph_sees_what_a_logged_in_reader_does():
    assert joins(unpublished(), with_rules(sees="logged_in")) == {
        ("factoid", "transfer"): 1,
        ("ada", "transfer"): 1,
        ("ben", "transfer"): 1,
    }


# -- a nested document, and the weight of a document's class -----------------------------------------------------------


def nested() -> MemoryReader:
    return graph(
        [Node("factoid", "Factoid"), Node("transfer", "Transfer"), *people("ada")],
        [
            ("factoid", "transfer", "statements"),
            ("transfer", "ada", "given_by"),
        ],
    )


def test_a_nested_document_is_joined_to_the_one_it_is_in():
    assert joins(nested()) == {("factoid", "transfer"): 1, ("ada", "transfer"): 1}


def test_a_nested_document_joins_its_entities_at_its_own_class_s_weight_not_the_one_it_is_in():
    maps = with_rules(class_weight={"Factoid": 2.0, "Transfer": 0.5})
    assert joins(nested(), maps)[("ada", "transfer")] == 0.5


def test_the_join_of_a_nested_document_to_the_one_it_is_in_takes_the_nested_document_s_weight():
    maps = with_rules(class_weight={"Factoid": 2.0, "Transfer": 0.5})
    assert joins(nested(), maps)[("factoid", "transfer")] == 0.5


def test_class_and_field_weights_and_shares_multiply_along_a_chain():
    reader = graph(
        [
            Node("transfer", "Transfer"),
            Node("identification", "Identification"),
            Node("alternative", "WeightedAlternative"),
            Node("activity", "Activity"),
            Node("role", "InRole"),
            *people("ben", "dee"),
            Node("york", "Place"),
        ],
        [
            ("transfer", "identification", "given_to"),
            ("identification", "alternative", "target"),
            ("alternative", "ben", "alternatives", {"percent": 70}),
            ("activity", "role", "participants"),
            ("role", "dee", "target"),
            ("role", "york", "at"),
        ],
    )
    maps = with_rules(
        class_weight={
            "Transfer": 0.5,
            "Identification": 0.5,
            "Activity": 2.0,
            "InRole": 0.3,
        },
        field_weight={
            "Transfer.given_to": 0.4,
            "Activity.participants": 0.5,
            "InRole.at": 0.7,
        },
    )
    assert joins(reader, maps) == {
        # (the transfer 0.5, its field 0.4, the identification 0.5, the share 0.7)
        ("ben", "transfer"): 0.07,
        # (the activity 2, its field 0.5, the role 0.3)
        ("activity", "dee"): 0.3,
        # (and the role's own field 0.7)
        ("activity", "york"): 0.21,
    }
