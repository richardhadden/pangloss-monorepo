"""The graph part's reader of a Cypher database (implementation_docs/similarity-build-plan.md, step 3.3), in Cypher both
backends run, through `pangloss_core.backend.current()`.

- `load_all()`: every `PGIndexableNode` and every forward edge between two of them, into a `MemoryReader`, for a whole
  rebuild. Nodes in pages by the index of `PGIndexableNode(id)` (keyset on `n.id`, no `SKIP`), each page's edges by
  its ids, a page in each read transaction; each query gives one row of lists, and an edge only the properties the
  maths reads (`used_properties`).
- `CypherReader`: a `maths.Reader` over one read transaction, for `refresh` and `overlay`. The maths is synchronous and
  the driver is not, so `reading(work)` runs `work(reader)` in a thread (`asyncio.to_thread`) while the transaction
  stays open on the event loop, and each call of the reader hands its query back to the loop
  (`asyncio.run_coroutine_threadsafe(...).result()`) and waits. The transaction is only ever used from the loop, one
  query at a time (the thread waits for each), which is how the driver expects a transaction to be used. The reads of
  one refresh are of one snapshot on Memgraph; Neo4j reads what is committed when each query runs, so a write that
  commits during a refresh may be seen in part (as by any read of several queries there).

What a node is given (`maths.Node`), from what is stored (notes/similarity-evaluation/stored_shapes.txt):

- `deleted` and `published` of a nested node are its head's (the `HeadNode` of its `head_node_id`); a head's are its
  own. Both properties are absent until set: absent is not deleted, and published (`fragments.published`).
- A nested node whose head is out (its head's class is of kind `out`, as a derived document is) or missing is given
  as deleted: the statements of a derived document are of classes that are stops, but they are out with their head.
- `cites` is the `target_id` of a citation (`PGCitation`, `PGUnprotectedCitation`); the citations of an id are asked
  of both labels, each by its index on `target_id` (a citation of a derived document has only the second).
- Edges are forward only: not the reverse edge of a field, nor the shortcut of a derived edge
  (`fragments.forward`), with both ends `PGIndexableNode`, and their properties as stored (`load_all`'s: only those
  the maths reads).
"""

import asyncio
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from pangloss_cypher import fragments

from pangloss_fastrp.maths import OUT, Edge, GraphMaps, Node
from pangloss_fastrp.memory import MemoryReader

# (nodes read in each page of `load_all`, each page in a transaction of its own; and ids in each query of the reader)
PAGE = 10_000
LOOKUP = 1_000

# (the edges a reader follows: `fragments.forward`, written out because both ends are matched here as well)
FORWARD = "NOT coalesce(e.reverse, false) AND NOT coalesce(e.derived, false)"

# (a page of `load_all`: one row, of a list for each node, in the order of `PAGE_COLUMNS`. One row of lists, not a
# record for each node: the driver's work for each record was most of the time of a page, 0.17 s of 10,000 nodes
# against 0.07 s, on Memgraph on :7690, 2026-11-21)
PAGE_QUERY = f"""
MATCH (n:PGIndexableNode) WHERE n.id > $after
WITH n ORDER BY n.id LIMIT $page
RETURN collect([n.id, n.type, n.head_node_id, {fragments.deleted("n")}, n.merged_into, n.published,
                n.target_id]) AS rows
"""
PAGE_COLUMNS = ("id", "type", "head", "deleted", "merged_into", "published", "cites")

NODES_QUERY = f"""
UNWIND $ids AS id
MATCH (n:PGIndexableNode {{id: id}})
OPTIONAL MATCH (h:HeadNode {{id: n.head_node_id}})
RETURN n.id AS id, n.type AS type, n.head_node_id AS head, {fragments.deleted("n")} AS deleted,
       n.merged_into AS merged_into, n.published AS published, n.target_id AS cites,
       h.type AS head_type, {fragments.deleted("h")} AS head_deleted, h.published AS head_published
"""

OUT_QUERY = f"""
UNWIND $ids AS id
MATCH (n:PGIndexableNode {{id: id}})-[e]->(m:PGIndexableNode)
WHERE {FORWARD}
RETURN n.id AS source, m.id AS target, type(e) AS field, properties(e) AS properties
"""

IN_QUERY = f"""
UNWIND $ids AS id
MATCH (m:PGIndexableNode {{id: id}})<-[e]-(n:PGIndexableNode)
WHERE {FORWARD}
RETURN n.id AS source, m.id AS target, type(e) AS field, properties(e) AS properties
"""

# (the properties of an edge the maths reads, besides `reverse` and `derived`, which no edge read here has: whether
# it is of a computed relation and who sees it; and the property of each share, `maps.shares`)
EDGE_PROPERTIES = ("computed", "seen_by")


def used_properties(maps: GraphMaps) -> list[str]:
    """The properties of an edge the maths can use under these maps, in order"""
    shared = sorted({str(share[0]) for share in maps.shares.values()})
    return [*EDGE_PROPERTIES, *(name for name in shared if name not in EDGE_PROPERTIES)]


def load_edges_query(maps: GraphMaps) -> str:
    """The forward edges of a page of `load_all`'s nodes, as one row of lists (`[source, target, field, ...]`, then
    the value of each of `used_properties(maps)`): not `properties(e)`, which carries what the maths never reads, and
    one row, not a record for each edge (0.32 s a page of 10,000 nodes and their edges against 0.11 s, on Memgraph
    on :7690, 2026-11-21)"""
    from pangloss_cypher import fragments

    values = ", ".join(f"e.{fragments.property_name(p)}" for p in used_properties(maps))
    return (
        "UNWIND $ids AS id "
        "MATCH (n:PGIndexableNode {id: id})-[e]->(m:PGIndexableNode) "
        f"WHERE {FORWARD} "
        f"RETURN collect([id, m.id, type(e), {values}]) AS rows"
    )


# (a query for each label, each by its own index on `target_id`)
CITING_QUERIES = tuple(
    f"UNWIND $ids AS id MATCH (c:{label} {{target_id: id}}) RETURN c.id AS id"
    for label in ("PGCitation", "PGUnprotectedCitation")
)

# The nodes below these heads (their documents and wrappers, by the index of `PGIndexableNode(head_node_id)`)
BELOW_QUERY = """
UNWIND $ids AS id
MATCH (n:PGIndexableNode {head_node_id: id})
RETURN n.id AS id
"""


def _published(value: Any) -> bool:
    return True if value is None else bool(value)


def node_of(
    row: Mapping[str, Any], head: Mapping[str, Any] | None, maps: GraphMaps
) -> Node:
    """The node of a row of `PAGE_QUERY` or `NODES_QUERY`, given its head's row (`type`, `deleted`, `published`), or
    None if it is a head or its head is missing"""
    deleted = bool(row["deleted"])
    published = _published(row["published"])
    if row["head"] is not None:
        if head is None or maps.kinds.get(head["type"], OUT) == OUT:
            deleted = True
        else:
            deleted = deleted or bool(head["deleted"])
            published = _published(head["published"])
    return Node(
        id=str(row["id"]),
        type=row["type"],
        deleted=deleted,
        merged_into=row["merged_into"],
        published=published,
        cites=row["cites"],
    )


def edge_of(row: Mapping[str, Any]) -> Edge:
    return Edge(
        str(row["source"]), str(row["target"]), row["field"], dict(row["properties"])
    )


def _chunks(ids: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for start in range(0, len(ids), size):
        yield ids[start : start + size]


async def _rows(tx: Any, query: str, **parameters: Any) -> list[dict[str, Any]]:
    result = await tx.run(query, **parameters)
    return [dict(record) async for record in result]


async def _one_row(tx: Any, query: str, **parameters: Any) -> list[list[Any]]:
    """The lists of a query that returns one row, `rows`"""
    record = await (await tx.run(query, **parameters)).single()
    return list(record["rows"] or []) if record is not None else []


def loaded_edges(rows: Iterable[Sequence[Any]], names: Sequence[str]) -> list[Edge]:
    """The edges of `load_edges_query`'s lists: of the properties `names`, only those an edge has"""
    edges = []
    for row in rows:
        properties = {
            name: value
            for name, value in zip(names, row[3:], strict=True)
            if value is not None
        }
        edges.append(Edge(str(row[0]), str(row[1]), row[2], properties))
    return edges


async def load_all(maps: GraphMaps, *, page: int = PAGE) -> MemoryReader:
    """Every node and forward edge of the graph, into memory (for a whole rebuild): the nodes as `maths.Node`s, with
    what they take from their heads worked out here. An edge carries only the properties the maths can use
    (`used_properties`), where a `CypherReader`'s carry all"""
    from pangloss_core import backend

    database = backend.current().database()
    names = used_properties(maps)
    edges_query = load_edges_query(maps)

    @database.read_transaction
    async def read(tx: Any, after: str) -> tuple[list[list[Any]], list[list[Any]]]:
        nodes = await _one_row(tx, PAGE_QUERY, after=after, page=page)
        ids = [str(row[0]) for row in nodes]
        edges = await _one_row(tx, edges_query, ids=ids) if ids else []
        return nodes, edges

    rows: list[dict[str, Any]] = []
    edges: list[Edge] = []
    after = ""
    while True:
        nodes, found = await read(after)
        rows += [dict(zip(PAGE_COLUMNS, row, strict=True)) for row in nodes]
        edges += loaded_edges(found, names)
        if len(nodes) < page:
            break
        # (the largest id of the page: `collect` is not promised to keep the order it is given)
        after = max(str(row[0]) for row in nodes)
    by_id = {str(row["id"]): row for row in rows}
    return MemoryReader(
        [
            node_of(row, by_id.get(str(row["head"])) if row["head"] else None, maps)
            for row in rows
        ],
        edges,
    )


class CypherReader:
    """A `maths.Reader` over a read transaction that is open on `loop`, called from another thread (`reading`). Every
    node it gives is kept in `seen`"""

    def __init__(self, tx: Any, loop: asyncio.AbstractEventLoop, maps: GraphMaps):
        self.tx, self.loop, self.maps = tx, loop, maps
        self.loop_thread = threading.get_ident()
        self.seen: dict[str, Node] = {}

    def _run(self, query: str, **parameters: Any) -> list[dict[str, Any]]:
        if threading.get_ident() == self.loop_thread:
            # (it would wait for the loop it is blocking: the maths that calls a reader runs in a thread)
            raise RuntimeError(
                "A CypherReader is called from a thread of its own (pangloss_fastrp.cypher_reader.reading), not "
                "from the event loop its transaction is open on"
            )
        future = asyncio.run_coroutine_threadsafe(
            _rows(self.tx, query, **parameters), self.loop
        )
        return future.result()

    def _each(self, query: str, ids: Iterable[str]) -> list[dict[str, Any]]:
        wanted = sorted({str(i) for i in ids})
        found: list[dict[str, Any]] = []
        for chunk in _chunks(wanted, LOOKUP):
            found += self._run(query, ids=list(chunk))
        return found

    # (the reader)
    def nodes(self, ids: Iterable[str] | None = None) -> list[Node]:
        if ids is None:
            raise NotImplementedError(
                "A CypherReader reads the nodes it is asked for; every node is `load_all()`'s"
            )
        made = []
        for row in self._each(NODES_QUERY, ids):
            head = (
                {
                    "type": row["head_type"],
                    "deleted": row["head_deleted"],
                    "published": row["head_published"],
                }
                if row["head_type"] is not None
                else None
            )
            node = node_of(row, head, self.maps)
            self.seen[node.id] = node
            made.append(node)
        return made

    def out_edges(self, ids: Iterable[str]) -> list[Edge]:
        return [edge_of(row) for row in self._each(OUT_QUERY, ids)]

    def in_edges(self, ids: Iterable[str]) -> list[Edge]:
        return [edge_of(row) for row in self._each(IN_QUERY, ids)]

    def citing(self, ids: Iterable[str]) -> list[str]:
        found: set[str] = set()
        for query in CITING_QUERIES:
            found |= {str(row["id"]) for row in self._each(query, ids)}
        return sorted(found)

    # (beside the reader)
    def below(self, heads: Iterable[str]) -> list[str]:
        """The ids of the nodes below these heads (their nested documents, wrappers and citations)"""
        return sorted({str(row["id"]) for row in self._each(BELOW_QUERY, heads)})


async def in_thread[T](
    tx: Any, maps: GraphMaps, work: Callable[[CypherReader], T]
) -> T:
    """`work(reader)` in a thread, with a `CypherReader` over `tx`, a transaction open on the running loop (for a
    transaction function that does more than read the graph)"""
    reader = CypherReader(tx, asyncio.get_running_loop(), maps)
    return await asyncio.to_thread(work, reader)


async def reading[T](maps: GraphMaps, work: Callable[[CypherReader], T]) -> T:
    """`work(reader)` in a thread, with a `CypherReader` over one read transaction"""
    from pangloss_core import backend

    database = backend.current().database()

    @database.read_transaction
    async def run(tx: Any) -> T:
        return await in_thread(tx, maps, work)

    return await run()
