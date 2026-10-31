"""Building a document as a tree, from the nodes and edges that the read query returns.

A relation is stored as a node's forward edge (named after the field) to the
related node, so a document is a tree: each node has, under the name of each of its
fields, a list of what it is related to. The read query returns the root node and
the forward edges of the tree:

    {"source": <id>, "type": <field name>, "properties": {...},
     "target": {...properties of the node}, "target_labels": [...]}

`build_tree` makes these into nested dicts, as the `View` models of Pangloss expect.
(Entities are not expanded: they are references.)
"""

import typing

# Properties of an edge that are not those of an `EdgeModel`
INTERNAL_EDGE_PROPERTIES = {"reverse"}


def build_tree(
    root: dict[str, typing.Any],
    root_labels: list[str],
    edges: list[dict[str, typing.Any]],
) -> dict[str, typing.Any]:
    edges_from: dict[str, list[dict[str, typing.Any]]] = {}
    for edge in edges:
        edges_from.setdefault(edge["source"], []).append(edge)

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
