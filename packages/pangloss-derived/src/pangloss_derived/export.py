"""The edges of a type of rule as a file for a graph tool: GraphML, which Gephi, Cytoscape and networkx read.

`graphml(edges)` takes what `read.graph(type)` gives. Each entity at an end is a node (its id, label and class); each
derived edge is an edge from its subject to its object, undirected if its class is symmetric, with its class, its
weight (how many justifications it has), whether it is plain, its context labels, its status (what its
justifications say, summed up: `pangloss_derived.status.summed`), and its qualifiers (`q_<name>`: a value, or the
label of an entity, with its id as `q_<name>_id`).
"""

import datetime
from typing import Any
from xml.sax.saxutils import escape, quoteattr

NAMESPACE = "http://graphml.graphdrawing.org/xmlns"

# (the attributes every edge and node has: their key, name and type)
NODE_KEYS = (("n_label", "label", "string"), ("n_type", "type", "string"))
EDGE_KEYS = (
    ("e_class", "class", "string"),
    ("e_weight", "weight", "int"),
    ("e_justifications", "justifications", "int"),
    ("e_plain", "plain", "boolean"),
    ("e_context", "context", "string"),
    ("e_status", "status", "string"),
)


def graphml_type(value: Any) -> str:
    """The GraphML type of a value of a qualifier"""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "long"
    if isinstance(value, float):
        return "double"
    return "string"


def text_of(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return str(value)


def is_ref(value: Any) -> bool:
    return isinstance(value, dict) and "id" in value


def qualifier_keys(edges: list[dict[str, Any]]) -> dict[str, str]:
    """The keys of the qualifiers of the edges, each with its type: a name two classes use for values of two types is
    text"""
    keys: dict[str, str] = {}
    for edge in edges:
        for name, value in edge.get("attributes", {}).items():
            if value is None:
                continue
            if is_ref(value):
                keys.setdefault(f"q_{name}", "string")
                keys.setdefault(f"q_{name}_id", "string")
                continue
            kind = graphml_type(value)
            if keys.setdefault(f"q_{name}", kind) != kind:
                keys[f"q_{name}"] = "string"
    return keys


def data(key: str, value: Any) -> str:
    return f"      <data key={quoteattr(key)}>{escape(text_of(value))}</data>"


def graphml(edges: list[dict[str, Any]], name: str = "derived") -> str:
    """The edges (as `read.graph` gives them) as a GraphML document"""
    qualifiers = qualifier_keys(edges)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<graphml xmlns="{NAMESPACE}">',
    ]
    for key, attribute, kind in NODE_KEYS:
        lines.append(
            f'  <key id="{key}" for="node" attr.name="{attribute}" attr.type="{kind}"/>'
        )
    for key, attribute, kind in EDGE_KEYS:
        lines.append(
            f'  <key id="{key}" for="edge" attr.name="{attribute}" attr.type="{kind}"/>'
        )
    for key, kind in qualifiers.items():
        lines.append(
            f'  <key id={quoteattr(key)} for="edge" attr.name={quoteattr(key[2:])} attr.type="{kind}"/>'
        )
    # (directed unless every edge is of a symmetric class; an edge says so itself when it differs from the graph)
    directed = any(not edge.get("symmetric") for edge in edges)
    default = "directed" if directed else "undirected"
    lines.append(f'  <graph id={quoteattr(name)} edgedefault="{default}">')
    nodes: dict[str, dict[str, Any]] = {}
    for edge in edges:
        for end in (edge["source"], edge["target"]):
            nodes.setdefault(str(end["id"]), end)
    for node_id, node in nodes.items():
        lines.append(f"    <node id={quoteattr(node_id)}>")
        lines.append(data("n_label", node.get("label") or node_id))
        lines.append(data("n_type", node.get("type") or ""))
        lines.append("    </node>")
    for edge in edges:
        symmetric = bool(edge.get("symmetric"))
        own = (
            "" if symmetric != directed else f' directed="{str(not symmetric).lower()}"'
        )
        lines.append(
            f"    <edge id={quoteattr(str(edge['id']))} source={quoteattr(str(edge['source']['id']))} "
            f"target={quoteattr(str(edge['target']['id']))}{own}>"
        )
        lines.append(data("e_class", edge["class"]))
        lines.append(
            data("e_weight", edge.get("weight", edge.get("justifications", 1)))
        )
        lines.append(data("e_justifications", edge.get("justifications", 1)))
        lines.append(data("e_plain", bool(edge.get("plain"))))
        lines.append(data("e_context", "|".join(edge.get("context_labels") or [])))
        lines.append(data("e_status", edge["status"]))
        for attribute, value in edge.get("attributes", {}).items():
            if value is None:
                continue
            if is_ref(value):
                lines.append(data(f"q_{attribute}", value.get("label") or value["id"]))
                lines.append(data(f"q_{attribute}_id", value["id"]))
            else:
                kind = qualifiers[f"q_{attribute}"]
                lines.append(
                    data(
                        f"q_{attribute}", value if kind != "string" else text_of(value)
                    )
                )
        lines.append("    </edge>")
    lines.append("  </graph>")
    lines.append("</graphml>")
    return "\n".join(lines) + "\n"
