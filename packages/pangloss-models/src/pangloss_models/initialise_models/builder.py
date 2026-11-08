"""Makes `Create`, `CreateDB`, `Update`, `UpdateDB` and `View` for a declared model.

One implementation, driven by a `ModelKind` (`kinds.py`) for each of them. The five modules
`initialise_create_model`, `initialise_create_db_model`, ... are thin entry points that call it.

The steps, for a kind:

1. `initialise_model`: make the model for a declared class (named, based on the right base class, with
   `type`, `label`, and `id` and `create_new` if the class can be given an id).
2. `add_fields`: give it its fields, from the field definitions of the declared class. A relation
   field is worked out by `relation_annotation`, which says what may be given for each type the
   relation allows.
3. For a relation to a generic wrapper (`InRole[Person]`) or to a document with bindings, a model is
   made for that use: `build_generic_model` and `build_bound_model`.
"""

from typing import Annotated, Any, ClassVar, Literal, Union
from uuid import UUID

from pydantic import AnyHttpUrl, ConfigDict, Field
from pydantic import create_model as pydantic_create_model
from pydantic.alias_generators import to_camel
from pydantic.fields import FieldInfo

from pangloss_models import literals
from pangloss_models.field_definitions import (
    FieldBinding,
    FieldDefinition,
    ListFieldDefinition,
    RelationFieldDefinition,
    RelationToDocument,
    RelationToEntity,
    RelationToGeneric,
    RelationToTypeVar,
)
from pangloss_models.initialise_models.common import (
    can_have_action_models,
    get_model_validators,
    pick_base_class,
    recursively_get_generic_naming,
)
from pangloss_models.initialise_models.kinds import (
    KINDS,
    FieldRule,
    ModelKind,
    Site,
)
from pangloss_models.initialise_models.tagged_union import (
    TaggedUnion,
    choose_by_tag,
)
from pangloss_models.model_bases.binding import bound_names
from pangloss_models.model_bases.model_tools import rebuild, set_field
from pangloss_models.utils import (
    annotation_is_optional,
    field_has_inherited_field_bindings,
    map_validators_to_kwargs,
    with_constraints,
)

# Models made for a use of a model with bindings, by (kind, the model, the bindings). They hold a
# reference to the declared class, so they belong to the registry that the class is in.
_bound_models: dict[tuple[str, type, frozenset[FieldBinding]], type] = {}

# The models made for a generic in `Update`, by (kind, the generic use, the bindings)
_generic_models: dict[tuple[str, Any, frozenset[FieldBinding]], type] = {}


def clear_caches() -> None:
    """Forget the models made for bindings and generics (the registry has been emptied)"""
    _bound_models.clear()
    _generic_models.clear()


# --- the model itself ------------------------------------------------------------------------------


def initialise_model(kind: ModelKind, model: type) -> None:
    """Make `kind` for a declared model, unless there is one already (the models refer to each other,
    so a model is made once)"""
    if not can_have_action_models(model):
        return
    if kind.attribute in model.__dict__:
        return
    base = pick_base_class(model, kind.bases)
    if not base:
        return

    name = model.__name__
    made = pydantic_create_model(
        f"{name}{kind.attribute}",
        __base__=base,
        __validators__=get_model_validators(
            model, kind.base_validators, kind.declared_validators
        ),
        __module__=model.__module__,
        _owner=(ClassVar[model], model),
        __doc__=model._meta.description if model._meta.description else "",  # type: ignore[attr-defined]
        __config__=config_for(kind),
        type=(Literal[name], name),
    )
    setattr(model, kind.attribute, made)

    if kind.id_fields:
        add_id_fields(made)
    add_label_field(made)
    rebuild(made)


def config_for(kind: ModelKind) -> ConfigDict:
    """The config of a generated model: camelCase aliases, and for the models a client sends no key the
    model has no field for (a misspelt key would otherwise be dropped, and the document saved without it)"""
    if kind.forbid_extra:
        return ConfigDict(alias_generator=to_camel, extra="forbid")
    return ConfigDict(alias_generator=to_camel)


def add_id_fields(made: type) -> None:
    """`id` and `create_new`, for a class that can be given an id"""
    meta = made._owner._meta  # type: ignore[attr-defined]
    if getattr(meta, "create_with_id", False):
        annotation: Any = UUID | None
        if getattr(meta, "accept_url_as_id", False):
            annotation = UUID | AnyHttpUrl | None
        set_field(made, "id", FieldInfo(annotation=annotation, default=None))
        set_field(
            made, "create_new", FieldInfo(annotation=Literal[True] | None, default=None)
        )
        rebuild(made)


def add_label_field(made: type) -> None:
    if getattr(made._owner._meta, "require_label", True):  # type: ignore[attr-defined]
        set_field(made, "label", FieldInfo(annotation=str))


# --- the fields ------------------------------------------------------------------------------------


def holds(rule: FieldRule, which: str, conditions: dict[str, bool]) -> bool:
    wanted = rule.nullable_when if which == "nullable" else rule.default_none_when
    return any(conditions[c] for c in wanted)


def add_fields(
    kind: ModelKind, model: type, fields_to_bind: frozenset[FieldBinding]
) -> None:
    """Give a model made for `kind` its fields, from the field definitions of the declared class.

    `fields_to_bind` are the bindings of the relation that this model is the target of: a field that
    one of them fills need not be given."""
    owner = model._owner  # type: ignore[attr-defined]
    fields = owner._meta.fields
    bindings = fields_to_bind if kind.applies_bindings else frozenset()

    def conditions(
        name: str, definition: FieldDefinition, fulfil: bool
    ) -> dict[str, bool]:
        return {
            "bound": field_has_inherited_field_bindings(
                bindings, bound_names(name, definition), definition.field_on_model
            ),
            "fulfil": fulfil,
            "optional": annotation_is_optional(definition.annotated_type)
            or getattr(definition, "optional", False),
        }

    def describe(definition: FieldDefinition) -> dict[str, Any]:
        return {"description": definition.description if kind.descriptions else None}

    def skipped(definition: FieldDefinition) -> bool:
        return kind.skip_db_fields and definition.db_field

    for name, definition in fields.literal_fields.items():
        if skipped(definition):
            continue
        when = conditions(name, definition, bool(definition.field_required_to_fulfil))
        # (from the annotation, so that what the class annotated the field with is the field's metadata, as
        # pydantic has it for a field declared in a class)
        info = FieldInfo.from_annotation(
            value_annotation(definition, holds(kind.literal, "nullable", when))
        )
        info.validation_alias = to_camel(name)
        info.description = describe(definition)["description"]
        set_field(model, name, info)
        if definition.has_default:
            # (the default the class declares, as pydantic would have it: a field with one may be left out)
            if definition.default_factory is not None:
                info.default_factory = definition.default_factory
            else:
                info.default = definition.default
        elif holds(kind.literal, "default", when):
            info.default = None
        elif definition.db_field and isinstance(definition, ListFieldDefinition):
            # a list only the database side has is filled in by a validator the class declares, so it may be left out
            info.default_factory = list

    for name, definition in fields.embedded_fields.items():
        if skipped(definition):
            continue
        when = conditions(name, definition, bool(definition.field_required_to_fulfil))
        annotation = embedded_annotation(kind, definition)
        if holds(kind.embedded, "nullable", when):
            annotation = annotation | None
        set_field(
            model,
            name,
            choose_by_tag(
                kind,
                FieldInfo(
                    annotation=annotation,
                    validation_alias=to_camel(name),
                    discriminator="type" if kind.discriminated else None,
                    **describe(definition),
                ),
            ),
        )
        if holds(kind.embedded, "default", when):
            model.model_fields[name].default = None  # type: ignore[attr-defined]

    for name, definition in fields.relation_fields.items():
        if skipped(definition):
            continue
        relation_bindings = (
            frozenset([*definition.bind_to_child_field, *bindings])
            if kind.applies_bindings
            else frozenset()
        )
        annotation = relation_annotation(kind, definition, relation_bindings)
        if annotation is None:
            continue
        fulfil = (
            bool(definition.field_required_to_fulfil)
            and not definition.subclasses_parent_fields
        )
        when = conditions(name, definition, fulfil)
        nullable = holds(kind.relation, "nullable", when)
        if nullable:
            annotation = Union[annotation, None]  # type: ignore[assignment]
        set_field(
            model,
            name,
            choose_by_tag(
                kind,
                FieldInfo(
                    annotation=annotation,
                    validation_alias=to_camel(name),
                    discriminator="type"
                    if kind.discriminated and not definition.wrapper
                    else None,
                    **describe(definition),
                    **map_validators_to_kwargs(definition.validators),
                ),
            ),
        )
        if holds(kind.relation, "default", when):
            model.model_fields[name].default = None  # type: ignore[attr-defined]
        elif kind.empty_list_default and definition.wrapper:
            # A relation with no items has no edges, so nothing to read back
            model.model_fields[name].default_factory = definition.wrapper  # type: ignore[attr-defined]

    for name, definition in fields.annotated_value_fields.items():
        if skipped(definition):
            continue
        when = conditions(name, definition, bool(definition.field_required_to_fulfil))
        annotation = definition.annotated_type
        if holds(kind.annotated_value, "nullable", when):
            annotation = annotation | None
        set_field(model, name, FieldInfo(annotation=annotation, **describe(definition)))
        if holds(kind.annotated_value, "default", when):
            model.model_fields[name].default = None  # type: ignore[attr-defined]

    rebuild(model)


def value_annotation(definition: Any, nullable: bool) -> Any:
    """The annotation of a literal or list field on a generated model: the declared type with what the class
    annotated it with (`Ge(1)`, `StringConstraints(...)`, an `AfterValidator`) carried in an `Annotated`, and
    `| None` if the class declared it optional or the kind of model makes it so"""
    declared = definition.annotated_type
    optional = annotation_is_optional(declared) or nullable
    annotation = with_constraints(
        literals.without_none(declared), definition.validators
    )
    return annotation | None if optional else annotation


def embedded_annotation(kind: ModelKind, definition: Any) -> Any:
    """What may be given for an embedded object: its model (and, in `Update`, a new one)"""
    # (in a fixed order, as for a relation: the options are a set)
    types = []
    for option in sorted(definition.type_options, key=option_order):
        for name in kind.offers:
            # (the embedded model may come after the model with the field: a binding on `Order.thing_ordered`
            # reaches `SealedLetter`, and so its `Seal`, through the abstract `Statement`, which the order of
            # making the models does not see. Its fields are given to it in its turn)
            initialise_model(KINDS[name], option.annotated_type)
            types.append(getattr(option.annotated_type, name))
    return Union[*types]  # type: ignore[valid-type]


# --- relations -------------------------------------------------------------------------------------


def with_edge(types: list[type], edge_model: Any) -> list[type]:
    return [t.apply_edge_model(edge_model) for t in types] if edge_model else types  # type: ignore[attr-defined]


def entity_types(kind: ModelKind, option: RelationToEntity, site: Site) -> list[type]:
    """What may be given for a relation to an entity: a reference to it and, if it is named by the
    document that needs it (`create_inline`), the entity itself"""
    entity = option.annotated_type
    offer_inline = entity._meta.create_inline and (
        kind.inline_plain if not option.edge_model else site in kind.inline_with_edge
    )
    types = [getattr(entity, kind.reference)]
    if offer_inline:
        # (the entity may come after the model with the relation to it)
        initialise_model(KINDS[kind.inline], entity)
        inline = getattr(entity, kind.inline)
        first = (site, bool(option.edge_model)) in kind.inline_first
        types = [inline, *types] if first else [*types, inline]
    return with_edge(types, option.edge_model)


def document_types(
    kind: ModelKind,
    option: RelationToDocument,
    bindings: frozenset[FieldBinding],
    site: Site,
) -> list[type]:
    """What may be given for a relation to a document: the document, made with any bindings"""
    document = option.annotated_type
    names = (
        kind.document_typevar
        if site == "typevar" and kind.document_typevar
        else kind.offers
    )
    types = []
    for name in names:
        offered = KINDS[name]
        initialise_model(offered, document)
        model = getattr(document, name)
        if bindings and offered.applies_bindings:
            model = build_bound_model(offered, model, bindings)
        types.append(model)
    return with_edge(types, option.edge_model)


def generic_types(
    kind: ModelKind, option: RelationToGeneric, bindings: frozenset[FieldBinding]
) -> list[type]:
    """What may be given for a relation to a generic wrapper such as `InRole[Person]`"""
    types = []
    for name in kind.offers:
        offered = KINDS[name]
        types.append(
            build_generic_model(
                offered, option, bindings if offered.applies_bindings else frozenset()
            )
        )
    return with_edge(types, option.edge_model)


def relation_annotation(
    kind: ModelKind,
    definition: RelationFieldDefinition,
    bindings: frozenset[FieldBinding],
) -> Any:
    """The annotation of a relation field: a union of what may be given for each type it allows
    (in a list, if it is one). None if it allows nothing."""
    types: list[type] = []
    # (in a fixed order: the options are a set, and the order of a union is the order here)
    for option in sorted(definition.type_options, key=option_order):
        if isinstance(option, RelationToEntity):
            types.extend(entity_types(kind, option, "field"))
        elif isinstance(option, RelationToDocument):
            types.extend(document_types(kind, option, bindings, "field"))
        elif isinstance(option, RelationToGeneric):
            types.extend(generic_types(kind, option, bindings))

    if not types:
        return None
    return wrap_in_union(kind, definition, types)


def union_order(member: Any) -> tuple[str, str]:
    """A fixed order for the members of a union that come from a set (whose order differs from
    one run to the next: hash randomisation, and so would the schemas and stubs made from it)"""
    return (
        str(getattr(member, "__module__", "")),
        str(getattr(member, "__qualname__", member)),
    )


def option_order(option: Any) -> tuple[str, str]:
    return (type(option).__name__, repr(getattr(option, "annotated_type", option)))


def wrap_in_union(
    kind: ModelKind, definition: RelationFieldDefinition, types: list[type]
) -> Any:
    union = Union[*types]  # type: ignore[valid-type]
    if definition.wrapper:
        return definition.wrapper[Annotated[union, union_choice(kind, types)]]  # type: ignore[index]
    return union


def union_choice(kind: ModelKind, types: list[type]) -> Any:
    """What makes the choice of a member of a union: its `type` if the kind is discriminated, else the
    tagged union (see `tagged_union.py`)"""
    if kind.discriminated:
        return Field(discriminator="type")
    if len(types) > 1:
        return TaggedUnion(types)
    return Field()


# --- generics --------------------------------------------------------------------------------------


def build_generic_model(
    kind: ModelKind, type_option: RelationToGeneric, bindings: frozenset[FieldBinding]
) -> type:
    """The model for a use of a generic wrapper in a relation (`InRole[Person]`): the wrapper's model,
    with the types that its type variables stand for put in its relations"""
    if not kind.cache_generic:
        return _build_generic_model(kind, type_option, bindings)
    key = (kind.attribute, type_option, bindings)
    if key not in _generic_models:
        _generic_models[key] = _build_generic_model(kind, type_option, bindings)
    return _generic_models[key]


def _build_generic_model(
    kind: ModelKind, type_option: RelationToGeneric, bindings: frozenset[FieldBinding]
) -> type:
    generic = type_option.base_type

    # The wrapper's own model, with the fields that are not type variables
    initialise_model(KINDS[kind.copy_fields_from], generic)
    initialise_model(kind, generic)
    base = getattr(generic, kind.attribute)
    add_fields(kind, base, frozenset())
    rebuild(base)

    type_names = recursively_get_generic_naming(type_option.parameter_type_options)
    bound = pydantic_create_model(
        f"{generic.__name__}[{type_names}]{kind.attribute}",
        __base__=base,
        __validators__=get_model_validators(
            generic, kind.generic_validators, kind.declared_validators
        ),
        __module__=generic.__module__,
        _owner=(ClassVar[generic], generic),
        __config__=config_for(kind),
        type=(Literal[generic.__name__], generic.__name__),
    )

    if bindings and kind.bind_generic_itself:
        bound = build_bound_model(kind, bound, bindings)

    # (a model made from a base class does not take its fields: they are put on, by hand)
    for name, field in getattr(generic, kind.copy_fields_from).model_fields.items():
        set_field(bound, name, field)

    for name, definition in generic._meta.fields.relation_fields.items():
        types: list[type] = []
        for generic_option in definition.type_options:
            if isinstance(generic_option, RelationToTypeVar):
                # what the type variable stands for in this use
                stands_for = type_option.parameter_type_options[
                    generic_option.type_var_name
                ]
                for option in generic_option.stand_in(stands_for.type_options):
                    if isinstance(option, RelationToEntity):
                        types.extend(entity_types(kind, option, "typevar"))
                    elif isinstance(option, RelationToDocument):
                        types.extend(document_types(kind, option, bindings, "typevar"))
                    elif isinstance(option, RelationToGeneric):
                        types.extend(generic_types(kind, option, bindings))
            elif isinstance(generic_option, RelationToEntity):
                types.extend(entity_types(kind, generic_option, "direct"))
            elif isinstance(generic_option, RelationToDocument):
                types.extend(document_types(kind, generic_option, bindings, "direct"))

        set_field(
            bound,
            name,
            choose_by_tag(
                kind,
                FieldInfo(
                    annotation=wrap_in_union(kind, definition, types),
                    validation_alias=to_camel(name),
                    # (as for the fields of any model: `metadata=` would not be applied)
                    **map_validators_to_kwargs(definition.validators),
                    discriminator="type"
                    if kind.discriminated and not definition.wrapper
                    else None,
                    description=definition.description if kind.descriptions else None,
                ),
            ),
        )
        if kind.empty_list_default and definition.wrapper:
            # (as in `add_fields`: a relation with no items has no edges, so nothing to read back)
            bound.model_fields[name].default_factory = definition.wrapper  # type: ignore[attr-defined]
        rebuild(bound)

    return bound


# --- bindings --------------------------------------------------------------------------------------


def build_bound_model(
    kind: ModelKind, model: type, bindings: frozenset[FieldBinding]
) -> type:
    """The model for a use of `model` where a parent gives some of its fields a value (the bindings of
    the relation): those fields need not be given"""
    key = (kind.attribute, model, bindings)
    if key in _bound_models:
        return _bound_models[key]

    owner = model._owner  # type: ignore[attr-defined]
    names = ",".join(sorted(str(binding) for binding in bindings))
    bound = pydantic_create_model(
        f"{model.__name__}[bound=({names})]{kind.bound_suffix}",
        __base__=model,
        __validators__=get_model_validators(
            owner, kind.bound_validators, kind.declared_validators
        ),
        __module__=owner.__module__,
        _owner=(ClassVar[owner], owner),
        __config__=config_for(kind),
        type=(Literal[owner.__name__], owner.__name__),
    )
    _bound_models[key] = bound

    if kind.bound_id_fields:
        add_id_fields(bound)
    add_label_field(bound)
    add_fields(kind, bound, bindings)
    rebuild(bound)
    return bound
