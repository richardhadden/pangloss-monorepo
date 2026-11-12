"""The names a `Companion` gives, against the models (implementation_docs/companion-documents.md): one that is misspelt does not
fail, it is never offered, or its entity is never put anywhere."""

from pangloss_models.companions import Companion, CopyFromOuter, Within, companions_of
from pangloss_models.diagnostics import reported
from pangloss_models.exceptions import AtString, PanglossModelError, did_you_mean
from pangloss_models.field_definitions import (
    FieldDefinition,
    RelationFieldDefinition,
)
from pangloss_models.model_bases.binding import NOT_MODELS


def _refuse(
    where: str, message: str, option: str, value: str, candidates=()
) -> PanglossModelError:
    candidates = sorted(candidates)
    return PanglossModelError(
        f"{where}: {message}" + (did_you_mean(value, candidates) if candidates else ""),
        at_string=AtString(option, value, tuple(candidates)),
    )


def _fields(model: type) -> dict[str, FieldDefinition]:
    return dict(getattr(getattr(model, "_meta", None), "fields", {}) or {})


def _option_types(definition: RelationFieldDefinition) -> set[type]:
    return {option.annotated_type for option in definition.type_options}


def _same_kind(source: FieldDefinition, target: FieldDefinition) -> bool:
    """Whether a value of `source` can be given to `target`: fields of one kind, and a relation to no type the target
    does not take, or a literal of the same type"""
    if type(source) is not type(target):
        return False
    if isinstance(source, RelationFieldDefinition) and isinstance(
        target, RelationFieldDefinition
    ):
        return _option_types(source) <= _option_types(target) and (
            source.wrapper is None or target.wrapper is not None
        )
    return getattr(source, "annotated_type", None) == getattr(
        target, "annotated_type", None
    )


def check_companion(entity: type, companion: Companion) -> None:
    from pangloss_models.model_registry import ModelRegistry

    models = ModelRegistry.all_models()
    where = f"{entity.__name__}: Companion(name={companion.name!r})"

    document = models.get(companion.document)
    if document is None:
        raise _refuse(
            where,
            f"there is no model called {companion.document!r}.",
            "document",
            companion.document,
            models,
        )
    if getattr(document, "__metatype__", None) != "Document":
        raise PanglossModelError(
            f"{where}: {companion.document} is not a document. A companion is a document, written with the entity",
            at_string=AtString("document", companion.document),
        )
    if document._meta.abstract or not document._meta.create_directly:
        raise PanglossModelError(
            f"{where}: {companion.document} cannot be made on its own"
            + (
                " (it is abstract)"
                if document._meta.abstract
                else " (`create_directly=False`)"
            )
            + ", so it cannot be a companion. Use a concrete document that can",
            at_string=AtString("document", companion.document),
        )
    document_fields = _fields(document)

    def check_entity_field(
        holder: type, name: str, option: str = "entity_field"
    ) -> None:
        holder_fields = _fields(holder)
        relations = {
            n: d
            for n, d in holder_fields.items()
            if isinstance(d, RelationFieldDefinition)
        }
        definition = relations.get(name)
        if definition is None:
            raise _refuse(
                where,
                f"{holder.__name__} has no relation called {name!r} to put the {entity.__name__} in.",
                option,
                name,
                relations,
            )
        # (an abstract entity's companions are those of the classes below it: each must fit)
        concrete = [
            m
            for m in models.values()
            if isinstance(m, type)
            and issubclass(m, entity)
            and getattr(m, "__metatype__", None) == "Entity"
            and not m._meta.abstract
        ]
        if not set(concrete) <= _option_types(definition):
            raise PanglossModelError(
                f"{where}: {holder.__name__}.{name} cannot hold a {entity.__name__} "
                f"(it holds {', '.join(sorted(t.__name__ for t in _option_types(definition)))})",
                at_string=AtString(option, name),
            )

    if companion.field is None:
        if companion.parts:
            raise PanglossModelError(
                f"{where}: has parts but no `field` to hold them. Give the companion's list relation as `field`",
            )
        if not companion.entity_field:
            raise PanglossModelError(
                f"{where}: without a `field`, the companion is itself the one part, and needs an `entity_field`: "
                f"the relation of {companion.document} to put the {entity.__name__} in",
            )
        check_entity_field(document, companion.entity_field)
    else:
        if companion.entity_field:
            raise PanglossModelError(
                f"{where}: with a `field`, the entity goes in the `entity_field` of each part, not of the companion. "
                "Leave out `entity_field`",
                at_string=AtString("entity_field", companion.entity_field),
            )
        relation = document_fields.get(companion.field)
        lists = [
            n
            for n, d in document_fields.items()
            if isinstance(d, RelationFieldDefinition) and d.wrapper
        ]
        if not isinstance(relation, RelationFieldDefinition):
            raise _refuse(
                where,
                f"{companion.document} has no list relation called {companion.field!r}.",
                "field",
                companion.field,
                lists,
            )
        if not relation.wrapper:
            raise PanglossModelError(
                f"{where}: {companion.document}.{companion.field} is not a list, so it cannot hold parts",
                at_string=AtString("field", companion.field),
            )
        if not companion.parts:
            raise PanglossModelError(
                f"{where}: has a `field` but no `parts` to put in it"
            )
        held = {
            t.__name__: t
            for t in _option_types(relation)
            if getattr(t, "__metatype__", None) == "Document"
        }
        seen: set[str] = set()
        for part in companion.parts:
            if part.type in seen:
                raise PanglossModelError(
                    f"{where}: the part {part.type} is given twice",
                    at_string=AtString("type", part.type),
                )
            seen.add(part.type)
            if part.type not in held:
                if part.type in models:
                    raise PanglossModelError(
                        f"{where}: {companion.document}.{companion.field} cannot hold a {part.type} itself "
                        f"(it holds {', '.join(sorted(held))})",
                        at_string=AtString("type", part.type, tuple(sorted(held))),
                    )
                raise _refuse(
                    where,
                    f"there is no model called {part.type!r}.",
                    "type",
                    part.type,
                    held,
                )
            check_entity_field(held[part.type], part.entity_field)

    within = [o for o in companion.offered if isinstance(o, Within)]
    _check_within(where, within, models)
    for copy in companion.copies:
        _check_copy(where, companion, copy, document_fields, within, models)

    names = [c.name for c in companions_of(entity)]
    if names.count(companion.name) > 1:
        raise PanglossModelError(
            f"{where}: {entity.__name__} has two companions called {companion.name!r} (the name is given twice)",
            at_string=AtString("name", companion.name),
        )


def _check_within(where: str, within: list[Within], models: dict[str, type]) -> None:
    every_name = set(models) | {
        parent.__name__
        for other in models.values()
        for parent in other.__mro__
        if not parent.__module__.startswith(NOT_MODELS)
    }
    by_name = {
        parent.__name__: parent
        for other in models.values()
        for parent in other.__mro__
        if not parent.__module__.startswith(NOT_MODELS)
    }
    for offer in within:
        for option in ("heads", "holders"):
            for name in getattr(offer, option):
                if name not in every_name:
                    raise _refuse(
                        where,
                        f"there is no model called {name!r}.",
                        option,
                        name,
                        every_name,
                    )
        for written in offer.fields:
            class_name, dot, field_name = written.partition(".")
            if not dot:
                raise PanglossModelError(
                    f"{where}: Within(fields=[... {written!r} ...]) is written Class.field "
                    "(`Statement.involves`), so that the field is known",
                    at_string=AtString("fields", written),
                )
            if class_name not in every_name:
                raise _refuse(
                    where,
                    f"there is no model called {class_name!r}.",
                    "fields",
                    written,
                    [f"{n}.{field_name}" for n in every_name],
                )
            fields = _fields(models.get(class_name) or by_name[class_name])
            if not fields:
                # (a trait or another class above a model has no fields of its own made: the models below it have)
                fields = {
                    n: d
                    for m in models.values()
                    if by_name[class_name] in m.__mro__
                    for n, d in _fields(m).items()
                }
            if field_name not in fields:
                raise _refuse(
                    where,
                    f"{class_name} has no field called {field_name!r}.",
                    "fields",
                    written,
                    [f"{class_name}.{n}" for n in fields],
                )


def _check_copy(
    where: str,
    companion: Companion,
    copy: CopyFromOuter,
    document_fields: dict[str, FieldDefinition],
    within: list[Within],
    models: dict[str, type],
) -> None:
    target = document_fields.get(copy.target)
    if target is None:
        raise _refuse(
            where,
            f"{companion.document} has no field called {copy.target!r} to copy into.",
            "to" if copy.to else "field",
            copy.target,
            document_fields,
        )
    heads = [models[name] for offer in within for name in offer.heads if name in models]
    if not heads:
        every_field = {n for m in models.values() for n in _fields(m)}
        if copy.field not in every_field:
            raise _refuse(
                where,
                f"no model has a field called {copy.field!r} to copy.",
                "field",
                copy.field,
                every_field,
            )
        return
    for head in heads:
        fields = _fields(head)
        source = fields.get(copy.field)
        if source is None:
            raise _refuse(
                where,
                f"{head.__name__} (a head it is offered within) has no field called {copy.field!r} to copy.",
                "field",
                copy.field,
                fields,
            )
        if not _same_kind(source, target):
            raise PanglossModelError(
                f"{where}: {head.__name__}.{copy.field} cannot be copied into {companion.document}.{copy.target}: "
                "they are not fields of the same type",
                at_string=AtString("field", copy.field),
            )


def check_companions(models: list[type]) -> None:
    """Raise `PanglossModelError` for a companion that names a model or field that does not exist, or cannot be used"""
    for model in models:
        if getattr(model, "__metatype__", None) != "Entity":
            continue
        # (each is checked where it is declared: a subclass that inherits it would only say the same again)
        inherited = [c for parent in model.__mro__[1:] for c in companions_of(parent)]
        for companion in companions_of(model):
            if companion in inherited:
                continue
            with reported(model):
                check_companion(model, companion)
