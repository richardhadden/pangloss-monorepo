"""Companion documents: a document offered with a new entity, and written with it (implementation_docs/companion-documents.md).

An entity declares them in its `Meta` (`Entity.Meta(companions=[Companion(...)])`). When one of the entity is made, the
interface offers each companion that fits where it is made (`offered`); a companion that is filled in is written in
the same transaction as the entity, with the entity put in the field of each part that is for it (`entity_field`).

The declaration is not data: a change to it is not a migration. Its names are strings (the entity is usually declared
before the documents that refer to it) and are checked at `initialise()` (`check_companions`)."""

from dataclasses import dataclass
from typing import Any, cast


def _tuple(value: Any) -> tuple:
    return (
        tuple(value) if isinstance(value, (list, tuple, set, frozenset)) else (value,)
    )


@dataclass(frozen=True, kw_only=True)
class CompanionPart:
    """A document the companion holds in its `field`, offered already added: `type` is its class, `entity_field` its
    relation that the new entity is put in"""

    type: str
    entity_field: str


@dataclass(frozen=True, kw_only=True)
class CopyFromOuter:
    """A field of the document the entity is made from (its head), copied into a field of the companion (`to`, by
    default the same name). A relation is copied as a value of its own, as a field binding copies"""

    field: str
    to: str | None = None

    @property
    def target(self) -> str:
        return self.to or self.field


@dataclass(frozen=True, kw_only=True)
class Within:
    """Offered when the entity is made from the form of a document: one whose head is of one of `heads` (with the types
    below them; none: any), from one of `fields` (`"Statement.involves"`, with the fields that stand for it; none: any),
    of a document of one of `holders` (with the types below; none: any)"""

    heads: tuple[str, ...] = ()
    fields: tuple[str, ...] = ()
    holders: tuple[str, ...] = ()

    def __post_init__(self):
        for name in ("heads", "fields", "holders"):
            object.__setattr__(self, name, _tuple(getattr(self, name)))


@dataclass(frozen=True)
class Standalone:
    """Offered when the entity is made on its own (its own page; a dialog with no document behind it)"""


@dataclass(frozen=True, kw_only=True)
class Companion:
    """A document offered with a new entity of the class that declares it.

    `document` is its class (a document that can be made on its own). With `field`, a list relation of it, the
    companion holds `parts`, each a document with a relation for the entity; without, the companion is itself the
    one part, and `entity_field` is its relation for the entity. `copies` are taken from the document the entity is
    made from. `offered` says where it is offered (any of them; none: everywhere)"""

    name: str
    document: str
    field: str | None = None
    parts: tuple[CompanionPart, ...] = ()
    entity_field: str | None = None
    copies: tuple[CopyFromOuter, ...] = ()
    offered: tuple[Within | Standalone, ...] = ()

    def __post_init__(self):
        for name in ("parts", "copies", "offered"):
            object.__setattr__(self, name, _tuple(getattr(self, name)))

    @property
    def slots(self) -> tuple[tuple[str | None, str], ...]:
        """Where the entity goes: (the type of each part, or `None` for the companion itself; the field)"""
        if self.field is None:
            return ((None, self.entity_field or ""),)
        return tuple((part.type, part.entity_field) for part in self.parts)


def companions_of(model: type) -> tuple[Companion, ...]:
    """The companions an entity class has (its own, or those it inherits)"""
    return tuple(getattr(getattr(model, "_meta", None), "companions", None) or ())


def companion_named(model: type, name: str) -> Companion | None:
    return next((c for c in companions_of(model) if c.name == name), None)


def _refused(message: str, *path: str | int):
    from pangloss_models.exceptions import PanglossWriteRefused

    error = PanglossWriteRefused(message)
    error.path = path
    return error


def _key_in(data: dict, name: str) -> str | None:
    """The key `data` has for the field `name`: as it is, or as it is in the JSON"""
    from pydantic.alias_generators import to_camel

    return next((k for k in (name, to_camel(name)) if k in data), None)


def companion_create(
    entity: type, entity_id: Any, name: str, document: dict[str, Any]
) -> Any:
    """The `Create` of the companion `name` of the class `entity`, from `document` as it is sent (by the interface:
    the parts that are filled in, without the entity), with a reference to the entity (`entity_id`) put in the field
    of each part that is for it. `PanglossWriteRefused`, with the `path` in `document`, for what the declaration does
    not allow; a pydantic `ValidationError` of the companion's model if it is not valid"""
    from pangloss_models.model_registry import ModelRegistry

    companion = companion_named(entity, name)
    if companion is None:
        names = ", ".join(c.name for c in companions_of(entity)) or "none"
        raise _refused(
            f"{entity.__name__} has no companion called {name!r} (it has: {names})"
        )
    model = ModelRegistry.all_models()[companion.document]
    data = dict(document)
    given_type = data.get("type")
    if given_type is not None and given_type != companion.document:
        raise _refused(
            f"The companion {name!r} is a {companion.document}, not a {given_type}",
            "type",
        )
    data["type"] = companion.document
    reference = {"type": entity.__name__, "id": str(entity_id)}

    def put(
        item: dict[str, Any], field_name: str, holder: type, *path: str | int
    ) -> None:
        definition = cast(Any, holder)._meta.fields[field_name]
        value = [reference] if definition.wrapper else reference
        key = _key_in(item, field_name)
        if key is not None:
            given = item[key]
            given_ids = [
                g.get("id")
                for g in (given if isinstance(given, list) else [given])
                if isinstance(g, dict)
            ]
            if given_ids != [str(entity_id)]:
                raise _refused(
                    f"{holder.__name__}.{field_name} is filled in by the server with the new {entity.__name__}: "
                    "leave it out",
                    *path,
                    key,
                )
            del item[key]
        item[field_name] = value

    if companion.field is None:
        put(data, companion.entity_field or "", model)
    else:
        key = _key_in(data, companion.field) or companion.field
        parts = list(data.get(key) or [])
        if not parts:
            raise _refused(
                f"The companion {name!r} has no parts: send it only if one is filled in",
                key,
            )
        slots = {part.type: part.entity_field for part in companion.parts}
        models = ModelRegistry.all_models()
        seen: set[str] = set()
        filled = []
        for index, part in enumerate(parts):
            part = dict(part) if isinstance(part, dict) else part
            part_type = part.get("type") if isinstance(part, dict) else None
            if part_type not in slots:
                raise _refused(
                    f"A {part_type} is not one of its parts (they are: {', '.join(slots)})",
                    key,
                    index,
                    "type",
                )
            if part_type in seen:
                raise _refused(
                    f"The part {part_type} is given twice", key, index, "type"
                )
            seen.add(part_type)
            put(part, slots[part_type], models[part_type], key, index)
            filled.append(part)
        data[key] = filled
    return cast(Any, model).Create.model_validate(data)


async def save_with_companions(
    self: Any,
    companions: dict[str, dict[str, Any]],
    detail: bool = False,
    **options: Any,
) -> tuple[Any, list[Any]]:
    """`Entity.Create(...).save_with_companions({name: document, ...})`: the entity, and each companion named (as it
    is sent: without the entity, which is put in it), made in one transaction (`create_heads`). Gives the entity's
    `ReferenceView` and the companions', or with `detail` their `HeadView`s. A refusal of a companion has the `path`
    `("companions", index, "document", ...)`, its index in the order given (the API's body has the same shape)"""
    from pangloss_models.creators import creators_asked, requested_creators, writing_as
    from pangloss_models.together import create_heads

    creators = (
        creators_asked(options.get("created_by"), options.get("toolchain"))
        or requested_creators.get()
    )
    with writing_as(creators):
        entity = self._to_db_model()
    made = []
    for index, (name, document) in enumerate(companions.items()):
        try:
            made.append(companion_create(self._owner, entity.id, name, document))
        except Exception as error:
            path = getattr(error, "path", None)
            if isinstance(path, tuple):
                cast(Any, error).path = ("companions", index, "document", *path)
            raise
    written = await create_heads(entity, *made, detail=detail, **options)
    return written[0], written[1:]
