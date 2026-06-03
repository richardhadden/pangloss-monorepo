from typing import ClassVar

from pydantic import Field
from pydantic_meta_kit import BaseMeta, InheritValue, WithMeta

from pangloss_models.field_definitions import (
    FieldDefinition,
    ModelFieldDict,
    ModelFields,
)
from pangloss_models.model_bases.base_models import _DeclaredClass


class AnnotatedValueMeta(BaseMeta):
    _owner_class: type[AnnotatedValue] | InheritValue = InheritValue.AS_DEFAULT

    field_definitions: ModelFields = Field(default_factory=ModelFields)

    @property
    def fields(self) -> ModelFieldDict[str, FieldDefinition]:
        if self.field_definitions:
            return self.field_definitions.fields
        raise Exception(f"{self.__class__.__name__}.field_definition missing")


class AnnotatedValue[T](_DeclaredClass, WithMeta[AnnotatedValueMeta]):
    """Allows additional literal fields to be bound to a value"""

    __metatype__ = "AnnotatedValue"
    _meta: ClassVar[AnnotatedValueMeta] = AnnotatedValueMeta()  # pyright: ignore[reportIncompatibleVariableOverride]

    value: T

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs) -> None:

        cls._meta = cls.__dict__.get("_meta", AnnotatedValueMeta(_owner_class=cls))  # pyright: ignore[reportIncompatibleVariableOverride]

        cls._meta._owner_class = cls

        cls._register()
