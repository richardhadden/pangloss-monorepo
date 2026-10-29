"""Walking the graph the way Pangloss stores it, in Neo4j's pattern syntax.

Memgraph walks with `-[*BFS (edge, node | condition)]->` and `-[* 0.. (edge, node | condition)]->`: a path of any length,
every edge and the node it reaches tested. In Neo4j that is a *quantified path pattern*: `((from)-[edge]->(to) WHERE
condition)+`, written between the node patterns it joins. (It finds every path, where BFS found a shortest one to each node;
the tree below a node is a tree, and where a node is reached twice the queries take each node and each edge once.)

The variables inside a quantified pattern are group variables of the whole query, so each use is given names of its own.
"""


def quantifier(minimum: int, maximum: int | None) -> str:
    if (minimum, maximum) == (1, None):
        return "+"
    if (minimum, maximum) == (0, None):
        return "*"
    return f"{{{minimum},{'' if maximum is None else maximum}}}"


def hops(
    name: str,
    condition: str,
    *,
    minimum: int = 1,
    maximum: int | None = None,
    backwards: bool = False,
) -> str:
    """Hops of one edge each, repeated, while `condition` holds of the edge (`{name}_edge`) and the node it reaches
    (`{name}_to`): to be written between two node patterns, `(a) {hops("t", "...")} (b)`. `backwards` follows the edges
    against their direction, from the node they point at."""
    edge, start, end = f"{name}_edge", f"{name}_from", f"{name}_to"
    link = (
        f"({start})<-[{edge}]-({end})" if backwards else f"({start})-[{edge}]->({end})"
    )
    return f"({link} WHERE {condition}){quantifier(minimum, maximum)}"


def below(name: str, *, minimum: int = 1) -> str:
    """Down the tree of a document: forward edges (a relation is stored as a forward edge and a reverse one marked
    `reverse: true`, which is not followed), not into an entity or the URL of one"""
    edge, end = f"{name}_edge", f"{name}_to"
    return hops(
        name,
        f"NOT {end}:Entity AND NOT {end}:PGUrl AND NOT coalesce({edge}.reverse, false)",
        minimum=minimum,
    )


def up(name: str, *, minimum: int = 1, maximum: int | None = None) -> str:
    """Up from a node to what holds it: along the reverse edges"""
    return hops(
        name,
        f"coalesce({name}_edge.reverse, false)",
        minimum=minimum,
        maximum=maximum,
    )
