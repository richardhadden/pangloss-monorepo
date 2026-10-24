"""The semantic spaces and context labels of the nodes of a document.

A node is in the semantic spaces above it, and its context is made of the spaces it is in and, in the
innermost (or in a root context if it is in none), the documents that are a part of its context. The
models work this out for an instance they are about to write (`recursively_propagate_context_types`),
and a migration for the nodes of a document that is already stored. It is one algorithm, here; each
says how to look at what it has (`ContextView`).

How the lists are shared is part of it, and is kept: what a single relation holds is given the lists
of the node (so what is added to the context below it is seen by what comes after), while each item
of a list is given a copy (so that the items do not see each other's).
"""

from collections.abc import Iterable
from copy import copy, deepcopy
from typing import Any, Protocol


class ContextView(Protocol):
    """How a node is looked at"""

    def is_entity(self, node: Any) -> bool:
        """An entity belongs to no document: it is a context of its own"""

    def is_space(self, node: Any) -> bool:
        """A semantic space: it adds itself to the context of what it holds"""

    def in_context(self, node: Any) -> bool:
        """A document that is a part of the context of what it holds, when it is nested in another"""

    def type_of(self, node: Any) -> str: ...

    def id_of(self, node: Any) -> str: ...

    def children(self, node: Any) -> Iterable[tuple[Any, bool]]:
        """What the node holds through its relations, each with whether it is one of a list"""

    def assign(
        self, node: Any, semantic_spaces: list[str], context_labels: list[dict]
    ) -> None:
        """Give the node its semantic spaces and context labels (not called for a space)"""


def propagate_context(
    node: Any,
    semantic_spaces: list[str],
    context_labels: list[dict],
    parent: Any,
    view: ContextView,
) -> None:
    """Work out the semantic spaces and context labels of a node and of what it holds, and give them
    to the nodes (`view.assign`). `parent` is None for the head of a document."""
    if parent is not None and view.is_entity(node):
        semantic_spaces, context_labels = [], []

    if not view.is_space(node):
        view.assign(node, [*semantic_spaces], [*context_labels])

    if view.is_space(node):
        semantic_spaces.append(view.type_of(node))
        context_labels.append({"type": view.type_of(node)})
    elif parent is not None and view.in_context(node):
        entry = {"type": view.type_of(node), "id": view.id_of(node)}
        if context_labels:
            if not context_labels[-1].get("contents", None):
                context_labels[-1]["contents"] = []
            context_labels[-1]["contents"].append(entry)
        else:
            context_labels.append({"type": "#rootcontext", "contents": [entry]})

    for child, many in view.children(node):
        if many:
            propagate_context(
                child, copy(semantic_spaces), deepcopy(context_labels), node, view
            )
        else:
            propagate_context(child, semantic_spaces, context_labels, node, view)
