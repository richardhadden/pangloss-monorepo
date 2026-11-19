"""`SearchPattern`: a pattern of structured search kept as a value of a model (the criteria of a description:
implementation_docs/matches-criteria.md, "The model").

    criteria: SearchPattern | None = None

It is the JSON of `POST /api/search` (`{"type": "Person", "where": {...}}`), and in Python a `Model.Where` or a
`Match` will do. It is stored as JSON text (a database that cannot hold a nested map holds text), and exported with
`format: "search-pattern"`.

A stored pattern is evaluated long after it was written, by something other than the person who wrote it, so it may
hold less than a search that is run once: `check_stored` says what, and checks the rest against the models.
"""

import json
from collections.abc import Iterable, Iterator
from typing import Any
from uuid import UUID

from pangloss_core import storage_of
from pangloss_models import LiteralCodec, Match, PanglossSearchError, register_codec
from pangloss_models.search import (
    Expr,
    check_match,
    resolve_search_type,
)
from pangloss_models.exceptions import PanglossUnknownTypeError
from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler, ValidationError
from pydantic_core import core_schema

FORMAT = "search-pattern"

# What a stored pattern may not hold, by key, and why. (A search that is run once may hold each of them)
REFUSED: dict[str, str] = {
    "$same_as": (
        "it stands for a cluster of entities that is read when the pattern is made into a query, which a stored "
        "pattern could not keep exact"
    ),
    "$var": "a variable is of a rule, not of a search",
    "$is": "a variable is of a rule, not of a search",
    "$derived": "derived facts in stored criteria are not built yet",
    "$document": "conditions relative to the document are not built yet",
}

# The keys of a condition whose values are ids of entities
ID_KEYS = ("is", "is_any")


def _plain(value: Any) -> Any:
    """A pattern as plain JSON: a `Where`, a `Match` or one of the classes of `search_where` as what it stands
    for, a `UUID` as its text"""
    if isinstance(value, UUID):
        return str(value)
    if hasattr(value, "to_json") and not isinstance(value, dict):
        return _plain(value.to_json())
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _as_data(value: Any) -> dict[str, Any]:
    """What a `SearchPattern` is made from, as `{"type", "where"}`: the JSON, its text (as it is stored), a
    `Match`, or a `Model.Where` (whose model is the type)"""
    from pangloss_models.search_where import Where

    if isinstance(value, SearchPattern):
        return value.data
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as error:
            raise ValueError(f"A search pattern is JSON: {error}") from None
    if isinstance(value, Where):
        model = type(value)._model
        if model is None:
            raise ValueError(
                "A search pattern is a Where of a model (Person.Where(...)), which says its type"
            )
        value = {"type": model.__name__, "where": value.to_json()}
    elif isinstance(value, Match):
        value = value.model_dump(by_alias=True, exclude_unset=True, mode="json")
    if not isinstance(value, dict):
        raise ValueError(
            f"A search pattern is an object with 'type' and 'where', a Match or a Where, not a {type(value).__name__}"
        )
    unknown = sorted(set(value) - {"type", "where"})
    if unknown:
        raise ValueError(
            f"A stored search pattern has 'type' and 'where' only, not {', '.join(repr(k) for k in unknown)}"
        )
    type_name = value.get("type")
    if not isinstance(type_name, str) or not type_name:
        raise ValueError("A search pattern needs the 'type' it is of")
    where = value.get("where")
    where = {} if where is None else _plain(where)
    if not isinstance(where, dict):
        raise ValueError("The 'where' of a search pattern is an object")
    return {"type": type_name, "where": where}


class SearchPattern:
    """A pattern of structured search, as a value: `data` is its JSON, `{"type": ..., "where": {...}}`"""

    __slots__ = ("data",)

    def __init__(self, value: Any):
        self.data: dict[str, Any] = _as_data(value)

    @property
    def type(self) -> str:
        return self.data["type"]

    @property
    def where(self) -> dict[str, Any]:
        return self.data["where"]

    def match(self, exclude_wrappers: Iterable[str] = ()) -> Match:
        """The pattern as a `Match`, to search with. Raises `PanglossSearchError` if it cannot be read as one"""
        try:
            return Match(
                type=self.type,
                where=self.where,
                exclude_wrappers=list(exclude_wrappers),
            )
        except ValidationError as error:
            first = error.errors()[0]
            raise PanglossSearchError(
                f"{'.'.join(str(part) for part in first['loc'])}: {first['msg']}"
            ) from None

    def text(self) -> str:
        """As it is stored: JSON, with its keys in order (so that the same pattern is the same text)"""
        return json.dumps(self.data, sort_keys=True, separators=(",", ":"))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, SearchPattern) and other.data == self.data

    def __hash__(self) -> int:
        return hash(self.text())

    def __repr__(self) -> str:
        return f"SearchPattern({self.data!r})"

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls,
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda value: value.data
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> dict[str, Any]:
        return {
            "type": "object",
            "format": FORMAT,
            "properties": {"type": {"type": "string"}, "where": {"type": "object"}},
            "required": ["type"],
        }


CODEC = LiteralCodec(
    (SearchPattern,),
    "str",
    FORMAT,
    # (a pattern is not compared with another by a search)
    search_kind=None,
    to_storage=lambda pattern: pattern.text(),
)


def register() -> None:
    """Make `SearchPattern` a literal type of the models (once: the module may be loaded again)"""
    from pangloss_models import literals

    if not any(
        codec.format == FORMAT and codec.types == CODEC.types
        for codec in literals.codecs()
    ):
        register_codec(CODEC)


register()


# --- walking a pattern's JSON -------------------------------------------------------------------------------------------


def walk(value: Any, path: str = "") -> Iterator[tuple[str, str, Any]]:
    """Every key of a pattern's JSON, at any depth, as (the path to it, the key, its value)"""
    if isinstance(value, dict):
        for key, item in value.items():
            here = f"{path}.{key}" if path else key
            yield here, key, item
            yield from walk(item, here)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk(item, f"{path}[{index}]")


def ids_named(pattern: SearchPattern) -> list[str]:
    """The ids of the entities a pattern names (`is`, `is_any`, wherever they are), each once, in order"""
    found: dict[str, None] = {}
    for _, key, value in walk(pattern.where):
        if key not in ID_KEYS:
            continue
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, str):
                found.setdefault(item, None)
    return list(found)


def with_ids(pattern: SearchPattern, replaced: dict[str, str]) -> SearchPattern:
    """The pattern with some of the ids it names replaced (`replaced`: the id as written, to the id it becomes).
    A list that by this names an entity twice has it once"""
    if not replaced:
        return pattern

    def rewritten(value: Any) -> Any:
        if isinstance(value, dict):
            made = {}
            for key, item in value.items():
                if key in ID_KEYS and isinstance(item, list):
                    made[key] = list(
                        dict.fromkeys(
                            replaced.get(each, each) if isinstance(each, str) else each
                            for each in item
                        )
                    )
                elif key in ID_KEYS and isinstance(item, str):
                    made[key] = replaced.get(item, item)
                else:
                    made[key] = rewritten(item)
            return made
        if isinstance(value, list):
            return [rewritten(item) for item in value]
        return value

    return SearchPattern({"type": pattern.type, "where": rewritten(pattern.where)})


async def resolve_merged(pattern: SearchPattern) -> SearchPattern:
    """The pattern with the id of each entity that was merged into another replaced by its survivor's: a structured
    search does not resolve the ids it is given (`{"is": id}` of a merged entity matches nothing). The stored pattern
    is not rewritten: that would change the document outside a save"""
    ids = ids_named(pattern)
    if not ids:
        return pattern
    survivors_of = getattr(storage_of().operations, "survivors_of", None)
    if survivors_of is None:
        return pattern
    return with_ids(pattern, await survivors_of(ids))


# --- the check of a stored pattern --------------------------------------------------------------------------------------


def check_stored(
    pattern: SearchPattern,
    allowed: Iterable[type] | None = None,
    exclude_wrappers: Iterable[str] = (),
) -> list[Expr]:
    """Check a pattern that is to be stored, against the models as they are now. Gives its checked conditions; raises
    `PanglossSearchError`, naming the path in the pattern, for:

    - a type that is not a document or an entity, or (`allowed`: the classes the pattern may be of) not one of those,
      nor a class below one;
    - anything a search of now would refuse: a field that is not there, an operator that does not fit, a value of the
      wrong type;
    - what only a stored pattern may not hold (`REFUSED`), and a `through` that names one of `exclude_wrappers`: the
      wrappers the pattern will be evaluated without, which is how it is checked."""
    for path, key, value in walk(pattern.where):
        if key in REFUSED:
            raise PanglossSearchError(
                f"{path}: '{key}' cannot be in a stored pattern: {REFUSED[key]}"
            )
        if key in ID_KEYS:
            # (said here, with the path: read as a search, the pattern would say only that an id is wrong)
            for item in value if isinstance(value, list) else [value]:
                try:
                    UUID(str(item))
                except ValueError:
                    raise PanglossSearchError(
                        f"{path}: {item!r} is not the id of an entity"
                    ) from None
    try:
        model = resolve_search_type(pattern.type)
    except PanglossUnknownTypeError as error:
        raise PanglossSearchError(f"type: {error}") from None
    if allowed is not None:
        classes = [cls for cls in allowed if isinstance(cls, type)]
        if not any(issubclass(model, cls) for cls in classes):
            names = ", ".join(sorted(cls.__name__ for cls in classes))
            raise PanglossSearchError(
                f"type: '{pattern.type}' is not what is described here ({names})"
            )
    return check_match(model, pattern.match(exclude_wrappers))


__all__ = [
    "CODEC",
    "FORMAT",
    "REFUSED",
    "SearchPattern",
    "check_stored",
    "ids_named",
    "resolve_merged",
    "walk",
    "with_ids",
]
