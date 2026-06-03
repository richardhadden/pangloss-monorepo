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
    extract_relation_config,
    extract_validators,
    flatten,
    get_all_parent_classes,
    get_concrete_types,
    get_direct_instantiations_of_trait,
    get_model_and_edge_type,
    get_relation_config,
    is_embedded,
    is_list_of_literal,
    is_list_relatable,
    is_literal,
    is_parameterized_generic,
    is_relatable,
    is_single_relatable,
    is_union_of_embedded,
    is_via_edge,
    model_is_trait,
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
    try:
        assert field_info.annotation
        list_inner_type_tuple: tuple[Any, ...] = get_args(field_info.annotation)
        assert list_inner_type_tuple
        list_inner_type: Any = list_inner_type_tuple[0]

        inner_type_validators: list[BaseMetadata] = []
        if get_origin(list_inner_type) is Annotated:
            annotated_inner_type_tuple: tuple[Any, ...] = get_args(list_inner_type)
            assert annotated_inner_type_tuple
            list_inner_type = annotated_inner_type_tuple[0]
            inner_type_validators: list[BaseMetadata] = [
                arg
                for arg in annotated_inner_type_tuple
                if isinstance(arg, BaseMetadata)
            ]
        assert is_literal(list_inner_type)
        return ListFieldDefinition(
            field_on_model=model,
            field_name=field_name,
            annotated_type=field_info.annotation,
            validators=[
                md for md in field_info.metadata if isinstance(md, BaseMetadata)
            ],
            inner_type=list_inner_type,
            inner_type_validators=inner_type_validators,
            db_field=is_db_field,
            description=extract_field_description(field_info),
        )
    except AssertionError:
        raise PanglossModelError(
            f"{model.__name__}.{field_name} has an invalid list field definition"
        )


def build_relation_options(
    model: type[_DeclaredClass],
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

    Adds dependency records to `model.depends_on_classes`, and returns the
    set of Matching `RelationOption` objects for the annotation.
    """
    relation_options = []

    if is_via_edge(annotation):
        annotation, edge_model = get_model_and_edge_type(annotation)  # pyright: ignore[reportArgumentType]
    else:
        annotation = annotation
        edge_model = edge_model

    origin = get_origin(annotation)

    if isclass(origin) and issubclass(origin, UnionType):
        for union_arg in get_args(annotation):
            relation_options.extend(
                build_relation_options(model, union_arg, edge_model=edge_model)
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
                model._depends_on_classes.add(t)

        type_options = {
            type_var.__name__: ParameterTypeOptions[type[origin]](
                annotated_type=type_arg,
                type_var=type_var,
                type_var_name=type_var.__name__,
                type_options=frozenset(
                    build_relation_options(model, type_arg, edge_model=edge_model)
                ),
            )
            for type_var, type_arg in params_type_args
        }

        if issubclass(origin, ReifiedRelation):
            model._depends_on_classes.add(origin)
            relation_options.append(
                RelationToReifiedRelation(
                    annotated_type=annotation,
                    edge_model=edge_model,
                    base_type=origin,
                    parameter_type_options=frozendict(type_options),
                )
            )
        if issubclass(origin, ReifiedRelationDocument):
            model._depends_on_classes.add(origin)
            relation_options.append(
                RelationToReifiedRelationDocument(
                    annotated_type=annotation,
                    edge_model=edge_model,
                    base_type=origin,
                    parameter_type_options=frozendict(type_options),
                )
            )
        if issubclass(origin, SemanticSpace):
            model._depends_on_classes.add(origin)
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
            model._depends_on_classes.add(origin)
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
) -> RelationFieldDefinition:
    """Build a RelationFieldDefinition from model field metadata.

    Supports t:
    - TypeVar relation annotations
    - list[T] relations
    - named relation model types (Document/Entity/Relation etc.)

    Applies relation subclassing hints from relation config and updates
    `model.depends_on_classes`.
    """

    relation_config = extract_relation_config(field_info)

    validators = extract_validators(field_info)

    if relation_config:
        field_subclassings = set(relation_config.subclasses_parent_fields)
    else:
        field_subclassings = set()

    if relation_config:
        bind_to_child_field = relation_config.bind_to_child_field
    else:
        bind_to_child_field = []

    reverse_name = (
        relation_config.reverse_name
        if relation_config and relation_config.reverse_name
        else f"{field_name}_reverse"
    )

    if (
        is_parameterized_generic(field_info.annotation)
        and isinstance((arg := get_args(field_info.annotation)[0]), TypeVar)
        and get_origin(field_info.annotation) is list
    ):
        return RelationFieldDefinition(
            field_name=field_name,
            field_on_model=model,
            annotated_type=field_info.annotation,  # pyright: ignore[reportArgumentType]
            type_options=set(
                [RelationToTypeVar(annotated_type=arg, type_var_name=arg.__name__)]
            ),
            subclasses_parent_fields=field_subclassings,
            reverse_name=reverse_name,
            wrapper=list,
            db_field=is_db_field,
            bind_to_child_field=bind_to_child_field,
            validators=validators,
            description=extract_field_description(field_info),
        )
    elif isinstance(field_info.annotation, TypeVar):
        return RelationFieldDefinition(
            field_name=field_name,
            field_on_model=model,
            annotated_type=field_info.annotation,  # pyright: ignore[reportArgumentType]
            type_options=set(
                [
                    RelationToTypeVar(
                        annotated_type=field_info.annotation,
                        type_var_name=field_info.annotation.__name__,
                    )
                ]
            ),
            subclasses_parent_fields=field_subclassings,
            reverse_name=reverse_name,
            wrapper=None,
            db_field=is_db_field,
            bind_to_child_field=bind_to_child_field,
            validators=validators,
            description=extract_field_description(field_info),
        )

    elif is_list_relatable(field_info.annotation):
        if TYPE_CHECKING:
            assert field_info.annotation

        # If wrapped in a list, unwrap the list type
        annotation = get_args(field_info.annotation)[0]

        if is_parameterized_generic(annotation) and isclass(
            (origin := get_origin(annotation))
        ):
            model._depends_on_classes.add(origin)
        elif isclass(annotation):
            model._depends_on_classes.add(annotation)

        return RelationFieldDefinition(
            field_name=field_name,
            field_on_model=model,
            annotated_type=field_info.annotation,
            type_options=build_relation_options(model, annotation),
            subclasses_parent_fields=field_subclassings,
            reverse_name=reverse_name,
            wrapper=list,
            db_field=is_db_field,
            bind_to_child_field=bind_to_child_field,
            validators=validators,
            description=extract_field_description(field_info),
        )

    else:
        if TYPE_CHECKING:
            assert is_relatable(field_info.annotation)
            assert is_single_relatable(field_info.annotation)

        if is_parameterized_generic(field_info.annotation) and isclass(
            (origin := get_origin(field_info.annotation))
        ):
            model._depends_on_classes.add(origin)  # pyright: ignore[reportArgumentType]
            model._depends_on_classes.update(get_args(field_info.annotation))
        else:
            model._depends_on_classes.add(field_info.annotation)

        return RelationFieldDefinition(
            field_name=field_name,
            field_on_model=model,
            annotated_type=field_info.annotation,
            type_options=build_relation_options(model, field_info.annotation),
            subclasses_parent_fields=field_subclassings,
            reverse_name=reverse_name,
            wrapper=None,
            db_field=is_db_field,
            bind_to_child_field=bind_to_child_field,
            validators=validators,
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
        annotated_type=cast(
            type[Embedded] | type[Embedded | Embedded], field_info.annotation
        ),
        type_options=set(
            EmbeddedOption(annotated_type=option) for option in field_options
        ),
        db_field=is_db_field,
        description=extract_field_description(field_info),
    )


def get_field_origin_model_and_definition(
    model: type[_DeclaredClass], field_name: str
) -> list[tuple[type[_DeclaredClass], FieldDefinition]] | None:
    """Find all parent models (including traits) that define a given field.

    Returns a list of (origin_model, field_definition) tuples for each parent
    class where `field_name` is present. Used to resolve subclassed fields.
    """

    parents_with_field: list[tuple[type[_DeclaredClass], FieldDefinition]] = []

    for parent_class in get_all_parent_classes(model):
        if get_origin(parent_class) is Fulfils:
            fulfiled_classes = get_args(parent_class)
            for fulfiled_class in fulfiled_classes:
                if (
                    issubclass(fulfiled_class, _DeclaredClass)
                    and field_name in fulfiled_class.model_fields
                ):
                    parents_with_field.append(
                        (fulfiled_class, fulfiled_class._meta.fields[field_name])
                    )
        elif field_name in parent_class.model_fields:
            parents_with_field.append(
                (parent_class, parent_class._meta.fields[field_name])
            )

        else:
            continue

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


def normalise_and_get_subclassed_fields(
    model: type[_DeclaredClass],
) -> dict[str, FieldSubclassing]:
    """Normalize relation subclass declarations from model fields.

    For each field with relation config subclass declarations, validate the
    target field exists and generate a set of `FieldSubclassing` objects.
    """

    subclassed_fields = {}
    for field_name, field_info in model.model_fields.items():
        if relation_config := get_relation_config(field_info):
            field_subclassings: set[FieldSubclassing] = set()
            for field_subclassing in relation_config.subclasses_parent_fields:
                if isinstance(field_subclassing, FieldSubclassing):
                    if (
                        field_subclassing.field_name
                        not in field_subclassing.field_on_model.model_fields
                    ):
                        raise PanglossModelError(
                            f"{model.__name__}.{field_name} is trying to subclass a field ('{field_subclassing}') that does not exist on a parent class"
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
                        get_field_origin_model_and_definition(model, field_subclassing)
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

            relation_config.subclasses_parent_fields = list(field_subclassings)
    return subclassed_fields


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


def get_fulfiled_types(model: type[_DeclaredClass]) -> set[type[_DeclaredClass]]:
    """Return all types fulfilled by `model` via `Fulfils` parent classes."""
    fulfilled_types = set()
    fulfilments = [f for f in get_all_parent_classes(model) if issubclass(f, Fulfils)]

    for f in fulfilments:
        fulfilled_types.update(f._fulfiling_types)

    return fulfilled_types


def get_fields_on_model(model: type[_DeclaredClass]):
    """Yields an iterable of field name, field info and set of FieldFulfilment objects for a model, removing subclassed
    fields"""

    subclassed_fields = normalise_and_get_subclassed_fields(model)

    fulfiled_types = get_fulfiled_types(model)

    for ft in fulfiled_types:
        subclassed_fields.update(normalise_and_get_subclassed_fields(ft))

    fulfilled_field_names = []
    for ft in fulfiled_types:
        fulfilled_field_names.extend(ft.model_fields.keys())

    for field_name in fulfilled_field_names:
        if field_name in ("type", "fulfiling_types"):
            continue

        if field_name in subclassed_fields:
            continue

        yield (
            field_name,
            [
                ft.model_fields[field_name]
                for ft in fulfiled_types
                if field_name in ft.model_fields
            ][0],
            set(
                FieldFulfilment(field_name=field_name, fulfils_class=ft)
                for ft in fulfiled_types
                if field_name in ft.model_fields
            ),
        )

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
                    for fsc in config.subclasses_parent_fields
                    if isinstance(fsc, FieldSubclassing)
                    and fsc.field_on_model in fulfiled_types
                ),
            )
        else:
            yield field_name, field_info, set()


def check_subclass_type(field_definition: RelationFieldDefinition):
    """Validate that subclassed relation field types are compatible.

    For each declared subclassing (from parent field relations), ensure the
    concrete type options of the child field are a subset of the parent.
    Raises a `PanglossModelError` if the type narrowing contract is violated.
    """
    for spf in field_definition.subclasses_parent_fields:
        assert isinstance(spf, FieldSubclassing)
        assert isinstance(spf.subclassed_field_definition, RelationFieldDefinition)

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
                f"{field_definition.field_on_model.__name__}.{field_definition.field_name} subclasses {spf.field_on_model}.{spf.field_name} "
                "but is not of the same type or narrowing of type"
            )


def extract_field_description(field_info: FieldInfo) -> str | None:
    description_objects_or_strings_from_metadata = [
        str(md) for md in field_info.metadata if isinstance(md, str)
    ]
    if (
        relation_config := extract_relation_config(field_info)
    ) and relation_config.description:
        description = relation_config.description

    elif description_objects_or_strings_from_metadata:
        description = description_objects_or_strings_from_metadata[0]

    else:
        description = None

    return description


def initialise_field_definitions(model: type[_DeclaredClass]):
    """Initialise and register field definitions for the model.

    Iterates through all fields (including inherited fulfilments) and creates the
    appropriate field definitions, including literal/list/embedded/relation
    field types, while applying subclassing rules and relation config.
    """

    if issubclass(model, _DeclaredClass):
        for field_name in model.model_fields.keys():
            if field_name == "meta":
                raise PanglossModelError("'meta' is a Pangloss reserved name"
                f"and cannot be used as a model field in ({model.__name__})")

    if issubclass(model, EdgeModel):
        for field_name, field_info in model.model_fields.items():
            if is_relatable(field_info.annotation) or is_list_relatable(
                field_info.annotation
            ):
                raise PanglossModelError(
                    f"EdgeModel {model.__name__} does not support relations ({model.__name__}.{field_name})"
                )
    if issubclass(model, AnnotatedValue):
        for field_name, field_info in model.model_fields.items():
            if is_relatable(field_info.annotation) or is_list_relatable(
                field_info.annotation
            ):
                raise PanglossModelError(
                    f"AnnotatedValue {model.__name__} does not support relations ({model.__name__}.{field_name})"
                )

    for field_name, field_info, field_fulfilment in get_fields_on_model(model):
        is_db_field = any(
            isclass(md) and issubclass(md, DBField) or isinstance(md, DBField)
            for md in field_info.metadata
        )

        if issubclass(model, AnnotatedValue) and field_name == "value":
            model._meta.field_definitions.add_field(
                name=field_name,
                field_definition=LiteralTypeVarFieldDefinition(
                    field_name=field_name,
                    field_on_model=model,
                    annotated_type=cast(TypeVar, field_info.annotation),
                    type_var_name=str(field_info.annotation),
                    db_field=is_db_field,
                    description=extract_field_description(field_info),
                ),
            )

        if (
            issubclass(model, SemanticSpace)
            and model is not SemanticSpace
            and model.__pydantic_generic_metadata__["origin"] is None
        ):
            field_definition = build_relatable_field_definition(
                field_name, field_info, model, is_db_field=is_db_field
            )

            model._meta.field_definitions.add_field(
                name=field_name,
                field_definition=field_definition,
            )

        if (
            issubclass(model, Conjunction)
            and model is not Conjunction
            and model.__pydantic_generic_metadata__["origin"] is None
        ):
            field_definition = build_relatable_field_definition(
                field_name, field_info, model, is_db_field=is_db_field
            )
            model._meta.field_definitions.add_field(
                name=field_name,
                field_definition=field_definition,
            )

        if issubclass(model, (ReifiedRelation, ReifiedRelationDocument)):
            if get_origin(field_info.annotation) and isinstance(
                get_args(field_info.annotation)[0], TypeVar
            ):
                field_definition = build_relatable_field_definition(
                    field_name, field_info, model, is_db_field=is_db_field
                )
                model._meta.field_definitions.add_field(
                    name=field_name,
                    field_definition=field_definition,
                )

        if is_embedded(field_info.annotation) or is_union_of_embedded(
            field_info.annotation
        ):
            field_definition = build_embedded_field_definition(
                field_name, field_info, model, is_db_field=is_db_field
            )
            model._meta.field_definitions.add_field(
                name=field_name,
                field_definition=field_definition,
            )
        elif isclass(field_info.annotation) and issubclass(
            field_info.annotation, AnnotatedValue
        ):
            field_definition = AnnotatedValueFieldDefinition(
                field_on_model=model,
                field_name=field_name,
                annotated_type=field_info.annotation,
                db_field=is_db_field,
                description=extract_field_description(field_info),
            )

            model._meta.field_definitions.add_field(
                name=field_name,
                field_definition=field_definition,
            )

        elif is_relatable(field_info.annotation) or is_list_relatable(
            field_info.annotation
        ):
            field_definition = build_relatable_field_definition(
                field_name, field_info, model, is_db_field=is_db_field
            )
            if field_fulfilment:
                field_definition.field_required_to_fulfil.update(field_fulfilment)

            check_subclass_type(field_definition)

            model._meta.field_definitions.add_field(
                name=field_name,
                field_definition=field_definition,
            )

        elif is_list_of_literal(field_info.annotation):
            field_definition = build_list_field_definition(
                field_name, field_info, model, is_db_field=is_db_field
            )
            model._meta.field_definitions.add_field(
                name=field_name,
                field_definition=field_definition,
            )

        elif is_literal(field_info.annotation):
            field_definition = LiteralFieldDefinition(
                field_on_model=model,
                field_name=field_name,
                annotated_type=field_info.annotation,
                validators=[
                    md for md in field_info.metadata if isinstance(md, BaseMetadata)
                ],
                db_field=is_db_field,
                description=extract_field_description(field_info),
            )

            model._meta.field_definitions.add_field(
                name=field_name,
                field_definition=field_definition,
            )
