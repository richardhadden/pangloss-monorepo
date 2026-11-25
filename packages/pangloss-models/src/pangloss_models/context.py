"""The path of the nodes of a document, and what is made from it.

A node's **path** is the nodes it is nested in, from the head of its document down to the node that holds it,
each an entry `{kind, type, id, field}`: `kind` is what the node is (`document`, `entity`, `space`, `reified`,
`conjunction`, `embedded`), and `field` the relation of that node through which the next is held. Every node on
the way is in it. The head's path is empty; an entity is a head wherever it is met, so its path is empty too.

A child's path is its parent's path and the parent: nothing is shared between nodes, the order of a class's fields
does not matter, and a node is never in its own path. The models work the paths out for an instance they are about
to write (`pangloss_models.model_bases.instance_context`), and a migration for the nodes of a document that is
stored. It is one algorithm, here; each says how to look at what it has (`ContextView`).

`semantic_spaces`, the types of the spaces a node is in, outermost first, is made from the path (`spaces_of`). It
is what a query filters by.

`context_labels` is the older record, still written until its readers are moved to the path
(implementation_docs/spaces-and-comparison-plan.md, steps 1.2 and 1.3): here it is made from the path too
(`labels_of`), so it holds what a node is nested in and nothing else.
"""

from collections.abc import Callable, Iterable
from typing import Any, Protocol, TypedDict

DOCUMENT, ENTITY, SPACE = "document", "entity", "space"
REIFIED, CONJUNCTION, EMBEDDED = "reified", "conjunction", "embedded"
KINDS = (DOCUMENT, ENTITY, SPACE, REIFIED, CONJUNCTION, EMBEDDED)

# The kind of each kind of declared class (its `__metatype__`, the `kind` of a model in a snapshot)
KIND_OF = {
    "Document": DOCUMENT,
    "Entity": ENTITY,
    "SemanticSpace": SPACE,
    "ReifiedRelation": REIFIED,
    "ReifiedRelationDocument": REIFIED,
    "Conjunction": CONJUNCTION,
    "Embedded": EMBEDDED,
}


class PathEntry(TypedDict):
    """A node that another is nested in"""

    kind: str
    type: str
    id: str
    field: str
    """The relation of this node through which the next of the path (or the node itself) is held"""


class ContextView(Protocol):
    """How a node is looked at"""

    def is_entity(self, node: Any) -> bool:
        """An entity belongs to no document: its path is empty, and what it holds starts from it"""

    def kind_of(self, node: Any) -> str:
        """One of `KINDS`"""

    def type_of(self, node: Any) -> str: ...

    def id_of(self, node: Any) -> str: ...

    def children(self, node: Any) -> Iterable[tuple[str, Any]]:
        """What the node holds, each with the name of the field that holds it"""

    def assign(self, node: Any, path: list[PathEntry]) -> None:
        """Give the node its path (a list of its own)"""


def propagate_context(node: Any, view: ContextView) -> None:
    """Work out the path of a head node and of everything it holds, and give each its own (`view.assign`)"""
    _propagate(node, [], view)


def _propagate(node: Any, path: list[PathEntry], view: ContextView) -> None:
    if path and view.is_entity(node):
        path = []
    view.assign(node, [*path])
    for field, child in view.children(node):
        entry: PathEntry = {
            "kind": view.kind_of(node),
            "type": view.type_of(node),
            "id": view.id_of(node),
            "field": field,
        }
        _propagate(child, [*path, entry], view)


def spaces_of(path: Iterable[PathEntry]) -> list[str]:
    """`semantic_spaces`: the types of the spaces of a path, outermost first"""
    return [entry["type"] for entry in path if entry["kind"] == SPACE]


def labels_of(
    path: Iterable[PathEntry], in_context: Callable[[str], bool]
) -> list[dict]:
    """`context_labels`, in the shape its readers know, from a path: a label for each space, and in the innermost
    (or in `#rootcontext` where there is none yet) the nested documents on the way whose class `in_context` says
    are shown. The head is not a part of it. Kept only until the readers read the path"""
    labels: list[dict] = []
    for position, entry in enumerate(path):
        if entry["kind"] == SPACE:
            labels.append({"type": entry["type"]})
        elif position and entry["kind"] == DOCUMENT and in_context(entry["type"]):
            if not labels:
                labels.append({"type": "#rootcontext"})
            labels[-1].setdefault("contents", []).append(
                {"type": entry["type"], "id": entry["id"]}
            )
    return labels
