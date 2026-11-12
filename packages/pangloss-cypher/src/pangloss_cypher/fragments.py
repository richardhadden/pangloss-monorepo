"""Pieces of Cypher that know how the models are stored: the one rule of what a reader sees, the head node of a node,
and checked names. The kit's queries are built with them, and so are the queries of the add-ons that read model data
(typology, calendar), through `pangloss_core.backend` (`backend.current().fragments`).

The rule of what is seen:

- what has been deleted is not seen: an entity that is deleted, or any node of a document whose head node is deleted;
- a document that is not published is seen only by a reader who may see what is not published (`$see_unpublished`,
  from `unpublished_visible()`). An entity is always published;
- a list may also ask for only what is (or is not) published (`$published`), or in a state of review
  (`$review_status`): `visible(..., filters=True)`. A null parameter asks for nothing.

A query that uses `visible` must give `$see_unpublished` (and, with `filters`, `$published` and `$review_status`).

What is **listed** is narrower than what is seen (`listed`): an entity that has been merged into another
(`merged_into`, implementation_docs/entity-identity.md) is seen wherever an edge still points at it, but it is not listed, searched for,
offered, or counted as something that refers to another. Use `visible` for what a document shows, `listed` for what
a reader looks through.
"""

import dataclasses
import re

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclasses.dataclass(frozen=True)
class HeadOf:
    """The head node of the node `node`, found by its `head_node_id` as `name`. In a query it is written as the head node,
    or the node itself if it is a head node (`coalesce(name, node)`); `match` finds it:

    ```python
    head = head_of("n", "n_head")
    f"{head.match} WITH n, {head.name} WHERE {visible('n', head)}"
    ```"""

    node: str
    name: str

    @property
    def match(self) -> str:
        return f"OPTIONAL MATCH ({self.name}:HeadNode {{id: {self.node}.head_node_id}})"

    def __str__(self) -> str:
        return f"coalesce({self.name}, {self.node})"


def head_of(node: str, as_: str) -> HeadOf:
    """The head node of `node`, which the query finds as `as_` (see `HeadOf`)"""
    return HeadOf(node, as_)


def creators(creation: str) -> str:
    """An expression: those who made a head node, from the record of its creation (`PGCreation`): a list of maps, one
    for each `created_by` edge, with its place among them (`position`; the models put them in order). None for a
    record that is not there"""
    return (
        f"[({creation})-[made_by:created_by]->(maker:PGUser) | {{username: maker.username, "
        "kind: coalesce(maker.kind, 'user'), version: made_by.version, date: made_by.date, "
        "position: coalesce(made_by.position, 0)}]"
    )


def deleted(node: str) -> str:
    """An expression: whether the node is deleted"""
    return f"coalesce({node}.deleted, false)"


def not_deleted(node: str) -> str:
    """A condition: the node is not deleted (of an entity, all there is to whether it is seen)"""
    return f"NOT {deleted(node)}"


def published(head: str | HeadOf) -> str:
    """An expression: whether the head node is published (what is not marked is)"""
    return f"coalesce({head}.published, true)"


def visible(
    node: str, head: str | HeadOf | None = None, *, filters: bool = False
) -> str:
    """A condition: the reader sees `node`.

    With no `head`, `node` is a head node (a document or an entity). With `head` (an expression for the head node of
    `node`, or `node` itself if it is one: a `HeadOf`), `node` may be any node, and if it is an entity only whether it
    is deleted counts. `filters`: also what a list asks for, by `$published` and `$review_status`."""
    if head is None:
        return f"{not_deleted(node)} AND ($see_unpublished OR {published(node)})"
    lines = [
        f"NOT coalesce(CASE WHEN {node}:Entity THEN {node}.deleted ELSE {head}.deleted END, false)",
        f"AND ({node}:Entity OR $see_unpublished OR {published(head)})",
    ]
    if filters:
        lines += [
            f"AND ($published IS NULL OR {published(head)} = $published)",
            f"AND ($review_status IS NULL OR {head}.review_status = $review_status)",
        ]
    return "\n".join(lines)


def not_merged(node: str) -> str:
    """A condition: the node is not an entity that has been merged into another"""
    return f"{node}.merged_into IS NULL"


def listed(
    node: str, head: str | HeadOf | None = None, *, filters: bool = False
) -> str:
    """A condition: `node` is among what a reader looks through (a list, a search, what is offered while typing, what
    refers to an entity): the reader sees it (`visible`, with the same arguments), and it is not an entity that has
    been merged into another"""
    return f"{visible(node, head, filters=filters)}\nAND {not_merged(node)}"


def uses_of(node: str) -> str:
    """A subquery that gives `uses`, how many things the reader sees refer to `node` (the node must be in the query
    already; `$see_unpublished` must be given). What refers to it is the reverse edges leading out of it (as for
    whether it can be deleted), each node once: a field that narrows another is two edges to the same node. What is
    inside a deleted or unpublished document does not count, nor does a node referring to itself, nor what an entity
    that was merged into another still refers to.

    (Measured, 691k nodes: 90 ms for all 18,571 items of a class, 9 ms for a page of 50; it costs what the items have
    edges, nothing is scanned.)"""
    head = head_of("used_by", "used_head")
    return f"""
    CALL ({node}) {{
      MATCH ({node})-[used_edge]->(used_by)
      WHERE coalesce(used_edge.reverse, false)
      {head.match}
      WITH {node}, used_by, CASE WHEN used_by:Entity THEN used_by ELSE {head} END AS holder
      WHERE {listed("holder")} AND holder <> {node}
      RETURN count(DISTINCT used_by) AS uses
    }}
"""


def only_used(node: str, *carried: str) -> str:
    """What a query puts after it has `node` and the variables `carried` to keep only what something refers to"""
    kept = ", ".join((node, *carried))
    return f"""{uses_of(node)}
    WITH {kept}, uses
    WHERE uses > 0
    WITH {kept}
"""


def hidden(head: str) -> str:
    """A condition: the reader does not see the head node `head` (the negation of `visible(head)`, written so that it
    is true or null, for a `NOT EXISTS` that finds a head node which hides what is below it)"""
    return f"{head}.deleted OR NOT ($see_unpublished OR {published(head)})"


def _checked(name: str, what: str) -> str:
    if not _IDENTIFIER.match(name):
        raise ValueError(f"{name!r} is not {what}")
    return f"`{name}`"


def label(name: str) -> str:
    """A label, for a pattern (`(n:{label(name)})`), if `name` can be the name of a class"""
    return _checked(name, "the name of a class")


def field_edge(field: str) -> str:
    """The type of the edge of a field, for a pattern (`-[:{field_edge(field)}]->`), if `field` can be the name of one"""
    return _checked(field, "the name of a field")


def property_name(name: str) -> str:
    """A property of a node, for an expression (`n.{property_name(name)}`), if `name` can be the name of one"""
    return _checked(name, "the name of a property")


def derived_visible(fact: str) -> str:
    """A condition: the reader sees the derived fact `fact` (`pangloss-derived`): one of its justifications rests only on
    head nodes the reader sees (`visible`), and none of the entities it relates is deleted or merged into another. So a deleted or unpublished
    document hides what it alone justifies at once, before the derivations have been worked out again. The query must
    give `$see_unpublished`.

    (Each justification's evidence is gathered in the comprehension that finds the justification: Memgraph evaluates
    a pattern comprehension on the variable of an enclosing quantifier, `any(j IN ... WHERE all(h IN [(j)-->(h) | h]
    ...))`, wrongly, so that one deleted document hid every fact of an entity until the worker had run.)"""
    return (
        f"any(evidence IN [({fact})<-[:justifies]-(j:PGJustification) | [(j)-[:evidence]->(h) | h]] "
        f"WHERE all(h IN evidence WHERE {visible('h')})) "
        f"AND all(e IN [({fact})-[]->(e:Entity) | e] WHERE {not_deleted('e')} AND {not_merged('e')})"
    )
