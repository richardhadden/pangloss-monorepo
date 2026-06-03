from typing import Annotated, ClassVar

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


class ConjunctionMeta(BaseMeta, DeclaredClassMeta):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    _owner_class: type[Conjunction] | InheritValue = InheritValue.AS_DEFAULT
    abstract: Annotated[bool, MetaRules.DO_NOT_INHERIT] = False
    require_label: bool | InheritValue = False
    field_definitions: ModelFields = Field(default_factory=ModelFields)

    @property
    def fields(self) -> ModelFieldDict[str, FieldDefinition]:
        return self.field_definitions.fields


class _ConjunctionCreateBase(_CreateBase):
    pass


class _ConjunctionCreateDBBase(_CreateDBBase):
    pass


class _ConjunctionUpdateBase(_UpdateBase):
    pass


class _ConjunctionUpdateDBBase(_UpdateDBBase):
    pass


class _ConjunctionViewBase(_ViewBase):
    pass


class Conjunction(_DeclaredClass, WithMeta[ConjunctionMeta]):
    __metatype__ = "Conjunction"
    _meta: ClassVar[ConjunctionMeta] = ConjunctionMeta()  # pyright: ignore[reportIncompatibleVariableOverride]

    Create: ClassVar[type[_ConjunctionCreateBase]]
    CreateDB: ClassVar[type[_ConjunctionCreateDBBase]]
    Update: ClassVar[type[_ConjunctionUpdateBase]]
    UpdateDB: ClassVar[type[_ConjunctionUpdateDBBase]]
    View: ClassVar[type[_ConjunctionViewBase]]

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs) -> None:

        cls._initialised = False

        # Make sure _meta class is new and not inherited
        cls._meta = cls.__dict__.get("_meta", ConjunctionMeta())  # pyright: ignore[reportIncompatibleVariableOverride]

        # Set owner class on cls._meta
        cls._meta._owner_class = cls

        cls._register()
