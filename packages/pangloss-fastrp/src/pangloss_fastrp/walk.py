"""What the second graph part, `"actual"`, makes of a document's stored path: the weight it joins at
(implementation_docs/spaces-and-comparison-plan.md, steps 5.3 and 5.4, the rule "by-walk"; implementation_docs/fastrp.md,
"The actual network").

For every stop that is a document (`GraphMaps.documents`), nested or a head, the walk
(`pangloss_models.spaces.signature`) of its stored path (`meta.path`; for a head, whose path is empty, of its class, so
that the ground of its class counts) gives

    asserted (1)                       weight 1, as in the structural network
    denied (-1)                        weight 0: out of the graph
    neither, leaning for               the weight of its degree (`FASTRP_DEGREE_WEIGHTS`; "none" where none is said)
    neither, leaning against or not    weight 0: out of the graph

and every other node (an entity, a wrapper, a citation) weight 1. A path with no space in it under a head whose
class's ground is asserted is weight 1 without a walk. The walk is asked once for each *shape* of path (the path
without its ids), so a rebuild walks a handful of shapes, not every document. No database here; `maths` (numpy) is
imported with it."""

import json
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from pangloss_fastrp.maths import STOP, GraphMaps, Node

# (the kind of a space's entry in a path: `pangloss_models.context.SPACE`)
SPACE = "space"


def weight_of(said: Any, weights: Mapping[str, float]) -> float:
    """The weight of a node by what the walk says of it (`spaces.Signature`) and the degree weights
    (`settings.degree_weights`)"""
    from pangloss_fastrp.settings import NO_DEGREE

    if said.veridical == 1:
        return 1.0
    if said.veridical == -1 or said.lean != "for":
        return 0.0
    return float(weights[said.degree or NO_DEGREE])


def stored_path(value: Any) -> list[Any]:
    """A path as a query gives it: a list, or (on a database that cannot hold one, Neo4j) its JSON text; none is
    empty"""
    if value is None:
        return []
    if isinstance(value, str):
        return json.loads(value)
    return list(value)


def _has_space(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        # (JSON text, read without parsing it: a false "yes" only costs the walk)
        return f'"{SPACE}"' in value
    return any(entry.get("kind") == SPACE for entry in value)


def shape_of(path: list[Any]) -> tuple[Any, ...]:
    """A path without its ids: what the walk's answer depends on"""
    return tuple(
        tuple(sorted((key, value) for key, value in entry.items() if key != "id"))
        for entry in path
    )


class Walk:
    """The weight of each node of the second part by its stored path, for one rebuild, refresh or overlay. `spaces`
    and `grounds` are read from the models where they are not given (`spaces.registered_spaces`,
    `registered_grounds`)"""

    def __init__(
        self,
        maps: GraphMaps,
        weights: Mapping[str, float],
        spaces: Mapping[str, Any] | None = None,
        grounds: Mapping[str, Any] | None = None,
    ):
        from pangloss_models import spaces as walking

        self.documents = frozenset(
            name
            for name, kind in maps.kinds.items()
            if kind == STOP and maps.documents.get(name)
        )
        self.weights = dict(weights)
        self.spaces = walking.registered_spaces() if spaces is None else spaces
        self.grounds = walking.registered_grounds() if grounds is None else grounds
        # (the head classes whose ground does not assert what they hold: a path under one is walked, space or none)
        self.unasserted = frozenset(
            name for name, ground in self.grounds.items() if ground["veridical"] != 1
        )
        self.shapes: dict[tuple[Any, ...], float] = {}

    def weight(self, type_name: str, path: Any, head_type: str | None = None) -> float:
        """The weight of a node of the class `type_name`, by its stored path (a list, JSON text, or None for a head)
        and the class of its head (None if not known: then the path's first entry says)"""
        if type_name not in self.documents:
            return 1.0
        if path is None or path == [] or path == "[]":
            # (a head: what its class's ground says of what it holds itself)
            if type_name not in self.unasserted:
                return 1.0
            return self._walked(("head", type_name), [], type_name)
        has_space = _has_space(path)
        if not has_space and head_type is not None and head_type not in self.unasserted:
            return 1.0
        entries = stored_path(path)
        if not has_space and entries and entries[0].get("type") not in self.unasserted:
            return 1.0
        return self._walked(shape_of(entries), entries, None)

    def _walked(
        self, shape: tuple[Any, ...], path: list[Any], head: str | None
    ) -> float:
        found = self.shapes.get(shape)
        if found is None:
            from pangloss_models.spaces import signature

            found = self.shapes[shape] = weight_of(
                signature(path, self.spaces, self.grounds, head=head), self.weights
            )
        return found

    def weighed(self, node: Node, path: Any, head_type: str | None = None) -> Node:
        """The node with its weight (`weight`)"""
        weight = self.weight(node.type, path, head_type)
        return node if weight == node.weight else replace(node, weight=weight)
