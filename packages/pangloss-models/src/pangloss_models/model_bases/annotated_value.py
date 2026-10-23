from typing import Annotated, ClassVar

from pydantic import Field
from pydantic_meta_kit import BaseMeta, InheritValue, MetaRules, WithMeta

from pangloss_models.field_definitions import (
    FieldDefinition,
    ModelFieldDict,
    ModelFields,
)
from pangloss_models.model_bases.base_models import _DeclaredClass


class AnnotatedValueMeta(BaseMeta):
    _owner_class: type[AnnotatedValue] | InheritValue = InheritValue.AS_DEFAULT

    field_definitions: Annotated[ModelFields, MetaRules.DO_NOT_INHERIT] = Field(
        default_factory=ModelFields
    )

    @property
    def fields(self) -> ModelFieldDict[str, FieldDefinition]:
        if self.field_definitions:
            return self.field_definitions.fields
        raise Exception(f"{self.__class__.__name__}.field_definition missing")


class AnnotatedValue[T](_DeclaredClass, WithMeta[AnnotatedValueMeta]):
    """Allows additional literal fields to be bound to a value"""

    __metatype__ = "AnnotatedValue"
    _meta: ClassVar[AnnotatedValueMeta] = AnnotatedValueMeta()

    value: T

