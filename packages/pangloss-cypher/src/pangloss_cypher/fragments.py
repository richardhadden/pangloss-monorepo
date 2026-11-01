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
