from typing import Annotated, ClassVar, Literal

from pydantic import ConfigDict, Field
from pydantic_meta_kit import BaseMeta, InheritValue, MetaRules, WithMeta

from pangloss_models.field_definitions import (
    FieldDefinition,
    ModelFieldDict,
    ModelFields,
)
from pangloss_models.model_bases.base_models import (
    DeclaredClassMeta,
    _CreateBase,
    _CreateDBBase,
    _DeclaredClass,
    _UpdateBase,
    _UpdateDBBase,
    _ViewBase,
)


class EmbeddedMeta(BaseMeta, DeclaredClassMeta):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    _owner_class: type[Embedded] | InheritValue = InheritValue.AS_DEFAULT
    abstract: Annotated[bool, MetaRules.DO_NOT_INHERIT] = False
    require_label: Literal[False] = False
    field_definitions: ModelFields = Field(default_factory=ModelFields)

    @property
    def fields(self) -> ModelFieldDict[str, FieldDefinition]:
        return self.field_definitions.fields


class _EmbeddedCreateBase(_CreateBase):
    pass


class _EmbeddedCreateDBBase(_CreateDBBase):
    pass


class _EmbeddedUpdateBase(_UpdateBase):
    pass


class _EmbeddedUpdateDBBAse(_UpdateDBBase):
    pass


class _EmbeddedViewBase(_ViewBase):
    pass


class Embedded(_DeclaredClass, WithMeta[EmbeddedMeta]):
    __metatype__ = "Embedded"
    _meta: ClassVar[EmbeddedMeta] = EmbeddedMeta()  # pyright: ignore[reportIncompatibleVariableOverride]

    Create: ClassVar[type[_EmbeddedCreateBase]]
    CreateDB: ClassVar[type[_EmbeddedCreateDBBase]]
    Update: ClassVar[type[_EmbeddedUpdateBase]]
    UpdateDB: ClassVar[type[_EmbeddedUpdateDBBAse]]

    View: ClassVar[type[_EmbeddedViewBase]]

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs) -> None:

        cls._initialised = False

        # Make sure _meta class is new and not inherited
        cls._meta = cls.__dict__.get("_meta", EmbeddedMeta())  # pyright: ignore[reportIncompatibleVariableOverride]

        # Set owner class on cls._meta
        cls._meta._owner_class = cls

        cls._register()
