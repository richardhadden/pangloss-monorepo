"""What the worker needs to know of a description's criteria, worked out from the checked pattern
(implementation_docs/matches-criteria.md, "Choosing the descriptions" and "As built", step 7).

A match of the criteria is an entity (the root). What makes it one is in **heads**: the entity itself, and the
documents that refer to it. Two things are asked of a pattern:

- **reach**: `local` if every condition is on the root itself or inside a document that refers to it directly (its
  nested documents, its wrappers, and which entities those name). Then a write can change whether an entity matches
  only if the head written names that entity (now, or before the write) or is it: the entities a write names are
  all the roots it can change. `far` if a condition is on another entity (its fields, its class, the documents that
  refer to it), on a document that is cited, or is an extension's: a write may then change a match of an entity it
  does not name.

- **anchors**: what every match must be joined to. An `is` or `is_any` on a relation, outside `$not` and
  `$any_of`, is a group of ids (of entities; or of documents, where one stands in for an entity or is cited) of which a match reaches one, by a chain of `hops` heads (one for a local
  condition: some head names both the root and the anchor, or is the root and names it). So every match is among
  what is found by going from the anchor to the heads that refer to it and on to what those heads name, `hops`
  times: a full evaluation that reads the anchor's neighbourhood and not every entity of the class.

Criteria that follow a relation the server computes (`Computed()`) are `far` and have no anchor.

A pattern is **complete** if it is local and all of it is one condition that holds an anchor ("secretary of
Maximilian": one `$incoming`, and everything asked is inside that document). Then every head that bears on a match
names an id of each group, and a write that names none of some group cannot change the result.
"""

import dataclasses
import hashlib
import json
from typing import Any

from pangloss_models import AnyOf, Document, Entity, Not
from pangloss_models.field_definitions import RelationToCitation
from pangloss_models.markers import is_computed
from pangloss_models.search import (
    CheckedCondition,
    CheckedIncoming,
    CheckedPattern,
    SearchKey,
)

from pangloss_criteria.pattern import ID_KEYS, SearchPattern

LOCAL = "local"
FAR = "far"

# (keys of a `where` whose value is a relation that is no field: the class of what it reaches is not known)
NO_FIELD = {str(SearchKey.ANY), str(SearchKey.MENTIONS)}


@dataclasses.dataclass(frozen=True)
class Anchor:
    """A group of entity ids of which every match reaches at least one, `hops` heads away"""

    ids: tuple[str, ...]
    hops: int


@dataclasses.dataclass(frozen=True)
class Analysis:
    reach: str
    anchors: tuple[Anchor, ...]
    complete: bool

    @property
    def stored_anchors(self) -> list[str]:
        """The ids kept on the description for the worker's first choice: those of which a write must name one to
        bear on the result. None for a pattern that is not complete: any write of a class it depends on may"""
        if not self.complete:
            return []
        return list(dict.fromkeys(id for anchor in self.anchors for id in anchor.ids))


def _options(model: type, field: str) -> list[Any] | None:
    """What the relation `field` of the class can hold, through wrappers (None if it is no field of it)"""
    fields = getattr(getattr(model, "_meta", None), "fields", None)
    definition = getattr(fields, "relation_fields", {}).get(field) if fields else None
    if definition is None:
        return None
    found: list[Any] = []

    def leaves(options: Any) -> None:
        for option in options:
            parameters = getattr(option, "parameter_type_options", None)
            if parameters:
                for parameter in parameters.values():
                    leaves(parameter.type_options)
            else:
                found.append(option)

    leaves(definition.type_options)
    return found


def names_heads(model: type, field: str) -> bool:
    """Whether the relation is a field of the class: what an `is` of it names is then a head that the node refers
    to by an edge (an entity; a document that stands in for one, or is cited)"""
    return bool(_options(model, field))


def is_computed_relation(model: type, field: str) -> bool:
    fields = getattr(getattr(model, "_meta", None), "fields", None)
    definition = getattr(fields, "relation_fields", {}).get(field) if fields else None
    return definition is not None and is_computed(definition)


def cites(model: type, field: str) -> bool:
    """Whether the relation may be to a document that is not part of this one (or is not known not to be)"""
    options = _options(model, field)
    return options is None or any(isinstance(o, RelationToCitation) for o in options)


def analyse(root: type, items: list[Any]) -> Analysis:
    """`root`: the class the criteria are of; `items`: the checked pattern (`check_stored`)"""
    anchors: list[Anchor] = []
    far = False
    computed = False

    def walk(model: type, exprs: list[Any], hops: int, anchoring: bool) -> None:
        nonlocal far, computed
        for expr in exprs:
            if isinstance(expr, AnyOf):
                for branch in expr.branches:
                    walk(model, branch, hops, False)
                continue
            if isinstance(expr, Not):
                walk(model, expr.items, hops, False)
                continue
            if not isinstance(expr, CheckedCondition):
                far = True
                continue
            value = expr.value
            if expr.kind == "relation" and is_computed_relation(model, expr.field):
                computed = True
            if expr.kind == "incoming" and isinstance(value, CheckedIncoming):
                if any(
                    is_computed_relation(value.pattern.model, name)
                    for name in value.fields
                ):
                    computed = True
                if not issubclass(model, Entity):
                    # (what refers to a document is another head: one that cites it)
                    far = True
                    walk(value.pattern.model, value.pattern.items, hops, False)
                else:
                    walk(value.pattern.model, value.pattern.items, hops, anchoring)
            elif expr.kind == "relation" and expr.operator in ("is", "is_any"):
                ids = value if isinstance(value, (list, tuple)) else [value]
                if (
                    anchoring
                    and expr.field not in NO_FIELD
                    and names_heads(model, expr.field)
                ):
                    anchors.append(Anchor(tuple(str(id) for id in ids), hops))
            elif isinstance(value, CheckedPattern):
                target = value.model
                if expr.kind == "somewhere":
                    # (a node anywhere in the same document)
                    walk(target, value.items, hops, anchoring)
                elif issubclass(target, Entity):
                    # (a second entity: its class, its fields, what refers to it)
                    far = True
                    walk(target, value.items, hops + 1, anchoring)
                elif issubclass(target, Document) and (
                    expr.field in NO_FIELD or cites(model, expr.field)
                ):
                    far = True
                    walk(target, value.items, hops, False)
                else:
                    # (a nested document, an embedded object: part of the same head)
                    walk(target, value.items, hops, anchoring)
            elif expr.kind == "extension":
                far = True

    walk(root, items, 1, True)
    if computed:
        # (a relation the server computes is followed by a search as any other, but it is no part of what a head
        # "names", and it changes with no write of a document: such criteria are evaluated in full, root first)
        return Analysis(FAR, (), False)
    one = len(items) == 1 and isinstance(items[0], CheckedCondition)
    complete = (
        not far
        and bool(anchors)
        and one
        and (
            items[0].kind == "incoming"
            or (items[0].kind == "relation" and items[0].operator in ("is", "is_any"))
        )
    )
    return Analysis(FAR if far else LOCAL, tuple(anchors), complete)


def shape_of(pattern: SearchPattern) -> str:
    """The pattern with its ids and values taken out, hashed: every "secretary of X" has one shape. (For counting
    and for `explain`. What is evaluated together is decided by the text of the compiled query.)"""

    def emptied(value: Any, key: str = "") -> Any:
        if isinstance(value, dict):
            return {k: emptied(v, k) for k, v in value.items()}
        if isinstance(value, list):
            if key in ID_KEYS or not any(isinstance(v, (dict, list)) for v in value):
                return "?"
            return [emptied(v, key) for v in value]
        if key in ("type", "field", "through") and isinstance(value, str):
            return value
        return "?"

    text = json.dumps(
        {"type": pattern.type, "where": emptied(pattern.where)}, sort_keys=True
    )
    return hashlib.sha1(text.encode()).hexdigest()


_known: dict[str, Analysis | None] = {}


def forget() -> None:
    """(`ModelRegistry.on_reset`) the models have changed"""
    _known.clear()


def of(pattern: SearchPattern) -> Analysis | None:
    """What a stored pattern is, as it is written (kept by its text: the worker asks for every description it
    looks at). None if it no longer fits the models"""
    from pangloss_models import PanglossSearchError
    from pangloss_models.search import resolve_search_type

    from pangloss_criteria.models import EXCLUDED
    from pangloss_criteria.pattern import check_stored

    text = pattern.text()
    if text not in _known:
        try:
            items = check_stored(pattern, None, EXCLUDED)
            _known[text] = analyse(resolve_search_type(pattern.type), items)
        except PanglossSearchError, ValueError:
            _known[text] = None
    return _known[text]
