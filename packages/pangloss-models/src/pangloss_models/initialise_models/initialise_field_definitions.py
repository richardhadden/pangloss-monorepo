from collections.abc import Iterable
from inspect import isclass
from types import UnionType
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    TypeVar,
    cast,
    get_args,
    get_origin,
)

from annotated_types import BaseMetadata
from frozendict import frozendict
from pydantic.fields import FieldInfo

from pangloss_models.exceptions import PanglossModelError
from pangloss_models.field_definitions import (
    AnnotatedValueFieldDefinition,
    EmbeddedFieldDefinition,
    EmbeddedOption,
    FieldDefinition,
    FieldFulfilment,
    FieldSubclassing,
    ListFieldDefinition,
    LiteralFieldDefinition,
    LiteralTypeVarFieldDefinition,
    ParameterTypeOptions,
    RelationFieldDefinition,
    RelationOption,
    RelationToConjunction,
    RelationToDocument,
    RelationToEntity,
    RelationToReifiedRelation,
    RelationToReifiedRelationDocument,
    RelationToSemanticSpace,
    RelationToTypeVar,
    TRelationFieldDefinitionAnnotation,
)
from pangloss_models.model_bases.annotated_value import AnnotatedValue
from pangloss_models.model_bases.base_models import _DeclaredClass
from pangloss_models.model_bases.configs import RelationConfig
from pangloss_models.model_bases.conjunction import Conjunction
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.edge_model import EdgeModel
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.helpers import DBField, Fulfils
from pangloss_models.model_bases.reified_relation import (
    ReifiedRelation,
    ReifiedRelationDocument,
)
from pangloss_models.model_bases.semantic_space import SemanticSpace
from pangloss_models.model_bases.trait import NonHeritableTrait, Trait
from pangloss_models.utils import (
    check_enum_values_in,
    extract_validators,
    flatten,
    get_all_parent_classes,
    get_concrete_types,
    get_direct_instantiations_of_trait,
    get_model_and_edge_type,
    get_relation_config,
    is_embedded,
    is_list_of_embedded_or_annotated_value,
    is_list_of_literal,
    is_list_relatable,
    is_literal,
    is_parameterized_generic,
    is_relatable,
    is_union_of_embedded,
    is_via_edge,
    model_is_trait,
)

# The names of fields that the models made from a declared model have for themselves.
# (`label` is not here: a model may say `label: str` for itself, and the model made from it
# then has the label that it always has.)
RESERVED_FIELD_NAMES = frozenset(
    {
        "id",
        "type",
        "meta",
        "urls",
        "create_new",
        "db_labels",
        "context_labels",
        "semantic_spaces",
        "edge_properties",
    }
)


def build_list_field_definition(
    field_name: str,
    field_info: FieldInfo,
    model: type[_DeclaredClass],
    is_db_field: bool = False,
) -> ListFieldDefinition:
    """Build a list field definition for a literal typed list.

    This function validates that the annotation is a list of a literal type
    (for example, `list[int]` with `Literal` style supported types) and
    constructs a `ListFieldDefinition` including inner type metadata.

    Raises:
        PanglossModelError: when field annotation is not a valid literal list.
    """
    invalid = PanglossModelError(
        f"{model.__name__}.{field_name} has an invalid list field definition"
    )
    arguments = get_args(field_info.annotation) if field_info.annotation else ()
    if not arguments:
        raise invalid
    list_inner_type: Any = arguments[0]

    inner_type_validators: list[BaseMetadata] = []
    if get_origin(list_inner_type) is Annotated:
        annotated_arguments = get_args(list_inner_type)
        list_inner_type = annotated_arguments[0]
        inner_type_validators = [
            arg for arg in annotated_arguments if isinstance(arg, BaseMetadata)
        ]
    if not is_literal(list_inner_type):
        raise invalid

    return ListFieldDefinition(
        field_on_model=model,
        field_name=field_name,
        annotated_type=field_info.annotation,
        validators=[md for md in field_info.metadata if isinstance(md, BaseMetadata)],
        inner_type=list_inner_type,
        inner_type_validators=inner_type_validators,
        db_field=is_db_field,
        description=extract_field_description(field_info),
    )


def build_relation_options(
    depends_on: set[type[_DeclaredClass]],
    annotation: TRelationFieldDefinitionAnnotation,
    edge_model: type[EdgeModel] | None = None,
) -> set[RelationOption]:
    """Resolve a relation annotation into one or more relation options.

    Traverses the relation annotation, potentially handling
    - Union[...]
    - ReifiedRelation[T]
    - SemanticSpace[T]
    - Conjunction[T]
    - Document and Entity relations

    Adds the classes the relation depends on to `depends_on` (the model's `_depends_on_classes`), and returns the
    set of Matching `RelationOption` objects for the annotation.
    """
    relation_options = []

    if is_via_edge(annotation):
        annotation, edge_model = get_model_and_edge_type(annotation)

    origin = get_origin(annotation)

    if isclass(origin) and issubclass(origin, UnionType):
        for union_arg in get_args(annotation):
            relation_options.extend(
                build_relation_options(depends_on, union_arg, edge_model=edge_model)
            )

    if (
        isclass(annotation)
        and issubclass(annotation, _DeclaredClass)
        and (origin := annotation.__pydantic_generic_metadata__["origin"])
        and isclass(origin)
        and issubclass(
            origin,
            (ReifiedRelation, ReifiedRelationDocument, SemanticSpace, Conjunction),
        )
    ):
        type_args = annotation.__pydantic_generic_metadata__["args"]
        parameters = origin.__pydantic_generic_metadata__["parameters"]
        params_type_args = zip(parameters, type_args)

        for t in type_args:
            if (
                isclass(t)
                and issubclass(t, (_DeclaredClass))
                and not is_parameterized_generic(t)
            ):
                depends_on.add(t)

        type_options = {
            type_var.__name__: ParameterTypeOptions[type[origin]](
                annotated_type=type_arg,
                type_var=type_var,
                type_var_name=type_var.__name__,
                type_options=frozenset(
                    # (the edge model is the relation to the wrapper's; what the wrapper relates to
                    # has its own, if the wrapper declares it)
                    build_relation_options(depends_on, type_arg)
                ),
            )
            for type_var, type_arg in params_type_args
        }

        if issubclass(origin, ReifiedRelation):
            depends_on.add(origin)
            relation_options.append(
                RelationToReifiedRelation(
                    annotated_type=annotation,
                    edge_model=edge_model,
                    base_type=origin,
                    parameter_type_options=frozendict(type_options),
                )
            )
        if issubclass(origin, ReifiedRelationDocument):
            depends_on.add(origin)
            relation_options.append(
                RelationToReifiedRelationDocument(
                    annotated_type=annotation,
                    edge_model=edge_model,
                    base_type=origin,
                    parameter_type_options=frozendict(type_options),
                )
            )
        if issubclass(origin, SemanticSpace):
            depends_on.add(origin)
            for concrete_semantic_space in get_concrete_types(origin):
                relation_options.append(
                    RelationToSemanticSpace(
                        annotated_type=annotation,
                        edge_model=edge_model,
                        base_type=concrete_semantic_space,
                        parameter_type_options=frozendict(type_options),
                    )
                )
        if issubclass(origin, Conjunction):
            depends_on.add(origin)
            for concrete_conjunction in get_concrete_types(origin):
                relation_options.append(
                    RelationToConjunction(
                        annotated_type=annotation,
                        edge_model=edge_model,
                        base_type=concrete_conjunction,
                        parameter_type_options=frozendict(type_options),
                    )
                )

    if isclass(annotation) and issubclass(annotation, Document):
        for concrete_type in get_concrete_types(annotation):
            if concrete_type._meta.abstract:
                continue
            relation_options.append(
                RelationToDocument(
                    annotated_type=concrete_type,
                    edge_model=edge_model,
                )
            )

    if isclass(annotation) and issubclass(annotation, Entity):
        for concrete_type in get_concrete_types(annotation):
            relation_options.append(
                RelationToEntity(
                    annotated_type=concrete_type,
                    edge_model=edge_model,
                )
            )

    if isclass(annotation) and issubclass(annotation, (Trait, NonHeritableTrait)):
        for concrete_type in get_concrete_types(annotation):
            if issubclass(concrete_type, Entity):
                relation_options.append(
                    RelationToEntity(
                        annotated_type=concrete_type,
                        edge_model=edge_model,
                    )
                )
            elif issubclass(concrete_type, Document):
                relation_options.append(
                    RelationToDocument(
                        annotated_type=concrete_type,
                        edge_model=edge_model,
                    )
                )

    return set(relation_options)


def build_relatable_field_definition(
    field_name: str,
    field_info: FieldInfo,
    model: type[_DeclaredClass],
    is_db_field: bool = False,
    subclasses_parent_fields: Iterable[str | FieldSubclassing] | None = None,
) -> RelationFieldDefinition:
    """Build a RelationFieldDefinition from model field metadata.

    `subclasses_parent_fields` are the normalised declarations (see
    `normalise_and_get_subclassed_fields`); if not given, those written in the relation config.

    Supports:
    - TypeVar relation annotations (`T`, `list[T]`: the relations of a generic wrapper)
    - list[X] relations
    - single relations to a Document, Entity, trait or generic

    Applies relation subclassing hints from relation config and records the classes the
    model depends on in `model._depends_on_classes`.
    """
    relation_config = get_relation_config(field_info)
    annotation = field_info.annotation

    if (
        is_parameterized_generic(annotation)
        and isinstance((type_var := get_args(annotation)[0]), TypeVar)
        and get_origin(annotation) is list
    ):
        wrapper = list
        type_options: set[RelationOption] = {
            RelationToTypeVar(annotated_type=type_var, type_var_name=type_var.__name__)
        }

    elif isinstance(annotation, TypeVar):
        wrapper = None
        type_options = {
            RelationToTypeVar(
                annotated_type=annotation, type_var_name=annotation.__name__
            )
        }

    elif is_list_relatable(annotation):
        # If wrapped in a list, unwrap the list type
        wrapper = list
        inner = get_args(annotation)[0]

        if is_parameterized_generic(inner) and isclass(origin := get_origin(inner)):
            model._depends_on_classes.add(origin)
        elif isclass(inner):
            model._depends_on_classes.add(inner)

        type_options = build_relation_options(model._depends_on_classes, inner)

    else:
        wrapper = None

        if is_parameterized_generic(annotation) and isclass(
            origin := get_origin(annotation)
        ):
            model._depends_on_classes.add(origin)
            model._depends_on_classes.update(get_args(annotation))
        else:
            model._depends_on_classes.add(annotation)

        type_options = build_relation_options(model._depends_on_classes, annotation)

    return RelationFieldDefinition(
        field_name=field_name,
        field_on_model=model,
        annotated_type=annotation,
        type_options=type_options,
        subclasses_parent_fields=set(
            subclasses_parent_fields
            if subclasses_parent_fields is not None
            else relation_config.subclasses_parent_fields
            if relation_config
            else ()
        ),
        reverse_name=(
            relation_config.reverse_name
            if relation_config and relation_config.reverse_name
            else f"{field_name}_reverse"
        ),
        wrapper=wrapper,
        db_field=is_db_field,
        bind_to_child_field=relation_config.bind_to_child_field
        if relation_config
        else [],
        validators=extract_validators(field_info),
        description=extract_field_description(field_info),
    )


def build_embedded_field_definition(
    field_name: str,
    field_info: FieldInfo,
    model: type[_DeclaredClass],
    is_db_field: bool = False,
) -> EmbeddedFieldDefinition:
    """Construct an embedded field definition for Embedded or union embedded.

    Validates the annotation resolves into concrete embedded candidates and
    returns an `EmbeddedFieldDefinition` with concrete options.
    """
    if TYPE_CHECKING:
        assert is_embedded(field_info.annotation) or is_union_of_embedded(
            field_info.annotation
        )

    field_options: set[type[Embedded]] = get_concrete_types(field_info.annotation)

    if isclass(field_info.annotation):
        model._depends_on_classes.add(field_info.annotation)

    return EmbeddedFieldDefinition(
        field_name=field_name,
        field_on_model=model,
        annotated_type=cast(type[Embedded], field_info.annotation),
        type_options=set(
            EmbeddedOption(annotated_type=option) for option in field_options
        ),
        db_field=is_db_field,
        description=extract_field_description(field_info),
    )


def get_field_origin_model_and_definition(
    model: type[_DeclaredClass], field_name: str
) -> list[tuple[type[_DeclaredClass], FieldDefinition]]:
    """Find all parent models (including traits, and the classes that the model `Fulfils`) that
    define a given field.

    Returns a list of (origin_model, field_definition) tuples. Used to resolve subclassed fields."""

    parents_with_field: list[tuple[type[_DeclaredClass], FieldDefinition]] = []

    for parent_class in get_all_parent_classes(model):
        # (`Fulfils[X]` is a parent too, but it is not a model: what it fulfils is added below)
        if field_name in getattr(parent_class, "model_fields", {}):
            parents_with_field.append(
                (parent_class, parent_class._meta.fields[field_name])
            )

    for fulfilled_class in sorted(
        get_fulfilled_types(model), key=lambda c: c.__qualname__
    ):
        if field_name in fulfilled_class.model_fields:
            parents_with_field.append(
                (fulfilled_class, fulfilled_class._meta.fields[field_name])
            )

    return parents_with_field


def recursively_add_field_subclassings(
    field_subclassings: set[FieldSubclassing], definition: FieldDefinition
) -> None:
    """Collect all transitive subclassed relation fields into `field_subclassings`.

    Traverses a `RelationFieldDefinition` and its nested parent-field subclassing
    tree, ensuring all indirect subclassing requirements are included.
    """
    if isinstance(definition, RelationFieldDefinition):
        for spf in definition.subclasses_parent_fields:
            assert isinstance(spf, FieldSubclassing)
            assert spf.subclassed_field_definition
            field_subclassings.add(spf)
            recursively_add_field_subclassings(
                field_subclassings=field_subclassings,
                definition=spf.subclassed_field_definition,
            )


def declaring_class(
    model: type[_DeclaredClass], field_name: str, config: RelationConfig
):
    """The most basic class in `model`'s MRO that has this field with this relation config: the class
    that wrote the declaration, which its names are to be resolved against."""
    for cls in reversed(model.mro()):
        info = getattr(cls, "model_fields", {}).get(field_name)
        if info is not None and get_relation_config(info) is config:
            return cls
    return model


def normalise_and_get_subclassed_fields(
    model: type[_DeclaredClass],
) -> tuple[dict[str, FieldSubclassing], dict[str, list[FieldSubclassing]]]:
    """Normalize relation subclass declarations from model fields.

    For each field with relation config subclass declarations, validate the
    target field exists and generate a set of `FieldSubclassing` objects.
    Returns the fields that are subclassed (by name), and, for each relation field of `model`,
    its normalised declarations. (The `RelationConfig` is shared with other classes and is not changed.)
    """

    subclassed_fields = {}
    normalised: dict[str, list[FieldSubclassing]] = {}
    for field_name, field_info in model.model_fields.items():
        if relation_config := get_relation_config(field_info):
            # (a field inherited from a parent is resolved from where it was declared)
            declared_on = declaring_class(model, field_name, relation_config)
            field_subclassings: set[FieldSubclassing] = set()
            for field_subclassing in relation_config.subclasses_parent_fields:
                if isinstance(field_subclassing, FieldSubclassing):
                    if (
                        field_subclassing.field_name
                        not in field_subclassing.field_on_model.model_fields
                    ):
                        raise PanglossModelError(
                            f"{model.__name__}.{field_name} is trying to subclass a field "
                            f"('{field_subclassing.field_on_model.__name__}.{field_subclassing.field_name}') "
                            "that does not exist on a parent class"
                        )

                    recursively_add_field_subclassings(
                        field_subclassings,
                        field_subclassing.field_on_model._meta.fields[
                            field_subclassing.field_name
                        ],
                    )

                    subclassed_fields[field_subclassing.field_name] = FieldSubclassing(
                        field_name=field_subclassing.field_name,
                        disambiguator=field_subclassing.disambiguator,
                        field_on_model=field_subclassing.field_on_model,
                    )

                    field_subclassings.add(
                        subclassed_fields[field_subclassing.field_name]
                    )

                else:
                    assert isinstance(field_subclassing, str)
                    origin_classes_and_definitions = (
                        get_field_origin_model_and_definition(
                            declared_on, field_subclassing
                        )
                    )

                    if not origin_classes_and_definitions:
                        raise PanglossModelError(
                            f"{model.__name__}.{field_name} is trying to subclass a field ('{field_subclassing}') that does not exist on a parent class"
                        )

                    for origin_class, definition in origin_classes_and_definitions:
                        if definition:
                            recursively_add_field_subclassings(
                                field_subclassings, definition
                            )

                        subclassed_fields[field_subclassing] = FieldSubclassing(
                            field_subclassing,
                            disambiguator=None,
                            field_on_model=origin_class,
                        )
                        field_subclassings.add(subclassed_fields[field_subclassing])

            normalised[field_name] = list(field_subclassings)
    return subclassed_fields, normalised


def field_is_from_indirect_non_heritable_model(model: type[_DeclaredClass], field_name):
    """Check whether the field comes from an indirect non-heritable trait.

    Non-heritable trait fields should not be inherited through an indirect path.
    Returns True if the field exists in an indirect non-heritable trait.
    """
    parent_classes = get_all_parent_classes(model)
    indirect_non_heritable_classes: list[type[NonHeritableTrait]] = [
        pc
        for pc in parent_classes
        if model_is_trait(pc)
        and issubclass(pc, NonHeritableTrait)
        and model not in get_direct_instantiations_of_trait(pc)
    ]
    for indirect_nht in indirect_non_heritable_classes:
        if field_name in indirect_nht._meta.fields:
            return True
    return False


def fulfilled_types_in_order(model: type[_DeclaredClass]) -> list[type[_DeclaredClass]]:
    """The classes `model` fulfils (through `Fulfils[...]` parents), in the order they are met, each once.
    (A set would make the order of the fields depend on the hash of the classes.)"""
    found: dict[type[_DeclaredClass], None] = {}
    for parent in model.mro():
        # (each `Fulfils[...]` holds its own classes: not those of `Fulfils`, or of another)
        if isinstance(parent, type) and issubclass(parent, Fulfils):
            for fulfilled in parent.__dict__.get("_fulfilling_types", ()):
                found.setdefault(fulfilled)
    return list(found)


def get_fulfilled_types(model: type[_DeclaredClass]) -> set[type[_DeclaredClass]]:
    """Return all types fulfilled by `model` via `Fulfils` parent classes."""
    return set(fulfilled_types_in_order(model))


def get_fields_on_model(model: type[_DeclaredClass]):
    """Yields an iterable of field name, field info and set of FieldFulfilment objects for a model, removing subclassed
    fields"""

    subclassed_fields, own_normalised = normalise_and_get_subclassed_fields(model)

    fulfilled_types = fulfilled_types_in_order(model)

    fulfilled_normalised: dict[
        type[_DeclaredClass], dict[str, list[FieldSubclassing]]
    ] = {}
    for fulfilled in fulfilled_types:
        fulfilled_subclassed, fulfilled_normalised[fulfilled] = (
            normalise_and_get_subclassed_fields(fulfilled)
        )
        subclassed_fields.update(fulfilled_subclassed)

    # the fields of the classes it fulfils, each once (the first class that has it gives its definition)
    fulfilled_field_names = dict.fromkeys(
        name for fulfilled in fulfilled_types for name in fulfilled.model_fields
    )

    for field_name in fulfilled_field_names:
        if field_name == "type":
            continue

        if field_name in subclassed_fields:
            continue

        having = [f for f in fulfilled_types if field_name in f.model_fields]
        yield (
            field_name,
            having[0].model_fields[field_name],
            set(
                FieldFulfilment(field_name=field_name, fulfils_class=f) for f in having
            ),
            fulfilled_normalised[having[0]].get(field_name),
        )

    # its own fields
    for field_name, field_info in model.model_fields.items():
        if (
            field_name in subclassed_fields
            or field_is_from_indirect_non_heritable_model(model, field_name)
        ):
            continue

        config = get_relation_config(field_info)

        if config:
            yield (
                field_name,
                field_info,
                set(
                    FieldFulfilment(
                        field_name=fsc.field_name, fulfils_class=fsc.field_on_model
                    )
                    for fsc in own_normalised[field_name]
                    if fsc.field_on_model in fulfilled_types
                ),
                own_normalised[field_name],
            )
        else:
            yield field_name, field_info, set(), None


def check_subclass_type(field_definition: RelationFieldDefinition):
    """Validate that subclassed relation field types are compatible.

    For each declared subclassing (from parent field relations), ensure the
    concrete type options of the child field are a subset of the parent.
    Raises a `PanglossModelError` if the type narrowing contract is violated.
    """
    model_name = field_definition.field_on_model.__name__
    for spf in field_definition.subclasses_parent_fields:
        parent = (
            f"{getattr(spf.field_on_model, '__name__', spf.field_on_model)}.{spf.field_name}"
            if isinstance(spf, FieldSubclassing)
            else spf
        )
        if not isinstance(spf, FieldSubclassing) or not isinstance(
            spf.subclassed_field_definition, RelationFieldDefinition
        ):
            raise PanglossModelError(
                f"{model_name}.{field_definition.field_name} subclasses {parent}, "
                "which is not a relation: only a relation can be narrowed by a relation"
            )

        field_type_options = set(
            flatten(
                get_concrete_types(f.annotated_type)
                for f in field_definition.type_options
            )
        )
        subclassed_field_type_options = set(
            flatten(
                get_concrete_types(f.annotated_type)
                for f in spf.subclassed_field_definition.type_options
            )
        )

        if not field_type_options.issubset(subclassed_field_type_options):
            raise PanglossModelError(
                f"{model_name}.{field_definition.field_name} subclasses {parent} "
                "but is not of the same type or narrowing of type"
            )


def extract_field_description(field_info: FieldInfo) -> str | None:
    """The description of a field: that of its `RelationConfig`, else the `description` of its
    `Field(...)`, else a bare string given in `Annotated[...]`"""
    relation_config = get_relation_config(field_info)
    if relation_config and relation_config.description:
        return relation_config.description

    if field_info.description:
        return field_info.description

    strings = [str(md) for md in field_info.metadata if isinstance(md, str)]
    return strings[0] if strings else None


def check_model_fields_are_allowed(model: type[_DeclaredClass]) -> None:
    """The names a model may not use, and the models that may not have relations"""
    for field_name in model.model_fields:
        if field_name in RESERVED_FIELD_NAMES:
            raise PanglossModelError(
                f"'{field_name}' is a Pangloss reserved name and cannot be used as a model field "
                f"in ({model.__name__}): the models made from it have a field of that name"
            )

    for kind, name in ((EdgeModel, "EdgeModel"), (AnnotatedValue, "AnnotatedValue")):
        if issubclass(model, kind):
            for field_name, field_info in model.model_fields.items():
                if is_relatable(field_info.annotation) or is_list_relatable(
                    field_info.annotation
                ):
                    raise PanglossModelError(
                        f"{name} {model.__name__} does not support relations ({model.__name__}.{field_name})"
                    )


def is_generic_wrapper(model: type[_DeclaredClass]) -> bool:
    """A generic wrapper (`Negative`, `InRole`, ...), or a use of one (`Negative[Statement]`): its
    fields are in terms of its type variables, and are defined on the wrapper itself"""
    return model.__pydantic_generic_metadata__["origin"] is not None or model in (
        AnnotatedValue,
        Conjunction,
        ReifiedRelation,
        ReifiedRelationDocument,
        SemanticSpace,
    )


def define_wrapper_field(
    model: type[_DeclaredClass],
    field_name: str,
    field_info: FieldInfo,
    is_db_field: bool,
) -> bool:
    """Define a field of a generic wrapper that is in terms of its type variable. Returns whether it
    was one. (These are in addition to the definition any field gets, below.)"""
    definition: FieldDefinition | None = None

    if issubclass(model, AnnotatedValue) and field_name == "value":
        definition = LiteralTypeVarFieldDefinition(
            field_name=field_name,
            field_on_model=model,
            annotated_type=cast(TypeVar, field_info.annotation),
            type_var_name=str(field_info.annotation),
            db_field=is_db_field,
            description=extract_field_description(field_info),
        )
        model._meta.field_definitions.add_field(
            name=field_name, field_definition=definition
        )
        found = True
    else:
        found = False

    # (the fields of a subclass of SemanticSpace or Conjunction are all relations to what the
    # wrapper stands for)
    for base in (SemanticSpace, Conjunction):
        if (
            issubclass(model, base)
            and model is not base
            and model.__pydantic_generic_metadata__["origin"] is None
        ):
            definition = build_relatable_field_definition(
                field_name, field_info, model, is_db_field=is_db_field
            )
            model._meta.field_definitions.add_field(
                name=field_name, field_definition=definition
            )
            found = True

    if issubclass(model, (ReifiedRelation, ReifiedRelationDocument)):
        if get_origin(field_info.annotation) and isinstance(
            get_args(field_info.annotation)[0], TypeVar
        ):
            definition = build_relatable_field_definition(
                field_name, field_info, model, is_db_field=is_db_field
            )
            model._meta.field_definitions.add_field(
                name=field_name, field_definition=definition
            )
            found = True

    return found


def define_field(
    model: type[_DeclaredClass],
    field_name: str,
    field_info: FieldInfo,
    is_db_field: bool,
    subclasses_parent_fields: Iterable[str | FieldSubclassing] | None = None,
) -> FieldDefinition | None:
    """The definition of a field, by what its type is. None if the type is not one that is supported."""
    annotation = field_info.annotation

    if is_embedded(annotation) or is_union_of_embedded(annotation):
        return build_embedded_field_definition(
            field_name, field_info, model, is_db_field=is_db_field
        )

    if isclass(annotation) and issubclass(annotation, AnnotatedValue):
        return AnnotatedValueFieldDefinition(
            field_on_model=model,
            field_name=field_name,
            annotated_type=annotation,
            db_field=is_db_field,
            description=extract_field_description(field_info),
        )

    if is_relatable(annotation) or is_list_relatable(annotation):
        definition = build_relatable_field_definition(
            field_name,
            field_info,
            model,
            is_db_field=is_db_field,
            subclasses_parent_fields=subclasses_parent_fields,
        )
        check_subclass_type(definition)
        return definition

    if is_list_of_literal(annotation):
        check_enum_values_in(annotation)
        return build_list_field_definition(
            field_name, field_info, model, is_db_field=is_db_field
        )

    if is_literal(annotation):
        check_enum_values_in(annotation)
        return LiteralFieldDefinition(
            field_on_model=model,
            field_name=field_name,
            annotated_type=annotation,
            validators=[
                md for md in field_info.metadata if isinstance(md, BaseMetadata)
            ],
            db_field=is_db_field,
            description=extract_field_description(field_info),
        )

    return None


def initialise_field_definitions(model: type[_DeclaredClass]):
    """Initialise and register field definitions for the model.

    Iterates through all fields (including inherited fulfilments) and creates the
    appropriate field definitions, including literal/list/embedded/relation
    field types, while applying subclassing rules and relation config.
    """
    check_model_fields_are_allowed(model)

    for field_name, field_info, field_fulfilment, normalised in get_fields_on_model(
        model
    ):
        is_db_field = any(
            isclass(md) and issubclass(md, DBField) or isinstance(md, DBField)
            for md in field_info.metadata
        )

        # Fields of the generic wrapper base classes (`target: list[T]`) and of their
        # parametrisations (`Negative[Statement]`) are defined elsewhere (or on the
        # unparametrised subclass), so are never "unsupported".
        is_wrapper_field = define_wrapper_field(
            model, field_name, field_info, is_db_field
        )
        supported_as_wrapper_field = is_generic_wrapper(model) or is_wrapper_field

        if is_list_of_embedded_or_annotated_value(field_info.annotation):
            raise PanglossModelError(
                f"{model.__name__}.{field_name}: lists of Embedded objects or of "
                "AnnotatedValues are not supported (a field can have only one)"
            )

        definition = define_field(
            model, field_name, field_info, is_db_field, normalised
        )
        if definition is not None:
            # (what a class that `Fulfils` another must hold for every field it has from it, of any
            # kind: without them it is not that class)
            definition.field_required_to_fulfil.update(field_fulfilment)
            model._meta.field_definitions.add_field(
                name=field_name, field_definition=definition
            )
        elif not supported_as_wrapper_field:
            raise PanglossModelError(
                f"Unsupported type for field {model.__name__}.{field_name}: "
                f"{field_info.annotation!r}. Supported field types are str, int, "
                "float, bool, Decimal, date, datetime, Enum subclasses, TypedDicts "
                "of these, lists of these, and other Pangloss models"
            )
