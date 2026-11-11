"""The checks of `Meta(label_template=...)` at `initialise()`: every path names fields that are there, goes no further
than an entity (a reference has only its label), and ends in something that can be written as text"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from pangloss_models.diagnostics import reported
from pangloss_models.exceptions import AtString, PanglossModelError, did_you_mean
from pangloss_models.field_definitions import (
    AnnotatedValueFieldDefinition,
    EmbeddedFieldDefinition,
    FieldDefinition,
    ListFieldDefinition,
    LiteralFieldDefinition,
    RelationFieldDefinition,
    RelationOption,
    RelationToConjunction,
    RelationToDocument,
    RelationToEntity,
    RelationToReifiedRelation,
    RelationToReifiedRelationDocument,
    RelationToSemanticSpace,
    RelationToTypeVar,
)
from pangloss_models.label_templates import (
    WRAPPERS,
    Formatter,
    Group,
    LabelTemplate,
    Part,
    Placeholder,
    label_formatter,
)

type Params = dict[str, Iterable[RelationOption]]


@dataclass(frozen=True)
class Place:
    """What a path can have reached: a model (with what its type variables stand for), an entity (referred to: only its
    label), a literal of a type, or something that cannot be told (a type variable not given here)"""

    kind: str
    model: Any = None
    params: tuple[tuple[str, frozenset[RelationOption]], ...] = ()


UNKNOWN = Place("unknown")


def _with_subclasses(model: type) -> list[type]:
    found = [model]
    for sub in model.__subclasses__():
        if (
            getattr(sub, "_meta", None) is not None
            and "field_definitions" in type(sub._meta).model_fields
        ):
            found.extend(_with_subclasses(sub))
    return found


def _fields(model: type) -> dict[str, FieldDefinition]:
    meta = getattr(model, "_meta", None)
    definitions = getattr(meta, "field_definitions", None)
    return dict(definitions.fields) if definitions is not None else {}


def _option_places(option: RelationOption, params: Params) -> Iterator[Place]:
    match option:
        case RelationToEntity():
            yield Place("entity", option.annotated_type)
        case RelationToDocument():
            yield Place("model", option.annotated_type)
        case (
            RelationToReifiedRelation()
            | RelationToReifiedRelationDocument()
            | RelationToConjunction()
            | RelationToSemanticSpace()
        ):
            given = tuple(
                (name, frozenset(parameter.type_options))
                for name, parameter in option.parameter_type_options.items()
            )
            yield Place("model", option.base_type, given)
        case RelationToTypeVar():
            options = params.get(option.type_var_name)
            if options is None:
                yield UNKNOWN
            else:
                for each in options:
                    yield from _option_places(each, {})
        case _:
            yield UNKNOWN


def _field_places(definition: FieldDefinition, params: Params) -> Iterator[Place]:
    match definition:
        case RelationFieldDefinition():
            for option in definition.type_options:
                yield from _option_places(option, params)
        case EmbeddedFieldDefinition():
            for option in definition.type_options:
                yield Place("model", option.annotated_type)
        case LiteralFieldDefinition():
            yield Place("literal", definition.annotated_type)
        case ListFieldDefinition():
            yield Place("literal", definition.inner_type)
        case AnnotatedValueFieldDefinition():
            yield Place("annotated", definition.annotated_type)
        case _:
            yield UNKNOWN


def _contents(model: type, params: Params) -> Iterator[Place]:
    """What a wrapper holds: a reified relation its `target`, anything else its relations"""
    for name, definition in _fields(model).items():
        if isinstance(definition, RelationFieldDefinition) and (
            model.__metatype__ != "ReifiedRelation" or name == "target"
        ):
            yield from _field_places(definition, params)


def _step(place: Place, name: str, seen: set[type]) -> tuple[list[Place], set[str]]:
    """Where `name` goes from `place`, and the names it could have been"""
    if place.kind in ("unknown", "annotated"):
        return [UNKNOWN], set()
    if place.kind != "model":
        return [], set()
    params: Params = dict(place.params)
    reached: list[Place] = []
    names: set[str] = set()
    for model in _with_subclasses(place.model):
        fields = _fields(model)
        names.update(fields)
        if name in fields:
            reached.extend(_field_places(fields[name], params))
    if not reached and place.model.__metatype__ in WRAPPERS and place.model not in seen:
        for held in _contents(place.model, params):
            more, also = _step(held, name, seen | {place.model})
            reached.extend(more)
            names.update(also)
    return reached, names


def _describe(model: type) -> str:
    return model.__name__


def _template_of(model: type) -> Any:
    return getattr(model._meta, "label_template", None)


def _end_problem(place: Place) -> str | None:
    """Why what a placeholder ends at cannot be written as text"""
    if place.kind == "literal" and place.model is bool:
        return "a yes-or-no field, which reads as 'true' or 'false': use it in an each(...) of the item, or not at all"
    if place.kind == "model" and place.model.__metatype__ == "Embedded":
        if not any(_template_of(m) for m in _with_subclasses(place.model)):
            return (
                f"an embedded {_describe(place.model)}, which has no label_template of its own (nor a Formatter): "
                "name one of its fields, or give it a template"
            )
    return None


def check_parts(
    owner: type, source: str, parts: Iterable[Part], places: list[Place]
) -> None:
    for part in parts:
        if isinstance(part, Group):
            check_parts(owner, source, part.parts, places)
        elif isinstance(part, Placeholder):
            check_placeholder(owner, source, part, places)


def check_placeholder(
    owner: type, source: str, part: Placeholder, places: list[Place]
) -> None:
    current = places
    for at, name in enumerate(part.path):
        if entities := [p for p in current if p.kind == "entity"]:
            raise PanglossModelError(
                f"{owner.__name__}: label_template {source!r}: '{'.'.join(part.path[:at])}' is a reference to "
                f"{entities[0].model.__name__}, of which a label can only use the label, not '{name}'",
                at_string=AtString("label_template", source),
            )
        literals = [p for p in current if p.kind == "literal"]
        if literals and len(literals) == len(current):
            raise PanglossModelError(
                f"{owner.__name__}: label_template {source!r}: '{'.'.join(part.path[:at])}' is a value, which has "
                f"no field '{name}'",
                at_string=AtString("label_template", source),
            )
        reached: list[Place] = []
        names: set[str] = set()
        for place in current:
            more, also = _step(place, name, set())
            reached.extend(more)
            names.update(also)
        if not reached:
            where = ".".join(part.path[:at]) or owner.__name__
            raise PanglossModelError(
                f"{owner.__name__}: label_template {source!r}: {where} has no field '{name}'."
                + did_you_mean(name, names),
                at_string=AtString("label_template", source, tuple(sorted(names))),
            )
        current = reached
    for each in part.filters:
        if each.name == "each":
            assert each.template is not None
            check_parts(owner, source, each.template, current)
            return
        if each.name == "count":
            return
    for place in current:
        if problem := _end_problem(place):
            raise PanglossModelError(
                f"{owner.__name__}: label_template {source!r}: '{'.'.join(part.path)}' is {problem}",
                at_string=AtString("label_template", source),
            )


def check_label_template(model: type) -> None:
    template = _template_of(model)
    if template is None:
        return
    if isinstance(template, Formatter):
        if label_formatter(template.name) is None:
            raise PanglossModelError(
                f"{model.__name__}: label_template=Formatter({template.name!r}): no formatter of that name is "
                "registered (`register_label_formatter`)",
                at_string=AtString("label_template", template.name),
            )
        return
    assert isinstance(template, LabelTemplate)
    for source, parts in zip(template.alternatives, template.parsed, strict=True):
        check_parts(model, source, parts, [Place("model", model)])


def check_label_templates(models: Iterable[type]) -> None:
    for model in models:
        if getattr(model, "__metatype__", None) and getattr(model, "_meta", None):
            with reported(model):
                check_label_template(model)
