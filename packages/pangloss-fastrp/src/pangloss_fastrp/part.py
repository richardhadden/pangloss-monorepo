"""The graph part (`"graph"`): a vector of each document and entity from what it is joined to, by FastRP over the joined
graph (`maths.py`, by the rules of `maps.py`), read from a Cypher database (`cypher_reader.py`).
implementation_docs/similarity-build-plan.md, step 3.3.

- `rebuild`: the whole graph read into memory (`load_all`), the maths in a thread, a vector for every stop that is
  joined to something (nested documents too), written in pages.
- `refresh`: the heads written and removed (`refresh_ids`). What the maths wants is every stop whose joins may have
  changed: both ends of every join made, lost or reweighted. They are worked out as every stop of the trees of those
  heads (the head and what has its `head_node_id`), every stop those are joined to as they are now **or would be were
  they in** (so a deleted, unpublished or merged item's neighbours are found by the edges it still has), and what the
  heads named before the write (`Changed.before`, which the worker has from the marks: a reference an update
  *dropped* leaves no edge to find it by, and the documents an update replaced are no longer there). The vectors of
  what is now joined to nothing go (`store.remove_vectors`, this part's only); the caller deletes every vector of
  `Changed.removed` (`pangloss_vectors.parts.Refreshed`).
- Past `FASTRP_REFRESH_CAP` nodes the neighbourhood is not read: the stops of the trees of the heads written get an
  approximate vector, from their joins and the vectors stored of what they are joined to (`approximate.py`), and are
  reported stale with the heads removed (whose neighbours are left as they were), until a rebuild.
- `overlay`: the nodes and edges of a write plan laid over the database, as the write would leave them.

numpy is imported only when one of these runs (`maths`), not with the package.
"""

import copy
from collections.abc import Iterable, Sequence
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from pangloss_vectors.parts import Changed, Refreshed, Vector, VectorRow, Writer

from pangloss_fastrp import maps
from pangloss_fastrp.settings import dimension, refresh_cap

if TYPE_CHECKING:
    from pangloss_fastrp.cypher_reader import CypherReader
    from pangloss_fastrp.maths import Edge, GraphMaps, Node, Reader

NAME = "graph"

# (rows given to the writer at a time)
WRITE_PAGE = 1000


def _plain(vector: Any) -> list[float]:
    return [float(x) for x in vector]


async def _write(write: Writer, rows: Sequence[VectorRow]) -> None:
    for start in range(0, len(rows), WRITE_PAGE):
        await write(rows[start : start + WRITE_PAGE])


class _AsIfIn:
    """A reader that gives these nodes as if they were in the graph (not deleted, merged nor unpublished): their joins
    as they would be, by the edges they have now"""

    def __init__(self, base: Reader, ids: Iterable[str]):
        self.base, self.ids = base, set(ids)

    def nodes(self, ids: Iterable[str] | None = None) -> list[Node]:
        return [
            replace(node, deleted=False, merged_into=None, published=True)
            if node.id in self.ids
            else node
            for node in self.base.nodes(ids)
        ]

    def out_edges(self, ids: Iterable[str]) -> Iterable[Edge]:
        return self.base.out_edges(ids)

    def in_edges(self, ids: Iterable[str]) -> Iterable[Edge]:
        return self.base.in_edges(ids)

    def citing(self, ids: Iterable[str]) -> Iterable[str]:
        return self.base.citing(ids)


def changed_stops(
    reader: CypherReader,
    graph: GraphMaps,
    heads: Iterable[str],
    before: Iterable[str] = (),
) -> set[str]:
    """What `maths.refresh` is to be given for a write of these heads: their trees, what those are joined to (as if
    they were in), and `before`"""
    from pangloss_fastrp import maths

    heads = sorted(set(heads))
    tree = set(heads) | set(reader.below(heads))
    found = maths.joins(_AsIfIn(reader, tree), graph, tree)
    return tree | {i for key in found for i in key} | set(before)


async def refresh_ids(
    ids: Iterable[str],
    write: Writer,
    before: Iterable[str] = (),
    *,
    removed: Iterable[str] = (),
) -> Refreshed:
    """Bring the graph vectors up to date after a write of the heads `ids` (and of the heads `removed`: deleted, or
    merged into another), writing those that changed with `write` and deleting this part's vectors of the stops now
    joined to nothing. `before`: the stops the heads named before the write, where the write may have dropped a
    reference or replaced its nested documents (see the module). Past the cap: approximate vectors of the trees of the
    heads written (`approximately`), and `stale` those and the heads removed"""
    from pangloss_vectors import store

    from pangloss_fastrp import maths
    from pangloss_fastrp.cypher_reader import reading

    written = sorted({str(i) for i in ids})
    heads = sorted(set(written) | {str(i) for i in removed})
    named = sorted({str(i) for i in before})
    if not heads and not named:
        return Refreshed()
    graph = maps.graph_maps()
    cap = refresh_cap()

    def work(reader: CypherReader) -> tuple[maths.Refreshed, dict[str, str]]:
        centre = changed_stops(reader, graph, heads, named)
        made = maths.refresh(reader, graph, centre, cap)
        return made, {i: reader.seen[i].type for i in made.vectors}

    try:
        made, types = await reading(graph, work)
    except maths.TooLarge:
        return await approximately(written, write, removed=len(heads) - len(written))
    rows = [
        VectorRow(of=i, type=types[i], vector=_plain(vector))
        for i, vector in sorted(made.vectors.items())
    ]
    await _write(write, rows)
    if made.gone:
        await store.remove_vectors(NAME, made.gone)
    return Refreshed(written=len(rows))


async def approximately(
    heads: Sequence[str], write: Writer, *, removed: int = 0
) -> Refreshed:
    """Past the cap: the stops of the trees of these heads that are in the graph get the approximate vector of
    `approximate.approximate`, from their joins (one ring read) and the stored vectors of what they are joined to;
    those of the trees that are out of it, or joined to nothing, lose theirs. All of them are stale, and so is each of
    the `removed` heads' neighbourhoods, left as it was"""
    from pangloss_vectors import store

    from pangloss_fastrp import maths
    from pangloss_fastrp.approximate import approximate
    from pangloss_fastrp.cypher_reader import reading

    if not heads:
        return Refreshed(stale=removed)
    graph = maps.graph_maps()

    def work(
        reader: CypherReader,
    ) -> tuple[set[str], set[str], dict[tuple[str, str], float], dict[str, str]]:
        tree = set(heads) | set(reader.below(heads))
        found = {node.id: node for node in reader.nodes(sorted(tree))}
        stops = {i for i in tree if graph.is_in(found.get(i))}
        weights = maths.joins(reader, graph, stops) if stops else {}
        return tree, stops, weights, {i: found[i].type for i in stops}

    tree, stops, weights, types = await reading(graph, work)
    around = {i for key in weights for i in key} - stops
    vectors = approximate(stops, weights, await store.read_part(NAME, around), graph)
    rows = [
        VectorRow(of=i, type=types[i], vector=_plain(vector))
        for i, vector in sorted(vectors.items())
    ]
    await _write(write, rows)
    gone = sorted(tree - set(vectors))
    if gone:
        await store.remove_vectors(NAME, gone)
    return Refreshed(written=len(rows), stale=len(rows) + removed)


# ---------------------------------------------------------------------------
# An overlay
# ---------------------------------------------------------------------------


URL_QUERY = """
UNWIND $values AS value
MATCH (:PGUrl {url: value})<-[:has_url]-(node:PGIndexableNode)
RETURN value, node.id AS id
"""


async def _resolved(tx: Any, plan: Any) -> tuple[Any, dict[Any, Any], dict[str, str]]:
    """A copy of the plan with its references as the write would make them (to the survivor of a merged entity), the
    entities written in it that exist, and the ids of the URLs it names. Refuses what the write would refuse of them
    (`PanglossReferenceError`)"""
    from pangloss_cypher.validate_write import (
        check_references_exist,
        find_existing_entities,
    )

    plan = copy.deepcopy(plan)
    existing = (
        await find_existing_entities(tx, plan.inline_entities)
        if plan.inline_entities
        else {}
    )
    await check_references_exist(tx, plan, existing)
    values = sorted({r.value for r in plan.references(existing) if r.is_url})
    urls: dict[str, str] = {}
    if values:
        result = await tx.run(URL_QUERY, values=values)
        urls = {str(r["value"]): str(r["id"]) async for r in result}
    return plan, existing, urls


def laid_out(
    plan: Any,
    existing: dict[Any, Any],
    urls: dict[str, str],
    published: bool,
    citations: Iterable[str],
) -> tuple[list[Node], list[Edge]]:
    """The nodes and forward edges a plan writes (`pangloss_cypher.write_plan.WritePlan`): its head and the nodes below
    it, each with the head's `published`, an entity written in it that does not exist (published), and an edge for each
    of a relation's names (the field's, and those of the parent fields it subclasses)"""
    from pangloss_cypher.write_plan import (
        InlineEntity,
        PlannedNode,
        ReferenceToExisting,
    )

    from pangloss_fastrp.maths import Edge, Node

    citation_types = set(citations)

    def node(planned: PlannedNode, is_published: bool) -> Node:
        cites = (
            planned.properties.get("target_id")
            if planned.type in citation_types
            else None
        )
        return Node(
            planned.id,
            planned.type,
            published=is_published,
            cites=None if cites is None else str(cites),
        )

    nodes = {plan.head.id: node(plan.head, published)}
    # (what a node takes from its head: the document's, or that of an entity written in it, which is published)
    head_published = {plan.head.id: published}
    edges: list[Edge] = []
    for source, relation, first in plan.walk(existing):
        target = relation.target
        if isinstance(target, PlannedNode):
            end = target.id
            head_published[end] = head_published.get(source.id, published)
            nodes[end] = node(target, head_published[end])
        elif isinstance(target, ReferenceToExisting):
            end = (
                urls.get(target.value, target.value) if target.is_url else target.value
            )
        else:
            assert isinstance(target, InlineEntity)
            if target.key in existing:
                end = existing[target.key].id
            else:
                assert target.node is not None
                end = target.node.id
                if first:
                    nodes[end] = node(target.node, True)
                    head_published[end] = True
        properties = dict(relation.edge_properties or {})
        for forward, _ in relation.edges:
            edges.append(Edge(source.id, str(end), forward, properties))
    return list(nodes.values()), edges


async def overlay_plan(plan: Any) -> dict[str, list[float]]:
    """The graph vectors of the stops of a write plan, were it written: of the head, its nested documents and the
    entities it writes, as a rebuild after the write would give them; nothing is written. An update replaces what is
    below its head (the nodes of its `head_node_id` now are taken away). A stop joined to nothing has none"""
    from pangloss_core import backend

    from pangloss_fastrp import maths
    from pangloss_fastrp.cypher_reader import in_thread

    graph = maps.graph_maps()
    cap = refresh_cap()
    database = backend.current().database()

    @database.read_transaction
    async def run(tx: Any) -> dict[str, Any]:
        resolved, existing, urls = await _resolved(tx, plan)

        def work(reader: CypherReader) -> dict[str, Any]:
            head_id = str(resolved.head.id)
            removed: list[str] = []
            if resolved.is_update:
                now = {n.id: n for n in reader.nodes([head_id])}
                published = head_id not in now or now[head_id].published
                removed = reader.below([head_id])
            else:
                published = bool(resolved.head.properties.get("published", True))
            nodes, edges = laid_out(
                resolved, existing, urls, published, graph.citations
            )
            return maths.overlay(reader, graph, nodes, edges, removed, cap)

        return await in_thread(tx, graph, work)

    return {i: _plain(vector) for i, vector in sorted((await run()).items())}


# ---------------------------------------------------------------------------
# The part
# ---------------------------------------------------------------------------


class GraphPart:
    """The part: an object, registered when `pangloss_fastrp` is imported"""

    name = NAME
    local = True
    requires: frozenset[str] = frozenset()
    weight = 1.0

    def __repr__(self) -> str:
        return "GraphPart()"

    def dimension(self) -> int:
        return dimension()

    def signature(self) -> str:
        return maps.signature()

    async def rebuild(self, write: Writer) -> int:
        """Every stop's vector, from the whole graph read into memory: the maths in a thread (seconds of numpy)"""
        import asyncio

        from pangloss_fastrp import maths
        from pangloss_fastrp.cypher_reader import load_all

        graph = maps.graph_maps()
        reader = await load_all(graph)
        vectors = await asyncio.to_thread(maths.rebuild, reader, graph)
        rows = [
            VectorRow(of=i, type=reader.node[i].type, vector=_plain(vector))
            for i, vector in sorted(vectors.items())
        ]
        await _write(write, rows)
        return len(rows)

    async def refresh(self, changed: Changed, write: Writer) -> Refreshed:
        """The heads written and removed, and what they named before (`refresh_ids`)"""
        return await refresh_ids(
            [item.id for item in changed.written],
            write,
            before=changed.before,
            removed=changed.removed,
        )

    async def overlay(self, plan: Any) -> dict[str, Vector]:
        return dict(await overlay_plan(plan))


PART = GraphPart()


def install() -> None:
    """(`pangloss_fastrp._install`) register the part"""
    from pangloss_vectors.parts import register_part

    register_part(PART)
