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
- `RememberingReader` (`reading(work, remember=N)`): a `CypherReader` that asks for an id at most once for each of
  its reads, for the groups of a refresh past the cap (`part.refresh_ids`), which overlap and are tried again in
  halves. It forgets everything once it holds more than `N` ids and answers (`REMEMBERED_CAPS` times the cap, for a refresh).
- `walk=` (of `load_all`, `reading`, `in_thread` and the readers): for the second part, `"actual"`. Each node's stored
  path (`meta.path`, `Dialect.meta_property`: JSON text on Neo4j) is read in the same query as the node, one column
  more (`page_query`, `nodes_query`), and the node is given the weight the walk says (`pangloss_fastrp.walk`). Without
  it (the graph part) the queries are those they were, and no path is read.

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
from typing import TYPE_CHECKING, Any

from pangloss_cypher import fragments

from pangloss_fastrp.maths import OUT, Edge, GraphMaps, Node
from pangloss_fastrp.memory import MemoryReader

if TYPE_CHECKING:
    from pangloss_fastrp.walk import Walk

# (nodes read in each page of `load_all`, each page in a transaction of its own; and ids in each query of the reader)
PAGE = 10_000
LOOKUP = 1_000

# A `RememberingReader` of a refresh forgets everything it has read once it holds more than this many times
# `FASTRP_REFRESH_CAP` ids and answers of its reads, edges with nodes (it reads them again; nothing else changes).
# The burst measured on 2026-11-21 (200 factoids, a cap of 50,000) asked for 1.6 million ids in all
REMEMBERED_CAPS = 40

# (the edges a reader follows: `fragments.forward`, written out because both ends are matched here as well)
FORWARD = "NOT coalesce(e.reverse, false) AND NOT coalesce(e.derived, false)"


def page_query(path: str | None = None) -> str:
    """A page of `load_all`: one row, of a list for each node, in the order of `PAGE_COLUMNS` (and with `path`, the
    expression of the node's stored path, `Dialect.meta_property`, that too, last: for the walk of the second part).
    One row of lists, not a record for each node: the driver's work for each record was most of the time of a page,
    0.17 s of 10,000 nodes against 0.07 s, on Memgraph on :7690, 2026-11-21"""
    more = f", {path}" if path is not None else ""
    return f"""
MATCH (n:PGIndexableNode) WHERE n.id > $after
WITH n ORDER BY n.id LIMIT $page
RETURN collect([n.id, n.type, n.head_node_id, {fragments.deleted("n")}, n.merged_into, n.published,
                n.target_id{more}]) AS rows
"""


def nodes_query(path: str | None = None) -> str:
    """The nodes of these ids, each with its head's type and flags (and with `path`, as `page_query`, its stored
    path)"""
    more = f", {path} AS path" if path is not None else ""
    return f"""
UNWIND $ids AS id
MATCH (n:PGIndexableNode {{id: id}})
OPTIONAL MATCH (h:HeadNode {{id: n.head_node_id}})
RETURN n.id AS id, n.type AS type, n.head_node_id AS head, {fragments.deleted("n")} AS deleted,
       n.merged_into AS merged_into, n.published AS published, n.target_id AS cites,
       h.type AS head_type, {fragments.deleted("h")} AS head_deleted, h.published AS head_published{more}
"""


# (the structural part's: no path is read)
PAGE_QUERY = page_query()
PAGE_COLUMNS = ("id", "type", "head", "deleted", "merged_into", "published", "cites")
NODES_QUERY = nodes_query()


def path_expression() -> str:
    """The stored path of the node `n`, as the backend under use reads it (Neo4j: JSON text)"""
    from pangloss_core import backend

    return backend.current().dialect.meta_property("n", "path")


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


# (a query for each label, each by its own index on `target_id`; `of`, the id cited, for `RememberingReader`)
CITING_QUERIES = tuple(
    f"UNWIND $ids AS id MATCH (c:{label} {{target_id: id}}) RETURN c.id AS id, id AS of"
    for label in ("PGCitation", "PGUnprotectedCitation")
)

# The nodes below these heads (their documents and wrappers, by the index of `PGIndexableNode(head_node_id)`); `of`,
# the head
BELOW_QUERY = """
UNWIND $ids AS id
MATCH (n:PGIndexableNode {head_node_id: id})
RETURN n.id AS id, id AS of
"""


def _published(value: Any) -> bool:
    return True if value is None else bool(value)


def node_of(
    row: Mapping[str, Any],
    head: Mapping[str, Any] | None,
    maps: GraphMaps,
    walk: Walk | None = None,
) -> Node:
    """The node of a row of `PAGE_QUERY` or `NODES_QUERY`, given its head's row (`type`, `deleted`, `published`), or
    None if it is a head or its head is missing. With `walk`, the row has the node's `path`, and the node the weight
    the walk gives it (the second part)"""
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
        weight=1.0
        if walk is None
        else walk.weight(row["type"], row["path"], head["type"] if head else None),
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


async def load_all(
    maps: GraphMaps, *, page: int = PAGE, walk: Walk | None = None
) -> MemoryReader:
    """Every node and forward edge of the graph, into memory (for a whole rebuild): the nodes as `maths.Node`s, with
    what they take from their heads worked out here. An edge carries only the properties the maths can use
    (`used_properties`), where a `CypherReader`'s carry all. With `walk` (the second part), each node's stored path
    is read in its page and walked (`node_of`)"""
    from pangloss_core import backend

    database = backend.current().database()
    names = used_properties(maps)
    edges_query = load_edges_query(maps)
    nodes_page = PAGE_QUERY if walk is None else page_query(path_expression())
    columns = PAGE_COLUMNS if walk is None else (*PAGE_COLUMNS, "path")

    @database.read_transaction
    async def read(tx: Any, after: str) -> tuple[list[list[Any]], list[list[Any]]]:
        nodes = await _one_row(tx, nodes_page, after=after, page=page)
        ids = [str(row[0]) for row in nodes]
        edges = await _one_row(tx, edges_query, ids=ids) if ids else []
        return nodes, edges

    rows: list[dict[str, Any]] = []
    edges: list[Edge] = []
    after = ""
    while True:
        nodes, found = await read(after)
        rows += [dict(zip(columns, row, strict=True)) for row in nodes]
        edges += loaded_edges(found, names)
        if len(nodes) < page:
            break
        # (the largest id of the page: `collect` is not promised to keep the order it is given)
        after = max(str(row[0]) for row in nodes)
    by_id = {str(row["id"]): row for row in rows}
    return MemoryReader(
        [
            node_of(
                row, by_id.get(str(row["head"])) if row["head"] else None, maps, walk
            )
            for row in rows
        ],
        edges,
    )


class CypherReader:
    """A `maths.Reader` over a read transaction that is open on `loop`, called from another thread (`reading`). Every
    node it gives is kept in `seen`. With `walk` (the second part), each node's stored path is read with it, in the
    same query, and walked"""

    def __init__(
        self,
        tx: Any,
        loop: asyncio.AbstractEventLoop,
        maps: GraphMaps,
        walk: Walk | None = None,
    ):
        self.tx, self.loop, self.maps = tx, loop, maps
        self.walk = walk
        self.nodes_query = (
            NODES_QUERY if walk is None else nodes_query(path_expression())
        )
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
        for row in self._each(self.nodes_query, ids):
            head = (
                {
                    "type": row["head_type"],
                    "deleted": row["head_deleted"],
                    "published": row["head_published"],
                }
                if row["head_type"] is not None
                else None
            )
            node = node_of(row, head, self.maps, self.walk)
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


class RememberingReader(CypherReader):
    """A `CypherReader` that asks the database for an id at most once for each of its five reads (`nodes`,
    `out_edges`, `in_edges`, `citing`, `below`), so that the groups of a refresh (`part.refresh_ids`), which overlap
    and are tried again in halves, read nothing twice. Before each read, if it holds more than `most` ids and answers (nodes, edges, citations, of all five reads) it forgets
    everything it holds and reads again (`seen` is kept)"""

    def __init__(
        self,
        tx: Any,
        loop: asyncio.AbstractEventLoop,
        maps: GraphMaps,
        most: int,
        walk: Walk | None = None,
    ):
        super().__init__(tx, loop, maps, walk)
        self.most = most
        self.forgotten = 0
        self._held: dict[str, dict[str, list[Any]]] = {}
        self._forget()

    def _forget(self) -> None:
        # (each read's answers by the id asked: a node is a list of none or one)
        self._held = {read: {} for read in ("nodes", "out", "in", "citing", "below")}
        # (how many ids and answers are held, of all five reads: the edges of a hub are most of what is held)
        self._size = 0

    def _remembered(
        self,
        read: str,
        ids: Iterable[str],
        fetch: Callable[[list[str]], Iterable[tuple[str, Any]]],
    ) -> list[Any]:
        """What is held of these ids for `read`, `fetch` asked (giving `(id asked, answer)` pairs) for the ids not
        held yet; each id's answers in the order of the ids"""
        if self._size > self.most:
            self.forgotten += 1
            self._forget()
        held = self._held[read]
        wanted = sorted({str(i) for i in ids})
        missing = [i for i in wanted if i not in held]
        if missing:
            for i in missing:
                held[i] = []
            self._size += len(missing)
            for of, found in fetch(missing):
                held[of].append(found)
                self._size += 1
        return [found for i in wanted for found in held[i]]

    def nodes(self, ids: Iterable[str] | None = None) -> list[Node]:
        if ids is None:
            return super().nodes(None)
        return self._remembered(
            "nodes",
            ids,
            lambda missing: (
                (node.id, node) for node in CypherReader.nodes(self, missing)
            ),
        )

    def out_edges(self, ids: Iterable[str]) -> list[Edge]:
        return self._remembered(
            "out",
            ids,
            lambda missing: (
                (e.source, e) for e in CypherReader.out_edges(self, missing)
            ),
        )

    def in_edges(self, ids: Iterable[str]) -> list[Edge]:
        return self._remembered(
            "in",
            ids,
            lambda missing: (
                (e.target, e) for e in CypherReader.in_edges(self, missing)
            ),
        )

    def citing(self, ids: Iterable[str]) -> list[str]:
        def fetch(missing: list[str]) -> Iterable[tuple[str, str]]:
            for query in CITING_QUERIES:
                for row in self._each(query, missing):
                    yield str(row["of"]), str(row["id"])

        return sorted(set(self._remembered("citing", ids, fetch)))

    def below(self, heads: Iterable[str]) -> list[str]:
        def fetch(missing: list[str]) -> Iterable[tuple[str, str]]:
            for row in self._each(BELOW_QUERY, missing):
                yield str(row["of"]), str(row["id"])

        return sorted(set(self._remembered("below", heads, fetch)))


async def in_thread[T](
    tx: Any,
    maps: GraphMaps,
    work: Callable[[CypherReader], T],
    *,
    remember: int | None = None,
    walk: Walk | None = None,
) -> T:
    """`work(reader)` in a thread, with a `CypherReader` over `tx`, a transaction open on the running loop (for a
    transaction function that does more than read the graph). `remember`: a `RememberingReader` that holds at most
    about that many nodes. `walk`: the reader walks each node's path (the second part)"""
    loop = asyncio.get_running_loop()
    reader = (
        CypherReader(tx, loop, maps, walk)
        if remember is None
        else RememberingReader(tx, loop, maps, remember, walk)
    )
    return await asyncio.to_thread(work, reader)


async def reading[T](
    maps: GraphMaps,
    work: Callable[[CypherReader], T],
    *,
    remember: int | None = None,
    walk: Walk | None = None,
) -> T:
    """`work(reader)` in a thread, with a `CypherReader` over one read transaction (`remember`, `walk`: see
    `in_thread`)"""
    from pangloss_core import backend

    database = backend.current().database()

    @database.read_transaction
    async def run(tx: Any) -> T:
        return await in_thread(tx, maps, work, remember=remember, walk=walk)

    return await run()
