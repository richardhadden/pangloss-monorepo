"""A graph held in memory, for the tests of every engine: `MemoryReader` fills in `maths.Reader`, and
`oracle(graph, maps)` is the slow, plain answer (a whole rebuild by the pure maths) that every other way of making
the vectors must equal. `World` makes a random graph with every shape the rules name, and edits it."""

import random
from collections import defaultdict
from collections.abc import Iterable

import numpy as np

from pangloss_fastrp.maths import Edge, GraphMaps, Node, rebuild


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
        return MemoryReader(self.node.values(), [e for edges in self.out.values() for e in edges])

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


def oracle(graph: MemoryReader, maps: GraphMaps) -> dict[str, np.ndarray]:
    return rebuild(graph, maps)


WORLD_MAPS = GraphMaps(
    kinds={
        "Person": "stop",
        "Place": "stop",
        "Factoid": "stop",
        "Event": "stop",
        "Gift": "stop",
        "Derived": "out",
        "InRole": "through",
        "Sworn": "through",
        "Identification": "through",
        "Alternative": "through",
        "Matches": "through",
        "Same": "through",
        "Negative": "end",
        "Quiet": "through",
        "PGCitation": "out",
    },
    class_weight={"Gift": 2.0, "Sworn": 0.5},
    held={
        "InRole": ["target"],
        "Sworn": ["target"],
        "Identification": ["target"],
        "Alternative": ["alternatives"],
        "Matches": ["target"],
        "Same": ["target"],
        "Negative": ["contents"],
        "Quiet": ["target"],
    },
    own={"Quiet": False},
    field_weight={"Event.place": 0.5, "InRole.at": 0.7},
    shares={"Alternative.alternatives": ["percent", 100]},
    citations={"PGCitation": True},
    dimension=32,
)


class World:
    """A random graph of people, places and documents in the shapes of `pangloss_testing.similar_models`, and
    random edits of it. Everything comes from the seed"""

    def __init__(self, seed: int, people: int = 300, documents: int = 300):
        self.random = random.Random(seed)
        self.graph = MemoryReader()
        self.count = 0
        self.people = [self.stop("Person") for _ in range(people)]
        self.places = [self.stop("Place") for _ in range(people // 10)]
        self.documents: list[str] = []
        for _ in range(documents):
            self.document()

    def new(self, type: str, **more) -> str:
        self.count += 1
        id = f"{type.lower()}-{self.count}"
        self.graph.add(Node(id, type, **more))
        return id

    def stop(self, type: str) -> str:
        return self.new(type)

    def edge(self, source: str, target: str, field: str, **properties) -> None:
        self.graph.link(Edge(source, target, field, properties))

    def person(self) -> str:
        return self.random.choice(self.people)

    def wrapped(self, holder: str, field: str, published: bool) -> None:
        """A person in a field, plain or behind wrappers of each kind"""
        r = self.random
        shape = r.choice(["plain", "role", "sworn", "alternatives", "matches", "quiet", "same", "deep"])
        if shape == "plain":
            self.edge(holder, self.person(), field)
        elif shape in ("role", "sworn", "quiet"):
            wrapper = self.new({"role": "InRole", "sworn": "Sworn", "quiet": "Quiet"}[shape], published=published)
            self.edge(holder, wrapper, field)
            self.edge(wrapper, self.person(), "target")
            if r.random() < 0.6:
                self.edge(wrapper, r.choice(self.places), "at")
        elif shape == "alternatives":
            self.alternatives(holder, field, published)
        elif shape == "matches":
            wrapper = self.new("Matches", published=published)
            self.edge(holder, wrapper, field)
            for person in r.sample(self.people, r.randint(1, 6)):
                seen = {"seen_by": "logged_in"} if r.random() < 0.2 else {}
                self.edge(wrapper, person, "target", computed=True, **seen)
        elif shape == "same":
            wrapper = self.new("Same", published=published)
            self.edge(holder, wrapper, field)
            for person in r.sample(self.people, 2):
                self.edge(wrapper, person, "target")
        else:
            role = self.new("InRole", published=published)
            self.edge(holder, role, field)
            self.alternatives(role, "target", published)

    def alternatives(self, holder: str, field: str, published: bool) -> None:
        r = self.random
        identification = self.new("Identification", published=published)
        alternative = self.new("Alternative", published=published)
        self.edge(holder, identification, field)
        self.edge(identification, alternative, "target")
        first = r.randint(10, 90)
        for person, percent in zip(r.sample(self.people, 2), (first, 100 - first), strict=True):
            self.edge(alternative, person, "alternatives", percent=percent, pg_edge_model="Likelihood")

    def statement(self, factoid: str, published: bool) -> str:
        r = self.random
        type = r.choice(["Event", "Gift"])
        statement = self.new(type, published=published)
        for _ in range(r.randint(1, 3)):
            self.wrapped(statement, r.choice(["by", "to"]), published)
        if r.random() < 0.3:
            # (a field that narrows a parent's: the same person under two names)
            person = self.person()
            self.edge(statement, person, "carried_out_by")
            self.edge(statement, person, "involves")
        if type == "Event" and r.random() < 0.5:
            self.edge(statement, r.choice(self.places), "place")
        if r.random() < 0.15 and self.documents:
            citation = self.new("PGCitation", published=published, cites=r.choice(self.documents))
            self.edge(statement, citation, "evidence")
        # (edges a reader should not give, and the maths does not follow if it does)
        if r.random() < 0.1:
            self.edge(self.person(), statement, "by", reverse=True)
        if r.random() < 0.1:
            self.edge(self.person(), self.person(), "SameGroup", derived=True)
        return statement

    def document(self, published: bool | None = None) -> str:
        r = self.random
        if published is None:
            published = r.random() > 0.15
        factoid = self.new("Factoid", published=published)
        for _ in range(r.randint(1, 3)):
            statement = self.statement(factoid, published)
            if r.random() < 0.15:
                negative = self.new("Negative", published=published)
                self.edge(factoid, negative, "statements")
                self.edge(negative, statement, "contents")
            else:
                self.edge(factoid, statement, "statements")
        self.documents.append(factoid)
        return factoid

    def tree(self, head: str) -> list[str]:
        """A document and everything nested in it (not the entities it names)"""
        found, level = [head], [head]
        while level:
            below = [
                e.target
                for i in level
                for e in self.graph.out.get(i, [])
                if not e.properties.get("reverse")
                and not e.properties.get("derived")
                and (node := self.graph.node.get(e.target)) is not None
                and node.type not in ("Person", "Place")
                and e.target not in found
            ]
            found += below
            level = below
        return found

    def replace(self, id: str, **changes) -> None:
        old = self.graph.node[id]
        values = {name: getattr(old, name) for name in old.__dataclass_fields__} | changes
        self.graph.node[id] = Node(**values)

    def edit(self) -> str:
        """One random edit; gives what it was, in words"""
        r = self.random
        kind = r.choice(
            ["add", "remove", "change", "drop reference", "share", "candidate", "merge", "publish", "delete entity"]
        )
        live = [d for d in self.documents if d in self.graph.node]
        if kind == "add" or not live:
            return f"add {self.document()}"
        document = r.choice(live)
        if kind == "remove":
            for id in self.tree(document):
                self.graph.remove(id)
            return f"remove {document}"
        if kind == "change":
            published = self.graph.node[document].published
            for id in self.tree(document)[1:]:
                self.graph.remove(id)
            for _ in range(r.randint(1, 2)):
                self.edge(document, self.statement(document, published), "statements")
            return f"change {document}"
        if kind == "publish":
            now = not self.graph.node[document].published
            for id in self.tree(document):
                self.replace(id, published=now)
            return f"publish {document} = {now}"
        if kind == "delete entity":
            person = self.person()
            self.replace(person, deleted=not self.graph.node[person].deleted)
            return f"delete (or bring back) {person}"
        if kind == "merge":
            absorbed, survivor = r.sample(self.people, 2)
            if self.graph.node[absorbed].merged_into or self.graph.node[survivor].merged_into:
                return "merge (nothing)"
            for edge in list(self.graph.into.get(absorbed, [])):
                if edge.properties.get("reverse") or edge.properties.get("derived"):
                    continue
                self.graph.unlink(edge)
                if not edge.properties.get("computed") and self.graph.node[edge.source].type != "Same":
                    self.graph.link(Edge(edge.source, survivor, edge.field, edge.properties))
                elif self.graph.node[edge.source].type == "Same":
                    self.graph.link(edge)  # (a claim that two are one still points at the absorbed one)
            self.replace(absorbed, merged_into=survivor)
            return f"merge {absorbed} into {survivor}"
        edges = [e for id in self.tree(document) for e in self.graph.out.get(id, [])]
        if kind == "drop reference":
            named = [e for e in edges if self.graph.node[e.target].type == "Person"]
            if not named:
                return "drop reference (nothing)"
            edge = r.choice(named)
            self.graph.unlink(edge)
            return f"drop {edge.source} -{edge.field}-> {edge.target}"
        if kind == "share":
            shared = [e for e in edges if "percent" in e.properties]
            if not shared:
                return "share (nothing)"
            edge = r.choice(shared)
            siblings = [e for e in self.graph.out[edge.source] if "percent" in e.properties]
            first = r.randint(5, 95)
            for sibling, percent in zip(siblings, (first, 100 - first), strict=False):
                self.graph.unlink(sibling)
                self.graph.link(Edge(sibling.source, sibling.target, sibling.field, {**sibling.properties, "percent": percent}))
            return f"shares of {edge.source} = {first}"
        wrappers = [id for id in self.tree(document) if self.graph.node[id].type == "Matches"]
        if not wrappers:
            return "candidate (nothing)"
        wrapper = r.choice(wrappers)
        self.edge(wrapper, self.person(), "target", computed=True)
        return f"candidate added to {wrapper}"
