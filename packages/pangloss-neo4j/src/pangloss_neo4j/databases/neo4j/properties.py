"""Storing what Neo4j cannot store as a property: maps.

A Neo4j property is a primitive, a temporal value, or a list of one of those. Pangloss keeps a map on every node
(`meta`: who made it and when, the semantic spaces it is in, its context labels, a list of maps) and on every annotated
value (`{value, certainty}`), and a model may have a `TypedDict`. They are *flattened* when written and *nested again* when
read, so that everything above this module sees what a Neo4j backend gives it (see `docs/neo4j-implementation.md`):

- a map becomes properties named by the path, joined by a dot: `meta.created_by`, `meta.semantic_spaces`, `date.value`.
  (In Cypher a name with a dot is written with backticks: `` n.`meta.created_by` ``; a model field cannot be called with a
  dot, so there is no clash);
- a list of maps (or of mixed values), which has no flat form, is stored as JSON text under the name with `#json` after it
  (`meta.context_labels#json`: no model field can have a `#` in its name, so text that happens to be JSON in a property is
  never taken for one of these). What a query needs of it is kept beside it, flat (`meta.context_label_types`);
- an empty map, and `None`, are no property.
"""

import json
from collections.abc import Callable
from typing import Any

from pangloss_models.exceptions import PanglossWriteError

SEPARATOR = "."

# The ending of the name of a property that holds a list of maps, as JSON text
JSON_SUFFIX = "#json"

# These are always JSON text, whatever they hold (an empty list too), so that there is one form to read
ALWAYS_JSON = frozenset({"meta.context_labels"})

# What is kept flat beside a JSON property, for the queries: {the property: (the new name, how to get it)}
DERIVED: dict[str, tuple[str, Callable[[Any], Any]]] = {
    "meta.context_labels": (
        "meta.context_label_types",
        lambda labels: [label["type"] for label in labels],
    ),
}
DERIVED_NAMES = frozenset(name for name, _ in DERIVED.values())

META_FIELDS = (
    "created_by",
    "created_when",
    "updated_by",
    "updated_when",
    "semantic_spaces",
)


def quote(name: str) -> str:
    """A property name for a query: `meta.created_by` is written `` `meta.created_by` ``"""
    return f"`{name}`"


def prop(variable: str, name: str) -> str:
    """`n.meta.created_by` as the query has to write it: `` n.`meta.created_by` ``"""
    return f"{variable}.{quote(name)}"


def is_map(value: Any) -> bool:
    return isinstance(value, dict)


def json_name(name: str) -> str:
    return f"{name}{JSON_SUFFIX}"


def storable_list(name: str, value: list[Any]) -> bool:
    """Whether a list can be a property: of one primitive type (a number may be an int or a float: Neo4j stores a list of
    either)"""
    kinds = {
        (
            "number"
            if isinstance(item, int | float) and not isinstance(item, bool)
            else type(item)
        )
        for item in value
    }
    return len(kinds) <= 1 and not any(isinstance(item, dict | list) for item in value)


def flatten(properties: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """The properties as Neo4j can store them: maps flattened by path, a list of maps as JSON text where that is
    allowed (`JSON_PROPERTIES`)"""
    flat: dict[str, Any] = {}
    for key, value in properties.items():
        name = f"{prefix}{key}"
        if value is None:
            continue
        if is_map(value):
            flat.update(flatten(value, f"{name}{SEPARATOR}"))
        elif isinstance(value, list) and (
            name in ALWAYS_JSON or not storable_list(name, value)
        ):
            try:
                flat[json_name(name)] = json.dumps(
                    value, default=json_default, separators=(",", ":")
                )
            except PanglossWriteError as error:
                raise PanglossWriteError(f"{name}: {error}") from None
        else:
            flat[name] = value
        if name in DERIVED and isinstance(value, list):
            derived_name, derive = DERIVED[name]
            flat[derived_name] = derive(value)
    return flat


def json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "to_native"):
        return value.to_native().isoformat()
    raise PanglossWriteError(f"Cannot store a {type(value).__name__} in a list of maps")


def unflatten(properties: dict[str, Any]) -> dict[str, Any]:
    """The inverse of `flatten`: names with dots are nested again, and the JSON properties decoded; what is kept flat for
    the queries is left out"""
    nested: dict[str, Any] = {}
    for name, value in properties.items():
        if name in DERIVED_NAMES:
            continue
        if name.endswith(JSON_SUFFIX):
            name = name[: -len(JSON_SUFFIX)]
            value = json.loads(value) if isinstance(value, str) else value
        parts = name.split(SEPARATOR)
        target = nested
        for part in parts[:-1]:
            existing = target.setdefault(part, {})
            if not isinstance(
                existing, dict
            ):  # (a value and a map of one name: the value is kept)
                break
            target = existing
        else:
            target[parts[-1]] = value
    return nested


def decode(value: Any) -> Any:
    """`unflatten` anywhere in what a query returned: a map with a name that has a dot, or with `meta` properties,
    wherever it is in the maps and lists"""
    if isinstance(value, dict):
        decoded = {
            key: (
                json.loads(item)
                if key == "context_labels" and isinstance(item, str)
                else decode(item)
            )
            for key, item in value.items()
        }
        if any(SEPARATOR in key or key.endswith(JSON_SUFFIX) for key in decoded):
            return unflatten(decoded)
        return decoded
    if isinstance(value, list):
        return [decode(item) for item in value]
    return value


def meta_map(variable: str) -> str:
    """The Cypher for the `meta` of a node, as the map that Neo4j keeps: `meta_map("n")`. (`context_labels` is the
    JSON text: `decode` makes it a list; `meta_properties` does it for the properties of a node)"""
    fields = ", ".join(
        f"{field}: {prop(variable, f'meta.{field}')}" for field in META_FIELDS
    )
    return f"{{{fields}, context_labels: {prop(variable, json_name('meta.context_labels'))}}}"


def flat_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """The flat properties of a `meta`, for `SET n += ...`: every property it can have is in the map, one that the `meta`
    has no value for as `None`, so that setting it takes the old one away"""
    flat = {f"meta.{field}": None for field in META_FIELDS}
    flat.update(
        {json_name("meta.context_labels"): None, "meta.context_label_types": None}
    )
    flat.update(flatten({"meta": meta}))
    return flat


def meta_of(properties: dict[str, Any]) -> dict[str, Any] | None:
    """The `meta` of a node's properties (flat, as Neo4j gives them), as the map; None if it has none"""
    return unflatten(properties).get("meta")
