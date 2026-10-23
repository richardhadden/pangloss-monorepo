from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field
from pangloss_models.meta_kit import BaseMeta, InheritValue, MetaRules, WithMeta

from pangloss_models.field_definitions import (
    FieldDefinition,
    ModelFieldDict,
    ModelFields,
)
from pangloss_models.model_bases.context_label import ContextLabel
from pangloss_models.model_bases.base_models import (
    DeclaredClassMeta,
    _BaseObject,
    _CreateBase,
    _CreateDBBase,
    _DeclaredClass,
    _HeadViewBase,
    _ReferenceViewBase,
    _UpdateBase,
    _UpdateDBBase,
    _ViewBase,
)


class ReifiedRelationMeta(BaseMeta, DeclaredClassMeta):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    _owner_class: type[ReifiedRelation] | InheritValue = InheritValue.AS_DEFAULT
    require_label: Literal[False] = False

    field_definitions: Annotated[ModelFields, MetaRules.DO_NOT_INHERIT] = Field(
        default_factory=ModelFields
    )

    @property
    def fields(self) -> ModelFieldDict[str, FieldDefinition]:
        return self.field_definitions.fields


class _ReifiedRelationCreateBase(_CreateBase):
    pass


class _ReifiedRelationCreateDBBase(_CreateDBBase):
    pass


class _ReifiedRelationUpdateBase(_UpdateBase):
    pass


class _ReifiedRelationUpdateDBBase(_UpdateDBBase):
    pass


class _ReifiedRelationViewBase(_ViewBase):
    pass


class ReifiedRelation[TTarget](_DeclaredClass, WithMeta[ReifiedRelationMeta]):
    __metatype__ = "ReifiedRelation"
    Meta: ClassVar[type[ReifiedRelationMeta]] = ReifiedRelationMeta
    model_config = ConfigDict(validate_assignment=True)
    _meta: ClassVar[ReifiedRelationMeta] = ReifiedRelationMeta()  # type: ignore

    Create: ClassVar[type[_ReifiedRelationCreateBase]]
    CreateDB: ClassVar[type[_ReifiedRelationCreateDBBase]]
    Update: ClassVar[type[_ReifiedRelationUpdateBase]]
    UpdateDB: ClassVar[type[_ReifiedRelationUpdateDBBase]]

    View: ClassVar[type[_ReifiedRelationViewBase]]

    target: list[TTarget]



class ReifiedRelationDocumentMeta(BaseMeta, DeclaredClassMeta):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    _owner_class: type[ReifiedRelationDocument] | InheritValue = InheritValue.AS_DEFAULT
    require_label: bool | InheritValue = True
    view_extra_fields: Annotated[list[str], MetaRules.ACCUMULATE] = Field(
        default_factory=list
    )
    reference_view_extra_fields: Annotated[list[str], MetaRules.ACCUMULATE] = Field(
        default_factory=list
    )

    field_definitions: Annotated[ModelFields, MetaRules.DO_NOT_INHERIT] = Field(
        default_factory=ModelFields
    )

    @property
    def fields(self) -> ModelFieldDict[str, FieldDefinition]:
        return self.field_definitions.fields


class _ReifiedRelationDocumentCreateBase(_CreateBase):
    pass


class _ReifiedRelationDocumentCreateDBBase(_CreateDBBase):
    pass


class _ReifiedRelationDocumentUpdateBase(_UpdateBase):
    pass


class _ReifiedRelationDocumentUpdateDBBase(_UpdateDBBase):
    pass


class _ReifiedRelationDocumentReferenceViewBase(_ReferenceViewBase):
    label: str


class _ReifiedRelationDocumentViewAPIMeta(_BaseObject):
    semantic_spaces: list[str] = Field(default_factory=list)
    context_labels: list[ContextLabel] | None = None


class _ReifiedRelationDocumentViewBase(_ViewBase):
    meta: _ReifiedRelationDocumentViewAPIMeta = Field(
        default_factory=_ReifiedRelationDocumentViewAPIMeta
    )


class _ReifiedRelationDocumentHeadViewBase(_HeadViewBase):
    pass


class ReifiedRelationDocument[TTarget](
    _DeclaredClass, WithMeta[ReifiedRelationDocumentMeta]
):
    __metatype__ = "ReifiedRelationDocument"
    Meta: ClassVar[type[ReifiedRelationDocumentMeta]] = ReifiedRelationDocumentMeta
    model_config = ConfigDict(validate_assignment=True)
    _meta: ClassVar[ReifiedRelationDocumentMeta] = ReifiedRelationDocumentMeta()

    Create: ClassVar[type[_ReifiedRelationDocumentCreateBase]]
    CreateDB: ClassVar[type[_ReifiedRelationDocumentCreateDBBase]]
    Update: ClassVar[type[_ReifiedRelationDocumentUpdateBase]]
    UpdateDB: ClassVar[type[_ReifiedRelationDocumentUpdateDBBase]]
    ReferenceView: ClassVar[type[_ReifiedRelationDocumentReferenceViewBase]]

    View: ClassVar[type[_ReifiedRelationDocumentViewBase]]
    HeadView: ClassVar[type[_ReifiedRelationDocumentHeadViewBase]]

    target: list[TTarget]

