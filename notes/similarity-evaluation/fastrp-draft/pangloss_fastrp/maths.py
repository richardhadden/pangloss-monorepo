"""The graph part's maths, with no database in it: the joined graph, FastRP over it, and the exact update of the
vectors a change can alter. An engine (Python over Cypher, the Memgraph module) fills in `Reader`; everything else
is here, so that every engine gives the same vectors.

**The joined graph** (implementation_docs/graph-embeddings.md, "The joined graph, as now proposed"). Its nodes are
the *stops*: documents and entities that are in (not deleted, not merged into another, visible to whom
`GraphMaps.sees` says). Two stops are joined when a chain of forward edges leads from one to the other through
wrappers only. The weight of a join is the product, along the chain, of the class weight of the stop it starts from,
the weight of each field, the weight of each wrapper class, the share of each edge of a `SumsTo` field, and, for
computed edges, one over the number of them from that wrapper's field. A wrapper's own relations are joined to the
stop the chain started from. A citation joins to what it cites. Between two stops there is one join, undirected, at
the largest weight of the ways between them.

**FastRP.** Each stop starts from a sparse random vector made from its id alone (`seeds`). A step replaces every
vector by the weighted mean of its neighbours', scaled to length one; the result is the weighted sum of the steps
(`GraphMaps.steps`). With `k` steps a vector depends on the stops within `k` joins, so a change at a stop alters the
vectors within `k - 1` joins of it, and they are computed exactly from the graph `2k - 1` joins out (`refresh`).
"""

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np
import scipy.sparse as sp

STOP, THROUGH, END, OUT = "stop", "through", "end", "out"


@dataclass(frozen=True, slots=True)
class Node:
    id: str
    type: str
    deleted: bool = False
    merged_into: str | None = None
    published: bool = True
    """Of a nested node: its head's (the reader says)"""
    cites: str | None = None
    """Of a citation: the id it cites"""


@dataclass(frozen=True, slots=True)
class Edge:
    """A forward edge of a field (the reader gives no reverse edge and no derived shortcut)"""

    source: str
    target: str
    field: str
    properties: Mapping[str, Any] = field(default_factory=dict)


class Reader(Protocol):
    def nodes(self, ids: Iterable[str] | None = None) -> Iterable[Node]:
        """The nodes of these ids that exist; with no ids, every node whose kind is a stop"""
        ...

    def out_edges(self, ids: Iterable[str]) -> Iterable[Edge]:
        """The forward edges from these nodes"""
        ...

    def in_edges(self, ids: Iterable[str]) -> Iterable[Edge]:
        """The forward edges to these nodes"""
        ...

    def citing(self, ids: Iterable[str]) -> Iterable[str]:
        """The ids of the citations that cite these ids"""
        ...


@dataclass(frozen=True)
class GraphMaps:
    """The rules, as plain data made from the models (`pangloss_fastrp.maps`); it survives `json.dumps` (`plain`).
    A key of a field is `"Type.field"`. What a map does not name has the default"""

    kinds: Mapping[str, str]
    """type → `stop`, `through` (a wrapper), `end` (a wrapper that ends a chain with no join) or `out`; a type not
    named is out"""
    class_weight: Mapping[str, float] = field(default_factory=dict)
    held: Mapping[str, Sequence[str]] = field(default_factory=dict)
    """wrapper type → the fields that hold what it wraps; its other fields are relations of its own"""
    own: Mapping[str, bool] = field(default_factory=dict)
    """wrapper type → whether its own relations are joined to the stop the chain started from (true)"""
    field_weight: Mapping[str, float] = field(default_factory=dict)
    shares: Mapping[str, Sequence[Any]] = field(default_factory=dict)
    """`"Type.field"` → `[property, total]`: an edge of the field counts its property over the total"""
    citations: Mapping[str, bool] = field(default_factory=dict)
    steps: Sequence[float] = (0.0, 1.0, 1.0)
    dimension: int = 128
    sees: str = "everyone"

    def plain(self) -> dict[str, Any]:
        return {
            "kinds": dict(self.kinds),
            "class_weight": dict(self.class_weight),
            "held": {key: list(value) for key, value in self.held.items()},
            "own": dict(self.own),
            "field_weight": dict(self.field_weight),
            "shares": {key: list(value) for key, value in self.shares.items()},
            "citations": dict(self.citations),
            "steps": list(self.steps),
            "dimension": self.dimension,
            "sees": self.sees,
        }

    @classmethod
    def of(cls, plain: Mapping[str, Any]) -> GraphMaps:
        return cls(**plain)

    def is_in(self, node: Node | None) -> bool:
        """Whether a node is a node of the joined graph"""
        return (
            node is not None
            and self.kinds.get(node.type, OUT) == STOP
            and not node.deleted
            and node.merged_into is None
            and (node.published or self.sees == "logged_in")
        )


def pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


class _Seen:
    """What has been read of the graph so far, so that nothing is asked for twice"""

    def __init__(self, reader: Reader, maps: GraphMaps):
        self.reader, self.maps = reader, maps
        self.node: dict[str, Node | None] = {}
        self.out: dict[str, list[Edge]] = {}
        self.read = 0

    def nodes(self, ids: Iterable[str]) -> None:
        missing = sorted({i for i in ids if i not in self.node})
        if not missing:
            return
        for found in self.reader.nodes(missing):
            self.node[found.id] = found
        for i in missing:
            self.node.setdefault(i, None)
        self.read += len(missing)

    def edges(self, ids: Iterable[str]) -> None:
        missing = sorted({i for i in ids if i not in self.out})
        if not missing:
            return
        for i in missing:
            self.out[i] = []
        for edge in self.reader.out_edges(missing):
            if edge.properties.get("reverse") or edge.properties.get("derived"):
                continue
            self.out[edge.source].append(edge)

    def kind(self, id: str) -> str:
        node = self.node.get(id)
        return OUT if node is None else self.maps.kinds.get(node.type, OUT)

    def is_wrapper(self, id: str) -> bool:
        node = self.node.get(id)
        return node is not None and not self.maps.citations.get(node.type) and self.kind(id) == THROUGH

    def below(self, starts: Iterable[str]) -> None:
        """Read everything the chains from these stops pass: a level of wrappers at a time"""
        level = {s for s in starts if self.maps.is_in(self.node.get(s))}
        while level:
            self.edges(level)
            targets = {edge.target for i in level for edge in self.out[i]}
            self.nodes(targets)
            cited = {n.cites for t in targets if (n := self.node[t]) is not None and n.cites}
            self.nodes(cited)
            level = {t for t in targets if self.is_wrapper(t) and t not in self.out}

    def joins_from(self, start: str, found: dict[tuple[str, str], float]) -> None:
        maps, node = self.maps, self.node[start]
        if not maps.is_in(node):
            return
        assert node is not None

        def join(end: str, weight: float) -> None:
            if end != start and weight > 0 and maps.is_in(self.node.get(end)):
                key = pair(start, end)
                if weight > found.get(key, 0.0):
                    found[key] = weight

        def follow(holder: Node, edges: list[Edge], weight: float, path: tuple[str, ...]) -> None:
            computed: dict[str, int] = {}
            usable = []
            for edge in edges:
                if edge.properties.get("computed"):
                    if maps.sees != "logged_in" and edge.properties.get("seen_by") == "logged_in":
                        continue
                    computed[edge.field] = computed.get(edge.field, 0) + 1
                usable.append(edge)
            for edge in usable:
                key = f"{holder.type}.{edge.field}"
                w = weight * maps.field_weight.get(key, 1.0)
                share = maps.shares.get(key)
                if share is not None and edge.properties.get(share[0]) is not None:
                    w *= float(edge.properties[share[0]]) / float(share[1])
                if edge.properties.get("computed"):
                    w /= computed[edge.field]
                arrive(edge.target, w, path)

        def arrive(id: str, weight: float, path: tuple[str, ...]) -> None:
            at = self.node.get(id)
            if at is None or id in path:
                return
            if maps.citations.get(at.type):
                if at.cites:
                    join(at.cites, weight)
                return
            kind = maps.kinds.get(at.type, OUT)
            if kind == STOP:
                join(id, weight)
            elif kind == THROUGH:
                weight *= maps.class_weight.get(at.type, 1.0)
                held = set(maps.held.get(at.type, ()))
                edges = self.out.get(id, [])
                follow(at, [e for e in edges if e.field in held], weight, (*path, id))
                if maps.own.get(at.type, True):
                    follow(at, [e for e in edges if e.field not in held], weight, (*path, id))

        follow(node, self.out.get(start, []), maps.class_weight.get(node.type, 1.0), (start,))

    def above(self, ids: Iterable[str]) -> set[str]:
        """The stops whose chains could end at these nodes: up through wrappers, and from the citations of them"""
        stops: set[str] = set()
        level, passed = set(ids), set()
        while level:
            passed |= level
            sources = {edge.source for edge in self.reader.in_edges(sorted(level))}
            sources |= set(self.reader.citing(sorted(level)))
            self.nodes(sources)
            level = set()
            for s in sources:
                at = self.node[s]
                if at is None or s in passed:
                    continue
                kind = self.maps.kinds.get(at.type, OUT)
                if kind == STOP:
                    stops.add(s)
                elif kind in (THROUGH, END) or self.maps.citations.get(at.type):
                    level.add(s)
        return stops

    def joins_touching(self, ids: set[str]) -> dict[tuple[str, str], float]:
        """Every join one of whose ends is among these stops, at its weight"""
        self.nodes(ids)
        starts = {i for i in ids if self.maps.is_in(self.node[i])}
        others = self.above(starts) - starts
        self.below(starts | others)
        found: dict[tuple[str, str], float] = {}
        for start in sorted(starts):
            self.joins_from(start, found)
        beside: dict[tuple[str, str], float] = {}
        for start in sorted(others):
            self.joins_from(start, beside)
        for key, weight in beside.items():
            if (key[0] in starts or key[1] in starts) and weight > found.get(key, 0.0):
                found[key] = weight
        return found


def joins(reader: Reader, maps: GraphMaps, starts: Iterable[str] | None = None) -> dict[tuple[str, str], float]:
    """The joins of the whole graph (no `starts`), or every join that touches one of `starts`: `(a, b) → weight`,
    `a < b`"""
    seen = _Seen(reader, maps)
    if starts is not None:
        return seen.joins_touching(set(starts))
    for node in reader.nodes(None):
        seen.node[node.id] = node
    everything = sorted(seen.node)
    seen.below(everything)
    found: dict[tuple[str, str], float] = {}
    for start in everything:
        seen.joins_from(start, found)
    return found


_GOLDEN = np.uint64(0x9E3779B97F4A7C15)


def seeds(ids: Sequence[str], dimension: int) -> np.ndarray:
    """The vector each id starts from: -1, 0 or 1 (a sixth, two thirds, a sixth), from a hash of the id alone, so
    that it is the same in every engine, on every run and whatever else is read with it"""
    numbers = np.array(
        [int.from_bytes(hashlib.blake2b(i.encode(), digest_size=8).digest(), "little") for i in ids],
        dtype=np.uint64,
    )
    with np.errstate(over="ignore"):
        z = numbers[:, None] + np.arange(1, dimension + 1, dtype=np.uint64)[None, :] * _GOLDEN
        z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        z = z ^ (z >> np.uint64(31))
    sixth = z % np.uint64(6)
    return np.where(sixth == 0, -1.0, np.where(sixth == 1, 1.0, 0.0))


def embed(ids: Sequence[str], weights: Mapping[tuple[str, str], float], maps: GraphMaps) -> np.ndarray:
    """FastRP over these nodes and joins: a row for each id, in the order given. (A row is right only if every
    join of the nodes its steps reach is among `weights`: `rebuild` gives all, `refresh` returns only such rows)"""
    index = {i: n for n, i in enumerate(ids)}
    rows, columns, values = [], [], []
    for (a, b), weight in sorted(weights.items()):
        if a in index and b in index:
            rows += [index[a], index[b]]
            columns += [index[b], index[a]]
            values += [weight, weight]
    n = len(ids)
    matrix = sp.csr_matrix((values, (rows, columns)), shape=(n, n), dtype=np.float64)
    degree = np.asarray(matrix.sum(axis=1)).ravel()
    inverse = np.where(degree > 0, 1.0 / np.maximum(degree, 1e-300), 0.0)[:, None]
    x = seeds(ids, maps.dimension)
    result = np.zeros((n, maps.dimension))
    for weight in maps.steps:
        x = (matrix @ x) * inverse
        length = np.linalg.norm(x, axis=1, keepdims=True)
        x = x / np.maximum(length, 1e-300)
        result += weight * x
    return result


def rebuild(reader: Reader, maps: GraphMaps) -> dict[str, np.ndarray]:
    """The vector of every stop that is joined to something"""
    weights = joins(reader, maps)
    ids = sorted({i for key in weights for i in key})
    made = embed(ids, weights, maps)
    return {i: made[n] for n, i in enumerate(ids)}


@dataclass
class Refreshed:
    vectors: dict[str, np.ndarray]
    """The vectors the change can have altered, as they now are"""
    gone: set[str]
    """Of those, the ones that now have no vector (out of the graph, or joined to nothing)"""
    read: int
    """How many nodes were read"""


class TooLarge(Exception):
    """The neighbourhood of a change passed the cap"""

    def __init__(self, reached: int):
        super().__init__(f"The neighbourhood of the change holds more than {reached} nodes")
        self.reached = reached


def refresh(reader: Reader, maps: GraphMaps, changed: Iterable[str], cap: int | None = None) -> Refreshed:
    """The vectors a change can have altered, exactly as a rebuild would give them. `changed` is every stop whose
    joins may differ from before: the stops written, and both ends of every join made, lost or reweighted (so what
    a document named before as well as what it names now). Raises `TooLarge` past `cap` nodes"""
    k = len(maps.steps)
    seen = _Seen(reader, maps)
    centre = set(changed)
    distance = {i: 0 for i in centre}
    weights: dict[tuple[str, str], float] = {}
    ring = set(centre)
    # (the rows of the nodes within 2k - 2 are wanted whole; their neighbours are the nodes within 2k - 1)
    for step in range(1, 2 * k):
        if not ring:
            break
        found = seen.joins_touching(ring)
        weights.update(found)
        following = set()
        for a, b in found:
            for i in (a, b):
                if i not in distance:
                    distance[i] = step
                    following.add(i)
        if cap is not None and len(distance) > cap:
            raise TooLarge(cap)
        ring = following
    ids = sorted(distance)
    made = embed(ids, weights, maps)
    degree = dict.fromkeys(ids, 0.0)
    for (a, b), weight in weights.items():
        degree[a] += weight
        degree[b] += weight
    vectors, gone = {}, set()
    for n, i in enumerate(ids):
        if distance[i] > k - 1:
            continue
        if degree[i] > 0:
            vectors[i] = made[n]
        else:
            gone.add(i)
    return Refreshed(vectors, gone, seen.read)


class Overlaid:
    """A reader with nodes and edges laid over another's, as a write not yet made would leave them: `nodes` are
    added or replace those of their ids, `removed` ids are gone with their edges, `edges` are added"""

    def __init__(self, base: Reader, nodes: Iterable[Node], edges: Iterable[Edge], removed: Iterable[str] = ()):
        self.base = base
        self.added = {node.id: node for node in nodes}
        self.removed = set(removed) - set(self.added)
        self.replaced = set(self.added) | self.removed
        self.extra = list(edges)

    def nodes(self, ids: Iterable[str] | None = None) -> Iterable[Node]:
        if ids is None:
            kept = [n for n in self.base.nodes(None) if n.id not in self.replaced]
            return kept + list(self.added.values())
        wanted = list(ids)
        kept = [n for n in self.base.nodes([i for i in wanted if i not in self.replaced])]
        return kept + [self.added[i] for i in wanted if i in self.added]

    def out_edges(self, ids: Iterable[str]) -> Iterable[Edge]:
        wanted = set(ids)
        # (a node of the overlay has only the overlay's edges: an update replaces everything below its head)
        kept = [
            e
            for e in self.base.out_edges(sorted(wanted - self.replaced))
            if e.target not in self.removed
        ]
        return kept + [e for e in self.extra if e.source in wanted]

    def in_edges(self, ids: Iterable[str]) -> Iterable[Edge]:
        wanted = set(ids)
        kept = [e for e in self.base.in_edges(sorted(wanted - self.removed)) if e.source not in self.replaced]
        return kept + [e for e in self.extra if e.target in wanted]

    def citing(self, ids: Iterable[str]) -> Iterable[str]:
        wanted = set(ids)
        kept = [i for i in self.base.citing(sorted(wanted)) if i not in self.replaced]
        return kept + [n.id for n in self.added.values() if n.cites in wanted]


def overlay(
    reader: Reader,
    maps: GraphMaps,
    nodes: Sequence[Node],
    edges: Sequence[Edge],
    removed: Iterable[str] = (),
    cap: int | None = None,
) -> dict[str, np.ndarray]:
    """The vectors the stops among `nodes` would have were these nodes and edges written (and `removed` taken
    away), as a rebuild after the write would give them; nothing is written. A stop joined to nothing has none"""
    laid = Overlaid(reader, nodes, edges, removed)
    wanted = [node.id for node in nodes if maps.is_in(node)]
    made = refresh(laid, maps, wanted, cap)
    return {i: made.vectors[i] for i in wanted if i in made.vectors}
