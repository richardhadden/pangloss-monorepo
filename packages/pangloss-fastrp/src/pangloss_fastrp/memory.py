"""A graph held in memory that fills in `maths.Reader`: what a whole rebuild reads the database into
(`cypher_reader.load_all`), and what the tests build graphs in (`pangloss_fastrp.testing`)"""

from collections import defaultdict
from collections.abc import Iterable

from pangloss_fastrp.maths import Edge, Node


class MemoryReader:
    def __init__(self, nodes: Iterable[Node] = (), edges: Iterable[Edge] = ()):
        self.node: dict[str, Node] = {}
        self.out: dict[str, list[Edge]] = defaultdict(list)
        self.into: dict[str, list[Edge]] = defaultdict(list)
        for node in nodes:
            self.add(node)
        for edge in edges:
            self.link(edge)

    def add(self, node: Node) -> Node:
        self.node[node.id] = node
        return node

    def link(self, edge: Edge) -> Edge:
        self.out[edge.source].append(edge)
        self.into[edge.target].append(edge)
        return edge

    def unlink(self, edge: Edge) -> None:
        self.out[edge.source].remove(edge)
        self.into[edge.target].remove(edge)

    def remove(self, id: str) -> None:
        """A node and its edges, gone"""
        for edge in list(self.out.get(id, [])) + list(self.into.get(id, [])):
            self.unlink(edge)
        self.node.pop(id, None)

    def copy(self) -> MemoryReader:
        return MemoryReader(
            self.node.values(), [e for edges in self.out.values() for e in edges]
        )

    # (the reader)
    def nodes(self, ids=None):
        if ids is None:
            return list(self.node.values())
        return [self.node[i] for i in ids if i in self.node]

    def out_edges(self, ids):
        return [e for i in ids for e in self.out.get(i, [])]

    def in_edges(self, ids):
        return [e for i in ids for e in self.into.get(i, [])]

    def citing(self, ids):
        wanted = set(ids)
        return [n.id for n in self.node.values() if n.cites in wanted]
