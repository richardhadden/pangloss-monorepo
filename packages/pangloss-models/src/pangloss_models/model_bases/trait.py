from typing import Any, ClassVar

from pydantic import ConfigDict, Field

from pangloss_models.field_definitions import (
    FieldDefinition,
    ModelFieldDict,
    ModelFields,
)
from pangloss_models.meta_kit import BaseMeta, InheritValue
from pangloss_models.model_bases.base_models import (
    DeclaredClassMeta,
    _DeclaredClass,
)
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity


class TraitMeta[T: Trait | NonHeritableTrait](BaseMeta, DeclaredClassMeta):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    field_definitions: ModelFields = Field(default_factory=ModelFields)
    _owner_class: type[T] | InheritValue = InheritValue.AS_DEFAULT

    @property
    def fields(self) -> ModelFieldDict[str, FieldDefinition]:
        return self.field_definitions.fields


class _Trait(_DeclaredClass):
    _kind_base: ClassVar[bool] = True


class Trait[T: Document | Entity](_Trait):
    _kind_base: ClassVar[bool] = True
    # Fields of the trait added to the `ReferenceView` of every class that has it (a database field may be one: a
    # reference view is only read). Those of a trait it extends are added too
    reference_view_fields: ClassVar[tuple[str, ...]] = ()
    Meta: ClassVar[Any] = TraitMeta
    # (a class variable, as `Entity._meta` is: so that `class Person(Entity, Agent)` with a `_meta` of its own is not,
    # to a type checker, a class variable over an instance variable)
    _meta: ClassVar[Any]


class NonHeritableTrait(_Trait):
    _kind_base: ClassVar[bool] = True
    Meta: ClassVar[Any] = TraitMeta
    _meta: ClassVar[Any]
