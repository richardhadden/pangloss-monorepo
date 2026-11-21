"""The graph part's reader on the backend under test (implementation_docs/similarity-build-plan.md, step 3.3): on a
document of every shape of `pangloss_testing.similar_models`, `load_all()` and `CypherReader` give the same nodes and
edges, and the joins the maths makes of them are the joins the rules give, written out by hand here; each query of
the reader reads from an index, never a label or every node."""

import dataclasses
from typing import no_type_check

import pytest
from pangloss_fastrp import maps, maths
from pangloss_fastrp.cypher_reader import (
    BELOW_QUERY,
    CITING_QUERIES,
    IN_QUERY,
    NODES_QUERY,
    OUT_QUERY,
    PAGE_QUERY,
    CypherReader,
    load_all,
    reading,
)
from pangloss_fastrp.maths import pair
from pangloss_testing.similar_models import declare

from fastrp_live_support import make_model_indexes, plan_of, scans_in, write_shapes

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture
def shapes(db_driver, clear_database):
    """(the database emptied before and after)"""
    return db_driver


async def joins_read(starts=None) -> dict:
    """`maths.joins` through a `CypherReader` (with `starts`), or over `load_all()`"""
    graph = maps.graph_maps()
    if starts is None:
        return maths.joins(await load_all(graph), graph)
    return await reading(graph, lambda reader: maths.joins(reader, graph, starts))


def by_hand(ids: dict[str, str], pairs: dict[tuple[str, str], float]) -> dict:
    return {pair(ids[a], ids[b]): pytest.approx(w) for (a, b), w in pairs.items()}


# The joins of `write_shapes`, from the rules: a nested document is joined to what it is in; a wrapper is passed
# through to what it holds (`Identification`, `WeightedAlternative` at its shares, `InRole`, `Sworn` below it, a
# `Negative` without a stop, `SameEntity`, a `MatchesCriteria` to its candidates at one over their number), and its
# own relations are joined to the document (`InRole.at`); a field and the parent field it subclasses are one join
# (`carried_out_by`, `involves`); a citation joins the citing statement to what it cites; a derived document and
# what is in it are out; entities have no forward edge of their own
SHAPES = {
    ("gift", "transfer"): 1,
    ("transfer", "Ada"): 1,
    ("transfer", "Ben"): 0.7,
    ("transfer", "Cy"): 0.3,
    ("no gift", "denied"): 1,
    ("denied", "Ada"): 1,
    ("denied", "Ben"): 0.7,
    ("denied", "Cy"): 0.3,
    ("meeting", "activity"): 1,
    ("activity", "Ada"): 1,
    ("activity", "Dee"): 1,
    ("activity", "Eve"): 1,
    ("activity", "place"): 1,
    ("members", "fay member"): 1,
    ("members", "gus member"): 1,
    ("fay member", "Fay"): 1,
    ("fay member", "group"): 1,
    ("gus member", "Gus"): 1,
    ("gus member", "group"): 1,
    ("member gift", "member transfer"): 1,
    ("member transfer", "Ada"): 1,
    ("member transfer", "Fay"): 0.5,
    ("member transfer", "Gus"): 0.5,
    ("inference", "inference statement"): 1,
    ("inference statement", "transfer"): 1,
    ("two names", "Dee"): 1,
    ("two names", "Eve"): 1,
    ("Fay's parent", "Fay child"): 1,
    ("Fay child", "Fay"): 1,
    ("Fay child", "Parent"): 1,
    ("Gus's parent", "Gus child"): 1,
    ("Gus child", "Gus"): 1,
    ("Gus child", "Parent"): 1,
}


@no_type_check
async def test_load_all_and_the_reader_give_the_same_nodes_and_edges(shapes):
    m = declare()
    ids = await write_shapes(m, shapes)
    graph = maps.graph_maps()
    everything = await load_all(graph, page=7)
    all_ids = sorted(everything.node)
    assert set(ids.values()) <= set(all_ids)

    def read(reader: CypherReader):
        return (
            {n.id: n for n in reader.nodes(all_ids)},
            sorted(_edge_key(e) for e in reader.out_edges(all_ids)),
            sorted(_edge_key(e) for e in reader.in_edges(all_ids)),
            sorted(reader.citing(all_ids)),
        )

    nodes, out, into, citing = await reading(graph, read)
    assert nodes == everything.node
    assert out == sorted(_edge_key(e) for e in everything.out_edges(all_ids))
    assert into == out
    assert citing == sorted(everything.citing(all_ids))
    # (the citation of the inference, and the two of the derived document, which only have `PGUnprotectedCitation`)
    assert len(citing) == 3


def _edge_key(edge: maths.Edge) -> tuple:
    return (edge.source, edge.target, edge.field, sorted(edge.properties.items()))


def touching(starts: list[str]) -> dict[tuple[str, str], float]:
    """The joins of `SHAPES` that have an end among these names"""
    return {key: w for key, w in SHAPES.items() if key[0] in starts or key[1] in starts}


@no_type_check
async def test_the_joins_of_the_whole_graph_are_those_of_the_rules(shapes):
    m = declare()
    ids = await write_shapes(m, shapes)
    assert await joins_read() == by_hand(ids, SHAPES)


@pytest.mark.parametrize(
    "starts",
    [
        # (alternatives at their shares, a citation of the transfer from the inference)
        ["gift", "transfer"],
        # (the same inside a `Negative`, which has no stop)
        ["no gift", "denied"],
        # (`InRole.at` joined to the activity, `Sworn` below `InRole`, `carried_out_by` and `involves` one join)
        ["meeting", "activity"],
        # (the candidates of a `MatchesCriteria` its worker found, at a half each)
        ["member gift", "member transfer"],
        # (the citing statement joined to the transfer it cites)
        ["inference", "inference statement"],
        # (`SameEntity` holds both people)
        ["two names"],
        # (a person: every join that ends at her)
        ["Fay"],
        # (the derived document, and the statement in it, out)
        ["siblings", "sibling"],
    ],
    ids=lambda starts: " and ".join(starts),
)
@no_type_check
async def test_the_joins_of_each_shape_read_through_the_reader_are_those_of_the_rules(
    shapes, starts
):
    m = declare()
    ids = await write_shapes(m, shapes)
    assert await joins_read([ids[name] for name in starts]) == by_hand(
        ids, touching(starts)
    )


@no_type_check
async def test_a_stop_on_negative_ends_the_chain_and_the_statement_in_it_keeps_its_own_joins(
    shapes, monkeypatch
):
    m = declare()
    ids = await write_shapes(m, shapes)
    rules = maps.build_maps()
    assert rules.kinds["Negative"] == "through"
    monkeypatch.setattr(
        maps,
        "_found",
        dataclasses.replace(rules, kinds={**rules.kinds, "Negative": "end"}),
    )
    wanted = {k: w for k, w in SHAPES.items() if k != ("no gift", "denied")}
    assert await joins_read() == by_hand(ids, wanted)
    assert await joins_read([ids["no gift"], ids["denied"]]) == by_hand(
        ids, {k: w for k, w in touching(["denied"]).items() if k in wanted}
    )


@no_type_check
async def test_a_merged_entity_is_out_and_its_survivor_is_joined_in_its_place(shapes):
    """Eve into Dee: the meeting's reference to Eve is moved to Dee (one join, at the larger weight); the claim that
    they are one still names Eve, who is out"""
    m = declare()
    ids = await write_shapes(m, shapes)
    await m.Person.merge(absorb=ids["Eve"], into=ids["Dee"])
    wanted = {k: w for k, w in SHAPES.items() if "Eve" not in k}
    assert await joins_read() == by_hand(ids, wanted)
    graph = maps.graph_maps()
    eve = await reading(graph, lambda reader: reader.nodes([ids["Eve"]]))
    assert eve[0].merged_into == ids["Dee"]
    assert await joins_read([ids["Eve"]]) == {}
    assert await joins_read([ids["Dee"]]) == by_hand(ids, touching(["Dee"]))


@no_type_check
async def test_a_nested_node_takes_deleted_from_its_head_and_is_out_when_its_head_is(
    shapes,
):
    m = declare()
    ids = await write_shapes(m, shapes)
    await m.Factoid.delete(ids["meeting"])
    graph = maps.graph_maps()
    found = await reading(
        graph,
        lambda reader: {
            n.id: n
            for n in reader.nodes(
                [ids["meeting"], ids["activity"], ids["siblings"], ids["sibling"]]
            )
        },
    )
    assert found[ids["meeting"]].deleted and found[ids["activity"]].deleted
    # (the derived document is of a kind that is out; the statement in it is a stop by its class, out with it)
    assert graph.kinds["DerivedFactoid"] == "out" and graph.kinds["Sibling"] == "stop"
    assert not found[ids["siblings"]].deleted and found[ids["sibling"]].deleted
    everything = await load_all(graph)
    assert everything.node[ids["activity"]].deleted
    assert everything.node[ids["sibling"]].deleted
    wanted = {k: w for k, w in SHAPES.items() if not {"meeting", "activity"} & set(k)}
    assert await joins_read() == by_hand(ids, wanted)


@pytest.mark.parametrize("sees", ["everyone", "logged_in"])
@no_type_check
async def test_an_unpublished_document_is_in_the_graph_only_when_the_graph_sees_what_the_logged_in_see(
    shapes, graph_sees, sees
):
    pytest.importorskip("pangloss_review")
    graph_sees(sees)
    m = declare(reviewed=True)
    ids = await write_shapes(m, shapes, published=True)
    secret = await m.Factoid.Create(
        label="secret",
        statements=[
            {
                "type": "Transfer",
                "label": "Ben gave to Cy",
                "given_by": {"type": "Person", "id": ids["Ben"]},
                "given_to": {"type": "Person", "id": ids["Cy"]},
            }
        ],
    ).save()
    graph = maps.graph_maps()
    assert graph.sees == sees
    everything = await load_all(graph)
    [statement] = [
        n.id
        for n in everything.node.values()
        if n.type == "Transfer" and n.id not in ids.values()
    ]
    ids |= {"secret": str(secret.id), "secret transfer": statement}
    assert not everything.node[ids["secret"]].published
    assert not everything.node[statement].published
    hidden = {
        ("secret", "secret transfer"): 1,
        ("secret transfer", "Ben"): 1,
        ("secret transfer", "Cy"): 1,
    }
    wanted = SHAPES | (hidden if sees == "logged_in" else {})
    assert await joins_read() == by_hand(ids, wanted)
    assert await joins_read([ids["Ben"]]) == by_hand(
        ids, {k: w for k, w in wanted.items() if "Ben" in k}
    )


# ---------------------------------------------------------------------------
# The plans
# ---------------------------------------------------------------------------


QUERIES = {
    "page": (PAGE_QUERY, {"after": "", "page": 10}),
    "nodes": (NODES_QUERY, {"ids": ["a", "b"]}),
    "out": (OUT_QUERY, {"ids": ["a", "b"]}),
    "in": (IN_QUERY, {"ids": ["a", "b"]}),
    "citing PGCitation": (CITING_QUERIES[0], {"ids": ["a", "b"]}),
    "citing PGUnprotectedCitation": (CITING_QUERIES[1], {"ids": ["a", "b"]}),
    "below": (BELOW_QUERY, {"ids": ["a", "b"]}),
}


@pytest.mark.parametrize("name", list(QUERIES))
@no_type_check
async def test_no_query_of_the_reader_scans_a_label_or_every_node(shapes, name):
    """On the shapes, with the indexes of the models made (`PGCitation(target_id)` is one)"""
    m = declare()
    await write_shapes(m, shapes)
    await make_model_indexes(shapes)
    query, parameters = QUERIES[name]
    plan = plan_of(shapes, query, **parameters)
    print(f"\n== {name}\n" + "\n".join(plan))
    assert scans_in(plan) == [], plan
