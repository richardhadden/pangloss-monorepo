from typing import Annotated, ClassVar, cast

from pydantic import ConfigDict, Field
from pydantic_meta_kit import BaseMeta, InheritValue, MetaRules, WithMeta

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

    field_definitions: Annotated[ModelFields, MetaRules.DO_NOT_INHERIT] = Field(
        default_factory=ModelFields
    )

    @property
    def fields(  # type: ignore
        self,
    ) -> ModelFieldDict[str, LiteralFieldDefinition | ListFieldDefinition]:
        if self.field_definitions:
            return cast(
                ModelFieldDict[str, LiteralFieldDefinition | ListFieldDefinition],
                self.field_definitions.fields,
            )
        raise Exception(f"{self.__class__.__name__}.field_definition missing")


class EdgeModel(_DeclaredClass, WithMeta[EdgeModelMeta]):
    __metatype__ = "EdgeModel"
    _meta: ClassVar[EdgeModelMeta] = EdgeModelMeta()

