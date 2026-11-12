"""Merging two entities that are one (implementation_docs/entity-identity.md, part 1): what the models know of it, with
no database. The storage does the merge (`Entity.merge`, `Entity.unmerge`, `Entity.merge_preview`, `Entity.merges`,
bound when the models are initialised); here are the rules it follows and what it gives back:

- which class the survivor takes (`survivor_class`);
- the fields the survivor has if no one chooses (`merged_values`), and a class's rule for the absorbed entity's label
  (`Entity.Meta(merge=MergeRules(label_into="aliases"))`);
- what a merge, a preview of one, and an undo say they did (`MergeResult`, `MergePreview`, `UnmergeResult`);
- `before_merge` (in `pangloss_models.hooks`): how an installed app refuses a merge.
"""

import contextlib
import contextvars
import dataclasses
import datetime
from collections.abc import Generator
from typing import Any
from uuid import UUID

from pangloss_models.exceptions import PanglossMergeError, PanglossServerOnly
from pangloss_models.markers import keeps_on_merge

# The most heads a merge writes in one transaction, if the settings say nothing (`MERGE_LIMIT`): over it a merge is
# made only when asked for as a large one, in batches (measured: 1,000 heads take 0.6 s in one transaction, 5,000
# take 13 s)
DEFAULT_MERGE_LIMIT = 1000


@dataclasses.dataclass(frozen=True)
class MergeRules:
    """What a merge does with the values of the absorbed entity that the survivor does not take, by default
    (`Entity.Meta(merge=MergeRules(...))`; the person merging may still choose otherwise)"""

    label_into: str | None = None
    """A list field of text (`aliases`): the absorbed entity's label is added to it, if it is not the survivor's
    label and not there already"""


@dataclasses.dataclass(frozen=True)
class HeadRef:
    """A head document or entity that a merge names: what it is, for a person to look at"""

    id: UUID
    type: str
    label: str | None = None


@dataclasses.dataclass
class MergeRecord:
    """A merge, as it is recorded (`PGMerge`)"""

    id: UUID
    survivor: UUID
    absorbed: UUID
    state: str
    """`proposed` (asked for, and nothing written: someone else verifies or rejects it), `rejected`, `stale` (proposed,
    and overtaken: one of its entities was merged, or the database migrated), `running` (a large merge whose batches
    are not all made), `done`, `undone`"""
    by: str | None = None
    """Who carried it out (of a merge that was proposed: who verified it)"""
    when: datetime.datetime | None = None
    survivor_type: str | None = None
    """The class of the survivor after the merge"""
    survivor_type_before: str | None = None
    absorbed_type: str | None = None
    survivor_label: str | None = None
    """The survivor's label before the merge"""
    absorbed_label: str | None = None
    survivor_version: int | None = None
    """The version the merge gave the survivor (of a proposal: the version it was proposed on)"""
    absorbed_version: int | None = None
    heads: int = 0
    """How many heads it wrote (each has a new version)"""
    moved: int = 0
    """How many references it moved to the survivor"""
    dropped: int = 0
    """How many it dropped, because the node already had the relation to the survivor"""
    undone_by: str | None = None
    undone_when: datetime.datetime | None = None
    proposed_by: str | None = None
    proposed_when: datetime.datetime | None = None
    note: str | None = None
    """What the one who proposed it said of it"""
    values: dict[str, Any] | None = None
    """Of a proposal: the fields the survivor would have (as its `Update` takes them)"""
    rejected_by: str | None = None
    rejected_when: datetime.datetime | None = None
    reason: str | None = None
    """Why it was rejected, or is stale"""
    undo_proposed_by: str | None = None
    """Who asked for it to be undone, if someone did who may not undo it alone: a different user accepts (by undoing
    it) or rejects that"""
    undo_proposed_when: datetime.datetime | None = None
    undo_note: str | None = None
    undo_rejected_by: str | None = None
    undo_rejected_reason: str | None = None

    @property
    def stands(self) -> bool:
        """It was carried out and not undone: the absorbed entity is merged by it"""
        return self.state in ("done", "running")


@dataclasses.dataclass
class MergeResult:
    """What a merge did"""

    merge: MergeRecord
    collapsed: list[HeadRef] = dataclasses.field(default_factory=list)
    """The heads that referred to both entities by one relation, and now refer to the survivor once: for a person to
    look at (two witnesses have become one)"""
    both: list[HeadRef] = dataclasses.field(default_factory=list)
    """The heads that referred to the two entities by different relations, and now refer to the survivor by both (a
    marriage of the survivor to itself)"""
    kept: int = 0
    """How many references were left on the absorbed entity (`KeepOnMerge()`)"""
    late: int = 0
    """How many references a later pass moved: made by writes that were under way when the merge was"""


@dataclasses.dataclass
class MergePreview:
    """What a merge would do, and whether it can be made"""

    survivor: UUID
    absorbed: UUID
    survivor_type: str | None = None
    """The class the survivor would have"""
    refused: list[str] = dataclasses.field(default_factory=list)
    """Why it cannot be made (empty: it can)"""
    heads: int = 0
    """How many heads it would write"""
    limit: int = DEFAULT_MERGE_LIMIT
    large: bool = False
    """It is over the limit: made only as a large merge, in batches, and not previewed in full"""
    refer_to_survivor: dict[str, int] = dataclasses.field(default_factory=dict)
    """How many heads refer to the survivor now, by their class"""
    refer_to_absorbed: dict[str, int] = dataclasses.field(default_factory=dict)
    collapsed: list[HeadRef] = dataclasses.field(default_factory=list)
    both: list[HeadRef] = dataclasses.field(default_factory=list)
    kept: int = 0
    values: dict[str, Any] | None = None
    """The fields the survivor would have (as its `Update` takes them)"""

    @property
    def possible(self) -> bool:
        return not self.refused


@dataclasses.dataclass
class UnmergeResult:
    """What the undoing of a merge did"""

    merge: MergeRecord
    restored: int = 0
    """How many references went back to the absorbed entity"""
    heads: int = 0
    """How many heads that wrote"""
    unmatched: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    """The recorded moves that could not be put back, each with why (`reason`): the node is gone (`gone`: removed,
    or its head saved without its ids), its head is deleted (`deleted`), or its relation no longer points at the
    survivor (`changed`)"""
    made_since: list[HeadRef] = dataclasses.field(default_factory=list)
    """The heads that refer to the survivor and were written since the merge: some may have been meant for the
    absorbed entity. They stay on the survivor"""
    fields_restored: bool = False
    """Whether the survivor's own fields were put back as they were before the merge (only if it had not changed
    since)"""
    draft: dict[str, Any] | None = None
    """If not: the survivor's fields as they were before the merge, for a person to reconcile with what it has now"""
    draft_type: str | None = None
    draft_reason: str | None = None


# --- as JSON, for the API and the SDK ---------------------------------------------------------------------------------

# The fields that hold an entity as its `Update` takes it, and the field that says of which class
_PAYLOADS = {"values": "survivor_type", "draft": "draft_type"}


def _payload(type_name: str | None, payload: Any, by_alias: bool) -> Any:
    """An entity's fields with the keys of JSON (`by_alias`) or of Python; as they are, if they are no longer those
    of the class (a draft from before a migration)"""
    from pangloss_models.model_registry import ModelRegistry
    from pydantic import ValidationError

    model = ModelRegistry.all_models().get(type_name) if type_name else None
    if model is None or not isinstance(payload, dict) or not hasattr(model, "Update"):
        return payload
    try:
        return model.Update.model_validate(payload).model_dump(  # ty: ignore[unresolved-attribute]
            mode="json", by_alias=by_alias
        )
    except ValidationError:
        return payload


def to_wire(value: Any) -> Any:
    """A result of this module (`MergeRecord`, `MergeResult`, `MergePreview`, `UnmergeResult`) as the API gives it:
    JSON, with camelCase keys"""
    from pydantic.alias_generators import to_camel

    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        wire: dict[str, Any] = {}
        for field in dataclasses.fields(value):
            item = getattr(value, field.name)
            if field.name in _PAYLOADS and item is not None:
                item = _payload(getattr(value, _PAYLOADS[field.name], None), item, True)
            elif field.name in ("refer_to_survivor", "refer_to_absorbed"):
                item = dict(item)
            else:
                item = to_wire(item)
            wire[to_camel(field.name)] = item
        if isinstance(value, MergePreview):
            wire["possible"] = value.possible
        return wire
    if isinstance(value, list):
        return [to_wire(item) for item in value]
    if isinstance(value, dict):
        return {to_camel(key): to_wire(item) for key, item in value.items()}
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    return value


def from_wire(kind: Any, wire: Any) -> Any:
    """The result the API gave (`to_wire`), as the dataclass `kind` again"""
    from pydantic.alias_generators import to_snake

    given = {to_snake(key): item for key, item in wire.items()}
    values: dict[str, Any] = {}
    for field in dataclasses.fields(kind):
        if field.name not in given:
            continue
        item = given[field.name]
        if item is None:
            values[field.name] = None
        elif field.name == "merge":
            values[field.name] = from_wire(MergeRecord, item)
        elif field.name in ("collapsed", "both", "made_since"):
            values[field.name] = [
                HeadRef(id=UUID(ref["id"]), type=ref["type"], label=ref.get("label"))
                for ref in item
            ]
        elif field.name in ("id", "survivor", "absorbed"):
            values[field.name] = UUID(item)
        elif field.name.endswith("when"):
            values[field.name] = datetime.datetime.fromisoformat(item)
        elif field.name == "unmatched":
            values[field.name] = [
                {to_snake(key): value for key, value in row.items()} for row in item
            ]
        elif field.name in _PAYLOADS:
            values[field.name] = _payload(given.get(_PAYLOADS[field.name]), item, False)
        else:
            values[field.name] = item
    return kind(**values)


# --- which class the survivor takes -----------------------------------------------------------------------------------


def _concrete_entities() -> list[Any]:
    from pangloss_models.model_bases.entity import Entity
    from pangloss_models.model_registry import ModelRegistry

    return [
        model
        for model in ModelRegistry.all_models().values()
        if isinstance(model, type)
        and issubclass(model, Entity)
        and not model._meta.abstract
    ]


def survivor_classes(survivor: Any, absorbed: Any) -> list[Any]:
    """The classes the survivor of a merge of entities of these two classes may take, the default first.

    The same class: that one. One a subclass of the other: the narrower (and the wider, if chosen). Neither: the
    classes that are both (`class PoetSoldier(Poet, Soldier)`), the least particular first. None: they cannot be
    merged."""
    if survivor is absorbed:
        return [survivor]
    if issubclass(absorbed, survivor):
        return [absorbed, survivor]
    if issubclass(survivor, absorbed):
        return [survivor, absorbed]
    both = [
        model
        for model in _concrete_entities()
        if issubclass(model, survivor) and issubclass(model, absorbed)
    ]
    # (the least particular: not a subclass of another that is both)
    least = [
        model
        for model in both
        if not any(other is not model and issubclass(model, other) for other in both)
    ]
    return sorted(least, key=lambda m: m.__name__) + sorted(
        (m for m in both if m not in least), key=lambda m: m.__name__
    )


def survivor_class(survivor: Any, absorbed: Any, chosen: Any = None) -> Any:
    """The class the survivor takes (`survivor_classes`): the one chosen, if it may be; else the default. Raises
    `PanglossMergeError` if the two cannot be merged, or the choice has to be made"""
    options = survivor_classes(survivor, absorbed)
    if not options:
        raise PanglossMergeError(
            f"A {absorbed.__name__} cannot be merged into a {survivor.__name__}: neither is a kind of the other, "
            f"and no class is both. Change the class of one of them first"
        )
    if chosen is not None:
        if chosen not in options:
            raise PanglossMergeError(
                f"The survivor of a {survivor.__name__} and a {absorbed.__name__} cannot be a {chosen.__name__}: "
                f"it can be {' or '.join(o.__name__ for o in options)}"
            )
        return chosen
    related = issubclass(absorbed, survivor) or issubclass(survivor, absorbed)
    least = [
        o
        for o in options
        if not any(other is not o and issubclass(o, other) for other in options)
    ]
    if not related and len(least) > 1:
        raise PanglossMergeError(
            f"A {survivor.__name__} and a {absorbed.__name__} can be merged as "
            f"{' or '.join(o.__name__ for o in least)}: say which (`as_class`)"
        )
    if getattr(options[0]._meta, "abstract", False):
        raise PanglossMergeError(
            f"{options[0].__name__} is abstract: the survivor cannot be one"
        )
    return options[0]


# --- the fields the survivor has --------------------------------------------------------------------------------------


def _empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def _identity(item: Any) -> Any:
    """What makes two items of a list the same: the id of a reference, else the item"""
    if isinstance(item, dict):
        if set(item) >= {"id", "type"} and not _is_nested(item):
            return ("ref", str(item["id"]))
        return ("map", repr(sorted((k, repr(v)) for k, v in item.items())))
    return ("value", repr(item))


def _is_nested(item: dict[str, Any]) -> bool:
    """(a reference has its id, type and label, and what its view shows; a wrapper has a target or contents)"""
    return any(isinstance(v, (dict, list)) for k, v in item.items() if k != "meta")


def _both(first: list[Any], second: list[Any]) -> list[Any]:
    seen: set[Any] = set()
    result = []
    for item in [*first, *second]:
        key = _identity(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def without_references_to(value: Any, ids: set[str]) -> Any:
    """`value` (what a relation of an entity holds) without the references to the entities `ids`: the survivor of a
    merge refers neither to itself nor to what it absorbed. A single relation that names one of them is None"""
    if isinstance(value, list):
        return [
            item
            for item in value
            if not (isinstance(item, dict) and str(item.get("id")) in ids)
        ]
    if isinstance(value, dict) and str(value.get("id")) in ids:
        return None
    return value


def merged_values(
    result: Any,
    survivor: dict[str, Any],
    absorbed: dict[str, Any],
) -> dict[str, Any]:
    """The fields the survivor of a merge has if no one chooses, as an `Update` of the class `result` takes them.
    `survivor` and `absorbed` are the two entities as they are edited (the dump of each one's `EditView`, without
    `meta`).

    - the label, and every single value: the survivor's, or the absorbed entity's where the survivor has none;
    - every list (of values, or of relations): both, without repeats;
    - the URLs: both;
    - the absorbed entity's label goes where the class says (`MergeRules(label_into=...)`);
    - a relation to either of the two is left out."""
    fields = result._meta.field_definitions.fields
    values: dict[str, Any] = {"id": survivor["id"], "type": result.__name__}
    for name in ("label", "label_auto"):
        if name in result.Update.model_fields and (
            name in survivor or name in absorbed
        ):
            mine = survivor.get(name)
            values[name] = absorbed.get(name) if _empty(mine) else mine
    for name, definition in fields.items():
        if name not in result.Update.model_fields or definition.db_field:
            continue
        mine, theirs = survivor.get(name), absorbed.get(name)
        if isinstance(mine, list) or isinstance(theirs, list):
            values[name] = _both(mine or [], theirs or [])
        else:
            values[name] = theirs if _empty(mine) else mine
    values["urls"] = sorted(
        {str(u) for u in [*survivor.get("urls", []), *absorbed.get("urls", [])]}
    )

    rules = getattr(result._meta, "merge", None)
    into = rules.label_into if rules is not None else None
    if into is not None:
        if into not in fields or not isinstance(values.get(into, []), list):
            raise PanglossMergeError(
                f"{result.__name__}: MergeRules(label_into={into!r}) does not name a list field of the class"
            )
        label = absorbed.get("label")
        if label and label != values.get("label") and label not in values[into]:
            values[into] = [*values.get(into, []), label]

    own = {str(survivor["id"]), str(absorbed["id"])}
    for name in getattr(fields, "relation_fields", {}):
        if name in values:
            values[name] = without_references_to(values[name], own)
    return values


def kept_fields(model: Any) -> set[str]:
    """The names of the edges of a node of the class that a merge leaves where they are: those of its relations
    marked `KeepOnMerge()`, and of the parent fields those are also stored as"""
    kept: set[str] = set()
    for name, definition in model._meta.fields.relation_fields.items():
        if keeps_on_merge(definition):
            kept.add(name)
            kept.update(
                getattr(parent, "field_name", parent)
                for parent in definition.subclasses_parent_fields
            )
    return kept


# --- what a write resolved ---------------------------------------------------------------------------------------------

# The references to merged entities that the writes inside `noting_resolved()` named, and the survivors they were
# written as: (the id given, the survivor's id). The API says them in its response. None: no one is listening
resolved_references: contextvars.ContextVar[list[tuple[str, str]] | None] = (
    contextvars.ContextVar("resolved_merged_references", default=None)
)


@contextlib.contextmanager
def noting_resolved() -> Generator[list[tuple[str, str]]]:
    """Within the block, the references to merged entities that writes resolve to their survivors are noted: the list
    given holds each as (the id written, the id of the survivor)"""
    noted: list[tuple[str, str]] = []
    token = resolved_references.set(noted)
    try:
        yield noted
    finally:
        resolved_references.reset(token)


def note_resolved(given: str, survivor: str) -> None:
    noted = resolved_references.get()
    if noted is not None and (given, survivor) not in noted:
        noted.append((given, survivor))


# --- the storage's operations, until a storage that has them is bound ---------------------------------------------------


def not_on_this_storage(operation: str, storage: str | None):
    """What `Entity.merge` and the like are on a storage that cannot merge (the SDK's, until it has the routes)"""

    async def refuse(cls, *args: Any, **kwargs: Any) -> Any:
        raise PanglossServerOnly(
            f"{cls.__name__}.{operation}: the storage {storage!r} cannot merge entities"
        )

    return refuse
