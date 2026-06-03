import typing
from datetime import date, datetime
from functools import cache
from inspect import isclass
from types import NoneType, UnionType
from typing import (
    Annotated,
    Any,
    Generic,
    Iterable,
    TypeIs,
    Union,
    cast,
    get_args,
    get_origin,
    overload,
)

import annotated_types
from annotated_types import BaseMetadata
from pydantic import BaseModel
from pydantic._internal._generics import PydanticGenericMetadata
from pydantic.fields import FieldInfo
from pydantic_meta_kit import WithMeta

from pangloss_models.exceptions import PanglossModelError
from pangloss_models.field_definitions import FieldBinding
from pangloss_models.model_bases.base_models import _BaseObject, _DeclaredClass
from pangloss_models.model_bases.configs import RelationConfig
from pangloss_models.model_bases.conjunction import Conjunction
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.edge_model import EdgeModel
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.helpers import ViaEdge
from pangloss_models.model_bases.reified_relation import (
    ReifiedRelation,
    ReifiedRelationDocument,
)
from pangloss_models.model_bases.semantic_space import SemanticSpace
from pangloss_models.model_bases.trait import (
    NonHeritableTrait,
    Trait,
    _Trait,
)

type ConcreteUnionType[T] = type[type[T] | type[T]]


@overload
def get_concrete_types[T](
    model: ConcreteUnionType[T], include_abstract: bool = False
) -> set[type[T]]: ...


@overload
def get_concrete_types(
    model: type[Entity],
    include_abstract: bool = False,
) -> set[type[Entity]]: ...


@overload
def get_concrete_types(
    model: type[Document],
    include_abstract: bool = False,
) -> set[type[Document]]: ...


@overload
def get_concrete_types(
    model: type[Embedded],
    include_abstract: bool = False,
) -> set[type[Embedded]]: ...


@overload
def get_concrete_types(
    model: type[SemanticSpace], include_abstract: bool = False
) -> set[type[SemanticSpace]]: ...


@overload
def get_concrete_types(
    model: type[Conjunction], include_abstract: bool = False
) -> set[type[Conjunction]]: ...


@overload
def get_concrete_types(
    model: type[Trait | NonHeritableTrait],
    include_abstract: bool = False,
) -> set[type[Document]] | set[type[Entity]]: ...


def get_concrete_types(
    model: Any,
    include_abstract: bool = False,
):
    """Return concrete (non-abstract) subclasses for a model.

    This is a convenience wrapper around :func:`generic_get_subclasses` that
    includes the model itself when it is concrete (or when
    ``include_abstract=True``).

    Args:
        model: A Pangloss model class (Document, Entity or Trait).
        include_abstract: If True, include abstract base classes in the result.

    Returns:
        A set of concrete subclasses (and possibly the model itself).
    """

    concrete_types = []
    if isinstance(model, UnionType):
        for type_in_union in get_args(model):
            concrete_types.extend(
                get_concrete_types(type_in_union, include_abstract=include_abstract)
            )

    if isclass(model) and issubclass(
        model, (Document, Entity, Embedded, SemanticSpace, Conjunction)
    ):
        if not model._meta.abstract or include_abstract:
            concrete_types.append(model)
        concrete_types.extend(
            generic_get_subclasses(model, include_abstract=include_abstract)
        )
    elif isclass(model) and issubclass(model, (Trait, NonHeritableTrait)):
        for direct_trait_instantiations in get_direct_instantiations_of_trait(
            model, follow_trait_subclasses=True
        ):
            if not direct_trait_instantiations._meta.abstract or include_abstract:
                concrete_types.append(direct_trait_instantiations)
            if not issubclass(model, NonHeritableTrait):
                concrete_types.extend(
                    generic_get_subclasses(
                        direct_trait_instantiations, include_abstract=include_abstract
                    )
                )
    return set(concrete_types)


def generic_get_subclasses[
    T: Document | Entity | Embedded | SemanticSpace | Conjunction
](model: type[T], include_abstract: bool = False) -> set[type[T]]:
    """Recursively find subclasses of a Document or Entity model.

    Traverses the subclass tree and returns all reachable subclasses, optionally
    filtering out abstract models.

    Args:
        model: The base class to inspect.
        include_abstract: If False, exclude models whose ``_meta.abstract`` is True.

    Returns:
        A set of subclass types.
    """
    subclasses = []
    for subclass in model.__subclasses__():
        # Skip if it is a parameterised generic
        if subclass.__pydantic_generic_metadata__["origin"] is not None:
            continue

        if not subclass._meta.abstract or include_abstract:
            subclasses += [
                subclass,
                *generic_get_subclasses(subclass, include_abstract=include_abstract),
            ]
        else:
            subclasses += generic_get_subclasses(
                subclass, include_abstract=include_abstract
            )
    return set(subclasses)


def model_is_trait(
    cls: type[_DeclaredClass] | type[Trait] | type[NonHeritableTrait],
):
    """Determines whether a model is a Trait, or subclass of a Trait,
    rather than a _DeclaredClass type to which a Trait has been applied"""

    return (
        isclass(cls)
        and issubclass(cls, (Trait, NonHeritableTrait))
        and is_subclass_of_heritable_trait(cls)
    )


def is_subclass_of_heritable_trait(
    cls: type[Trait] | type[NonHeritableTrait],
) -> bool:
    """Determine whether a class is a subclass of a Trait,
    not the application of a trait to a real Document or Entity class.

    This should work by not having BaseNode in its class hierarchy
    """
    for parent in cls.mro()[1:]:
        if issubclass(parent, (Document, Entity)):
            return False
    else:
        return True


def get_trait_subclasses(
    trait: type[Trait] | type[NonHeritableTrait],
) -> set[type[Trait] | type[NonHeritableTrait]]:
    """Get subclasses of a Trait that are Traits, not instantiations
    of a Trait"""

    subclasses = [trait]
    for subclass in trait.__subclasses__():
        if model_is_trait(subclass):
            subclasses.extend(get_trait_subclasses(subclass))
    return set(subclasses)


def get_direct_instantiations_of_trait(
    trait: type[Trait] | type[NonHeritableTrait],
    follow_trait_subclasses: bool = False,
) -> set[type[Document] | type[Entity]]:
    """Given a Trait class, find the models to which it is *directly* applied,
    i.e. omitting children"""

    if follow_trait_subclasses:
        trait_subclasses = [
            trait_subclass for trait_subclass in get_trait_subclasses(trait)
        ]
        instantiations_of_trait = []
        for trait_subclass in trait_subclasses:
            instantiations_of_trait.extend(
                subclass
                for subclass in trait_subclass.__subclasses__()
                if issubclass(subclass, (Document, Entity))
            )
        return set(instantiations_of_trait)

    return set(
        [
            subclass
            for subclass in trait.__subclasses__()
            if issubclass(subclass, (Document, Entity))
        ]
    )


def is_literal(
    annotation: type[Any] | None | UnionType,
) -> TypeIs[type[str | int | float | date | datetime]]:
    """Checks whether an annotation is of a literal type"""
    LITERAL_TYPES = {str, int, float, date, datetime}
    if annotation_is_optional(annotation):
        annotation = [t for t in get_args(annotation) if t is not NoneType][0]

    return annotation in LITERAL_TYPES


def is_list_of_literal(
    annotation: type[Any] | None,
) -> TypeIs[type[list[str | int | float | date | datetime]]]:

    # list[X]
    if get_origin(annotation) is not list:
        return False
    # (X,)
    args = get_args(annotation)
    if not args:
        return False

    inner_type = args[0]

    if is_literal(inner_type):
        return True

    if get_origin(inner_type) is Annotated:
        inner_type_args = get_args(inner_type)
        if not inner_type_args:
            return False
        if is_literal(inner_type_args[0]):
            return True
    return False


def is_embedded(annotation: type[Any] | UnionType | None) -> TypeIs[type[Embedded]]:
    if isclass(annotation) and issubclass(annotation, Embedded):
        return True
    return False


def is_union_of_embedded(
    annotation: type[Any] | None | UnionType,
) -> TypeIs[type[Embedded | Embedded]]:
    if isinstance(annotation, UnionType):
        if all(is_embedded(arg) for arg in get_args(annotation)):
            return True
    return False


def is_union_of_relatable(
    annotation: type[Any] | None | UnionType,
) -> TypeIs[UnionType]:
    if isinstance(annotation, UnionType):
        return all(is_relatable(arg) for arg in get_args(annotation))
    return False


def is_via_edge(
    annotation: type[Any] | None | UnionType,
) -> TypeIs[type[ViaEdge[Document | Entity, EdgeModel]]]:
    generic_metadata: PydanticGenericMetadata | None = getattr(
        annotation, "__pydantic_generic_metadata__", None
    )
    if generic_metadata and generic_metadata["origin"] is ViaEdge:
        if is_relatable(generic_metadata["args"][0]):
            return True
    return False


def get_model_and_edge_type(
    annotation: type[ViaEdge[type[Document | Entity], EdgeModel]],
) -> tuple[type[Document | Entity], type[EdgeModel]]:
    generic_metadata: PydanticGenericMetadata | None = getattr(
        annotation, "__pydantic_generic_metadata__", None
    )
    if generic_metadata and generic_metadata["origin"] is ViaEdge:
        if is_relatable(generic_metadata["args"][0]) and issubclass(
            generic_metadata["args"][1], EdgeModel
        ):
            return cast(
                tuple[type[Document | Entity], type[EdgeModel]],
                generic_metadata["args"],
            )

    raise PanglossModelError("ViaEdge model incorrectly used")


def is_relatable(
    annotation: type[Any] | None | type[Any | Any] | UnionType,
) -> TypeIs[type[_DeclaredClass] | type[Union[_DeclaredClass, _DeclaredClass]]]:
    if is_union_of_relatable(annotation):
        return True

    if is_via_edge(annotation):
        return True

    if isclass(annotation) and issubclass(annotation, (_DeclaredClass)):
        return True
    return False


def is_single_relatable(annotation: type[Any]) -> TypeIs[type[_DeclaredClass]]:
    if isclass(annotation) and issubclass(annotation, _DeclaredClass):
        return True
    return False


def is_list_relatable(annotation: type[Any] | None) -> bool:

    # list[X]
    if get_origin(annotation) is not list:
        return False
    # (X,)
    args = get_args(annotation)
    if not args:
        return False

    inner_type = args[0]

    if is_relatable(inner_type):
        return True

    if get_origin(inner_type) is Annotated:
        inner_type_args = get_args(inner_type)
        if not inner_type_args:
            return False
        if is_relatable(inner_type_args[0]):
            return True
    return False


def is_parameterized_generic(tp):
    return get_origin(tp) is not None and len(get_args(tp)) > 0


def flatten[T](xss: Iterable[Iterable[T]]) -> list[T]:
    return [x for xs in xss for x in xs]


def extract_relation_config(field_info: FieldInfo) -> RelationConfig | None:
    if not field_info.metadata:
        return None
    for metadata_object in field_info.metadata:
        if isinstance(metadata_object, RelationConfig):
            return metadata_object


def extract_validators(field_info: FieldInfo):

    if not field_info.metadata:
        return []

    validators: list[BaseMetadata] = []
    for metadata_object in field_info.metadata:
        if isinstance(metadata_object, BaseMetadata):
            validators.append(metadata_object)
    if relation_config := extract_relation_config(field_info):
        validators.extend(relation_config.validators)
    return validators


@cache
def get_relation_config(field_info: FieldInfo) -> RelationConfig | None:
    if field_info.metadata and (
        rcs := [md for md in field_info.metadata if isinstance(md, RelationConfig)]
    ):
        relation_config = cast(RelationConfig, rcs[0])
        return relation_config
    return None


@cache
def get_top_level_classes():
    usable_subclasses: list[type[Any]] = _DeclaredClass.__subclasses__()
    usable_subclasses.remove(_Trait)
    usable_subclasses.extend(
        [
            Trait,
            NonHeritableTrait,
            BaseModel,
            _Trait,
            _DeclaredClass,
            _BaseObject,
            WithMeta,
            Generic,  # pyright: ignore[reportArgumentType]
            object,
        ]
    )
    return set(usable_subclasses)


@overload
def get_parent_class(model: type[Document]) -> type[Document] | None: ...


@overload
def get_parent_class(model: type[Entity]) -> type[Entity] | None: ...


@overload
def get_parent_class(model: type[Embedded]) -> type[Embedded] | None: ...


@overload
def get_parent_class(model: type[ReifiedRelation]) -> type[ReifiedRelation] | None: ...


@overload
def get_parent_class(
    model: type[ReifiedRelationDocument],
) -> type[ReifiedRelationDocument] | None: ...


@overload
def get_parent_class(model: type[SemanticSpace]) -> type[SemanticSpace] | None: ...


@overload
def get_parent_class(model: type[Conjunction]) -> type[Conjunction] | None: ...


@overload
def get_parent_class(
    model: type[Trait],
) -> type[Trait] | None: ...


@overload
def get_parent_class(
    model: type[NonHeritableTrait],
) -> type[NonHeritableTrait] | None: ...


@overload
def get_parent_class(
    model: type[_DeclaredClass],
) -> type[_DeclaredClass] | None: ...


def get_parent_class(model) -> Any:
    for parent_class in model.mro():
        if parent_class is model:
            continue
        elif parent_class in get_top_level_classes():
            return None
        else:
            return parent_class
    return None


@overload
def get_all_parent_classes(
    model: type[Document],
) -> list[type[Document] | type[Trait] | type[NonHeritableTrait]]: ...


@overload
def get_all_parent_classes(
    model: type[Entity],
) -> list[type[Entity] | type[Trait] | type[NonHeritableTrait]]: ...


@overload
def get_all_parent_classes(model: type[Embedded]) -> list[type[Embedded]]: ...


@overload
def get_all_parent_classes(
    model: type[ReifiedRelation],
) -> list[type[ReifiedRelation]]: ...


@overload
def get_all_parent_classes(
    model: type[ReifiedRelationDocument],
) -> list[type[ReifiedRelationDocument] | type[Trait] | type[NonHeritableTrait]]: ...


@overload
def get_all_parent_classes(
    model: type[SemanticSpace],
) -> list[type[SemanticSpace]]: ...


@overload
def get_all_parent_classes(
    model: type[Conjunction],
) -> list[type[Conjunction]]: ...


@overload
def get_all_parent_classes(
    model: type[Trait],
) -> list[type[Trait]]: ...


@overload
def get_all_parent_classes(
    model: type[NonHeritableTrait],
) -> list[type[NonHeritableTrait]]: ...


@overload
def get_all_parent_classes[T](
    model: T,
) -> list[T]: ...


def is_subclass_of_with_meta(cls):
    if pgm := getattr(cls, "__pydantic_generic_metadata__", None):
        if pgm["origin"] is WithMeta:
            return True
    return False


def class_is_direct_descendent_of_non_heritable_trait(
    model, trait: type[NonHeritableTrait]
) -> bool:
    if not issubclass(trait, NonHeritableTrait):
        return True

    if model in get_direct_instantiations_of_trait(trait):
        return True

    return False


def get_all_parent_classes(model):
    parent_classes = []

    for parent_class in model.mro():
        if parent_class is model:
            continue
        else:
            parent_classes.append(parent_class)

    filtered_parent_classes = []

    for pc in parent_classes:
        if pc in get_top_level_classes():
            continue

        if is_subclass_of_with_meta(pc):
            continue

        filtered_parent_classes.append(pc)

    return filtered_parent_classes


def annotation_is_optional(ann: Any) -> TypeIs[UnionType]:

    if get_origin(ann) is typing.Union:
        return NoneType in get_args(ann)

    return False


def map_validators_to_kwargs(validators: list[BaseMetadata]):
    validator_dict = {}
    for validator in validators:
        match validator:
            case annotated_types.Gt(v):
                validator_dict["gt"] = v
            case annotated_types.Ge(v):
                validator_dict["ge"] = v
            case annotated_types.Lt(v):
                validator_dict["lt"] = v
            case annotated_types.Le(v):
                validator_dict["le"] = v
            case annotated_types.MultipleOf(v):
                validator_dict["multiple_of"] = v
            case annotated_types.MinLen(v):
                validator_dict["min_length"] = v
            case annotated_types.MaxLen(v):
                validator_dict["max_length"] = v
            case _:
                pass
    return validator_dict


def field_has_inherited_field_bindings(
    field_bindings: frozenset[FieldBinding],
    field_name: str,
    model: type[_DeclaredClass],
) -> bool:
    for field_binding in field_bindings:
        if (
            field_name in field_binding.child_fields
            and (
                not field_binding.allowed_type_names
                or model.__name__ in field_binding.allowed_type_names
            )
            and model.__name__ not in field_binding.excluded_type_names
        ):
            return True

    return False
