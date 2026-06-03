from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import TYPE_CHECKING, Any, Callable, Protocol, TypeVar, runtime_checkable

from annotated_types import BaseMetadata
from frozendict import frozendict
from pydantic.fields import FieldInfo

from pangloss_models.exceptions import PanglossInitialisationError

if TYPE_CHECKING:
    from pangloss_models.model_bases.annotated_value import AnnotatedValue
    from pangloss_models.model_bases.base_models import _DeclaredClass
    from pangloss_models.model_bases.base_types import BaseTypes
    from pangloss_models.model_bases.conjunction import Conjunction
    from pangloss_models.model_bases.document import Document
    from pangloss_models.model_bases.edge_model import EdgeModel
    from pangloss_models.model_bases.embedded import Embedded
    from pangloss_models.model_bases.entity import Entity
    from pangloss_models.model_bases.reified_relation import (
        ReifiedRelation,
        ReifiedRelationDocument,
    )
    from pangloss_models.model_bases.semantic_space import SemanticSpace


@dataclass(frozen=True, kw_only=True)
class FieldFulfilment:
    """For a given field, describes which parent fields of a class
    subclassed with `Fulfils[Class]` will fulfil"""

    field_name: str
    fulfils_class: type[_DeclaredClass]


@dataclass(frozen=True, kw_only=True)
class FieldDefinition:
    field_on_model: type[_DeclaredClass]
    field_name: str
    annotated_type: type[_DeclaredClass | BaseTypes | list] | TypeVar
    field_required_to_fulfil: set[FieldFulfilment] = dataclass_field(
        default_factory=set
    )
    db_field: bool = False
    description: str | None = None

    @property
    def model_field(self) -> FieldInfo:
        try:
            return self.field_on_model.model_fields[self.field_name]
        except KeyError:
            raise PanglossInitialisationError(
                f"FieldInfo object for field {self.field_name} on model {self.field_on_model.__name__} not found"
            )
        except Exception:
            raise PanglossInitialisationError("Model Config not accessible yet")


@dataclass(frozen=True, kw_only=True)
class LiteralFieldDefinition(FieldDefinition):
    annotated_type: type[BaseTypes]
    validators: list[BaseMetadata] = dataclass_field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class ListFieldDefinition(FieldDefinition):
    annotated_type: type[list[BaseTypes]]
    validators: list[BaseMetadata] = dataclass_field(default_factory=list)
    inner_type: type[BaseTypes]
    inner_type_validators: list[BaseMetadata] = dataclass_field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class AnnotatedValueFieldDefinition(FieldDefinition):
    annotated_type: type[AnnotatedValue]


type TRelationFieldDefinitionAnnotation = (
    type[_DeclaredClass | BaseTypes | list]
    | type[list[type[_DeclaredClass | BaseTypes | list]]]
)


@dataclass(frozen=True, kw_only=True)
class LiteralTypeVarFieldDefinition(FieldDefinition):
    annotated_type: TypeVar
    type_var_name: str


@dataclass(frozen=True, kw_only=True)
class EmbeddedFieldDefinition(FieldDefinition):
    annotated_type: type[Embedded] | type[Embedded | Embedded]
    type_options: set[EmbeddedOption]


@dataclass(frozen=True, kw_only=True)
class EmbeddedOption:
    annotated_type: type[Embedded]


@dataclass(frozen=True)
class FieldSubclassing:
    field_name: str

    field_on_model: type[_DeclaredClass]
    disambiguator: str | None = None
    subclassed_field_definition: FieldDefinition | None = dataclass_field(
        default=None, init=False
    )

    def __post_init__(self):
        """This class can be initialised by the user in defintions; however,
        it is always automatically recreated by the initialisation process
        in an updated and consistent form with all fields complete, including
        `subclassed_field_definition`, which is set here.

        However, when created by the user, `self.field_on_model` may not
        be initialised at this point, throwing a key error. We are safe
        to ignore this.
        """
        try:
            object.__setattr__(
                self,
                "subclassed_field_definition",
                self.field_on_model._meta.fields[self.field_name],
            )
        except KeyError:
            pass

    def __hash__(self):
        return (
            hash(self.field_name) + hash(self.disambiguator) + hash(self.field_on_model)
        )


@dataclass(frozen=True, kw_only=True)
class FieldBinding:
    bound_field: str
    child_fields: list[str]
    allowed_type_names: list[str] = dataclass_field(default_factory=list)
    excluded_type_names: list[str] = dataclass_field(default_factory=list)
    converter: Callable[[Any], Any] | None = None

    def __hash__(self):
        return hash(
            self.bound_field
            + str(self.child_fields)
            + str(self.allowed_type_names)
            + str(self.excluded_type_names)
            + repr(self.converter)
        )


@dataclass(frozen=True, kw_only=True)
class RelationFieldDefinition(FieldDefinition):
    annotated_type: TRelationFieldDefinitionAnnotation  # pyright: ignore[reportIncompatibleVariableOverride]
    type_options: set[RelationOption] = dataclass_field(default_factory=set)
    reverse_name: str
    subclasses_parent_fields: set[str | FieldSubclassing]
    wrapper: type[list | tuple] | None = None
    validators: list[BaseMetadata] = dataclass_field(default_factory=list)
    bind_to_child_field: list[FieldBinding] = dataclass_field(default_factory=list)

    @staticmethod
    def type_option_contains_typevar(
        type_options: set[RelationOption] | frozenset[RelationOption],
    ) -> bool:
        for type_option in type_options:
            if isinstance(type_option, RelationToTypeVar):
                return True
            if isinstance(type_option, RelationToReifiedRelation):
                for param_type_option in type_option.parameter_type_options.values():
                    if isinstance(param_type_option.type_var, TypeVar):
                        return True

        return False

    @property
    def contains_typevar(self) -> bool:
        return self.type_option_contains_typevar(self.type_options)


@dataclass(frozen=True, kw_only=True)
class RelationOption:
    annotated_type: type
    edge_model: type[EdgeModel] | None = None


@dataclass(frozen=True, kw_only=True)
class RelationToDocument(RelationOption):
    annotated_type: type[Document]


@dataclass(frozen=True, kw_only=True)
class RelationToEntity(RelationOption):
    annotated_type: type[Entity]


@dataclass(frozen=True, kw_only=True)
class RelationToSemanticSpace(RelationOption):
    annotated_type: TRelationFieldDefinitionAnnotation
    base_type: type[SemanticSpace]
    parameter_type_options: frozendict[str, ParameterTypeOptions]


@runtime_checkable
class RelationToGeneric(Protocol):
    annotated_type: TRelationFieldDefinitionAnnotation
    base_type: type[Conjunction]
    parameter_type_options: frozendict[str, ParameterTypeOptions]


@dataclass(frozen=True, kw_only=True)
class RelationToConjunction(RelationOption):
    annotated_type: TRelationFieldDefinitionAnnotation
    base_type: type[Conjunction]
    parameter_type_options: frozendict[str, ParameterTypeOptions]


@dataclass(frozen=True)
class ParameterTypeOptions[T]:
    annotated_type: TRelationFieldDefinitionAnnotation
    type_var: TypeVar
    type_var_name: str
    type_options: frozenset[RelationOption] = dataclass_field(default_factory=frozenset)


@dataclass(frozen=True, kw_only=True)
class RelationToReifiedRelation(RelationOption):
    annotated_type: TRelationFieldDefinitionAnnotation
    base_type: type[ReifiedRelation]
    parameter_type_options: frozendict[str, ParameterTypeOptions]


@dataclass(frozen=True, kw_only=True)
class RelationToReifiedRelationDocument(RelationOption):
    annotated_type: TRelationFieldDefinitionAnnotation
    base_type: type[ReifiedRelationDocument]
    parameter_type_options: frozendict[str, ParameterTypeOptions]


@dataclass(frozen=True, kw_only=True)
class RelationToTypeVar(RelationOption):
    type_var_name: str
    annotated_type: TypeVar  # pyright: ignore[reportIncompatibleVariableOverride]


@dataclass(frozen=True, kw_only=True)
class IncomingRelationDefinition:
    source: type[_DeclaredClass]
    field_definition: RelationFieldDefinition
    via_reified: bool


class ModelFieldDict[K, V](dict[K, V]):
    @property
    def typevar_fields(self) -> dict[K, RelationFieldDefinition]:
        typevar_fields = {}
        for field_name, field in self.items():
            typevar_fields[field_name] = field
        return typevar_fields

    @property
    def literal_fields(self) -> dict[K, LiteralFieldDefinition | ListFieldDefinition]:
        return {
            field_name: field_definition
            for field_name, field_definition in self.items()
            if isinstance(
                field_definition, (LiteralFieldDefinition, ListFieldDefinition)
            )
        }

    @property
    def relation_fields(self) -> dict[K, RelationFieldDefinition]:
        return {
            field_name: field_definition
            for field_name, field_definition in self.items()
            if isinstance(field_definition, RelationFieldDefinition)
        }

    @property
    def embedded_fields(self) -> dict[K, EmbeddedFieldDefinition]:
        return {
            field_name: field_definition
            for field_name, field_definition in self.items()
            if isinstance(field_definition, EmbeddedFieldDefinition)
        }

    @property
    def annotated_value_fields(self) -> dict[K, AnnotatedValueFieldDefinition]:
        return {
            field_name: field_definition
            for field_name, field_definition in self.items()
            if isinstance(field_definition, AnnotatedValueFieldDefinition)
        }

    @property
    def bind_to_child_field_bindings(self) -> dict[K, list[FieldBinding]]:
        return {
            field_name: field_definition.bind_to_child_field
            for field_name, field_definition in self.relation_fields.items()
            if field_definition.bind_to_child_field
        }


@dataclass
class ModelFields:
    fields: ModelFieldDict[str, FieldDefinition] = dataclass_field(
        default_factory=ModelFieldDict
    )

    def add_field(self, name: str, field_definition: FieldDefinition):
        self.fields[name] = field_definition

    incoming_fields: dict[str, list] = dataclass_field(
        default_factory=lambda: defaultdict(list)
    )
