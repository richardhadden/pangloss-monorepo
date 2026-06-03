from typing import ClassVar, cast

from pydantic import ConfigDict, Field
from pydantic_meta_kit import BaseMeta, InheritValue

from pangloss_models.field_definitions import (
    ListFieldDefinition,
    LiteralFieldDefinition,
    ModelFieldDict,
    ModelFields,
)
from pangloss_models.model_bases.base_models import (
    DeclaredClassMeta,
    _DeclaredClass,
)


class EdgeModelMeta(BaseMeta, DeclaredClassMeta):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    _owner_class: type[EdgeModel] | InheritValue = InheritValue.AS_DEFAULT

    field_definitions: ModelFields = Field(default_factory=ModelFields)

    @property
    def fields(  # type: ignore
        self,
    ) -> ModelFieldDict[str, LiteralFieldDefinition | ListFieldDefinition]:  # pyright: ignore[reportIncompatibleMethodOverride]
        if self.field_definitions:
            return cast(
                ModelFieldDict[str, LiteralFieldDefinition | ListFieldDefinition],
                self.field_definitions.fields,
            )
        raise Exception(f"{self.__class__.__name__}.field_definition missing")


class EdgeModel(_DeclaredClass):
    __metatype__ = "EdgeModel"
    _meta: ClassVar[EdgeModelMeta] = EdgeModelMeta()  # pyright: ignore[reportIncompatibleVariableOverride]

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs) -> None:

        # Set model it uninitialised, as may inherit _initialised from parent class
        cls._initialised = False

        # Make sure _meta class is new and not inherited
        cls._meta = cls.__dict__.get("_meta", EdgeModelMeta())  # pyright: ignore[reportIncompatibleVariableOverride]

        # Set owner class on cls._meta
        cls._meta._owner_class = cls

        cls._register()
