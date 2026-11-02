"""Building a document as a tree, from the nodes and edges that the read query returns.

A relation is stored as a node's forward edge (named after the field) to the
related node, so a document is a tree: each node has, under the name of each of its
fields, a list of what it is related to, in the order it was written (`pg_position` on
the edge). The read query returns the root node and
the forward edges of the tree:

    {"source": <id>, "type": <field name>, "properties": {...},
     "target": {...properties of the node}, "target_labels": [...]}

`build_tree` makes these into nested dicts, as the `View` models of Pangloss expect.
(Entities are not expanded: they are references.)

What a read gives is a `GraphFragment`: the root, its labels, the edges and the `meta`. Nothing of it is Cypher: it is
what a backend of another kind would give as well.
"""

import dataclasses
import typing

# The edge property of a value's place in the list of its field, from 0: written on the forward edges (`render_write`,
# and by the migrations that make edges), and read here to put each list in its order
POSITION = "pg_position"

# Properties of an edge that are not those of an `EdgeModel`
INTERNAL_EDGE_PROPERTIES = {"reverse", POSITION}


def _list_order(edge: dict[str, typing.Any]) -> tuple[bool, int, str]:
    """Where an edge's value goes in the list of its field: by its place as written (`pg_position`); one written
    before there were places, after those, by the id of what it is to (ids are made in time order, so the nodes of a
    document made at once are in the order they were in)"""
    position = edge["properties"].get(POSITION)
    return (
        position is None,
        position if isinstance(position, int) else 0,
        str(edge["target"].get("id", "")),
    )


def build_tree(
    root: dict[str, typing.Any],
    root_labels: list[str],
    edges: list[dict[str, typing.Any]],
) -> dict[str, typing.Any]:
    edges_from: dict[str, list[dict[str, typing.Any]]] = {}
    for edge in edges:
        edges_from.setdefault(edge["source"], []).append(edge)
    # (the query gives the edges in no order: each list in the order it was written)
    for outgoing in edges_from.values():
        outgoing.sort(key=_list_order)

    def build(properties: dict[str, typing.Any], labels: list[str]) -> dict:
        node = dict(properties)
        if "Entity" in labels and properties is not root:
            return node

        for edge in edges_from.get(properties["id"], []):
            child = build(edge["target"], edge["target_labels"])

            # The properties of an edge (ViaEdge) are those of the model
            edge_properties = {
                key: value
                for key, value in edge["properties"].items()
                if key not in INTERNAL_EDGE_PROPERTIES
            }
            if edge_properties:
                child["edge_properties"] = edge_properties

            node.setdefault(edge["type"], []).append(child)
        return node

    return build(root, root_labels)


@dataclasses.dataclass(frozen=True)
class GraphFragment:
    """What a read of a document or an entity gives: the root node's properties and labels, the forward edges of the
    tree below it (as `build_tree` takes them), and its `meta`"""

    root: dict[str, typing.Any]
    labels: list[str]
    edges: list[dict[str, typing.Any]]
    meta: dict[str, typing.Any]

    @classmethod
    def from_record(cls, record: dict[str, typing.Any]) -> "GraphFragment":
        """From a row of the read query (`read_query.build_fetch_document_query`)"""
        return cls(
            root=record["root"],
            labels=record["root_labels"],
            edges=record["edges"],
            meta=record["meta"],
        )

    def tree(self) -> dict[str, typing.Any]:
        """The document, as the `View` models take it"""
        tree = build_tree(self.root, self.labels, self.edges)
        tree["meta"] = self.meta
        return tree
