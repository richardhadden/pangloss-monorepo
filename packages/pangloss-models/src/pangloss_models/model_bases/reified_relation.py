from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_meta_kit import InheritValue, MetaRules

from pangloss_models.field_definitions import (
    FieldDefinition,
    ModelFieldDict,
    ModelFields,
)
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


class ReifiedRelationMeta(BaseModel, DeclaredClassMeta):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    _owner_class: type[ReifiedRelation] | InheritValue = InheritValue.AS_DEFAULT
    require_label: Literal[False] = False

    field_definitions: ModelFields = Field(default_factory=ModelFields)

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


class ReifiedRelation[TTarget](_DeclaredClass):
    __metatype__ = "ReifiedRelation"
    Meta: ClassVar[type[ReifiedRelationMeta]] = ReifiedRelationMeta
    model_config = ConfigDict(validate_assignment=True)
    _meta: ClassVar[ReifiedRelationMeta] = ReifiedRelationMeta()  # pyright: ignore[reportIncompatibleVariableOverride]

    Create: ClassVar[type[_ReifiedRelationCreateBase]]
    CreateDB: ClassVar[type[_ReifiedRelationCreateDBBase]]
    Update: ClassVar[type[_ReifiedRelationUpdateBase]]
    UpdateDB: ClassVar[type[_ReifiedRelationUpdateDBBase]]

    View: ClassVar[type[_ReifiedRelationViewBase]]

    target: list[TTarget]

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs) -> None:

        if cls is ReifiedRelation:
            return

        cls._initialised = False

        # Make sure _meta class is new and not inherited
        cls._meta = cls.__dict__.get("_meta", ReifiedRelationMeta())  # pyright: ignore[reportIncompatibleVariableOverride]

        # Set owner class on cls._meta
        cls._meta._owner_class = cls

        cls._register()


class ReifiedRelationDocumentMeta(BaseModel, DeclaredClassMeta):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    _owner_class: type[ReifiedRelationDocument] | InheritValue = InheritValue.AS_DEFAULT
    require_label: Literal[False] = False
    view_extra_fields: Annotated[list[str], MetaRules.ACCUMULATE] = Field(
        default_factory=list
    )
    reference_view_extra_fields: Annotated[list[str], MetaRules.ACCUMULATE] = Field(
        default_factory=list
    )

    field_definitions: ModelFields = Field(default_factory=ModelFields)

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
    semantic_space_labels: list[str] = Field(default_factory=list)


class _ReifiedRelationDocumentViewBase(_ViewBase):
    label: str
    meta: _ReifiedRelationDocumentViewAPIMeta = Field(
        default_factory=_ReifiedRelationDocumentViewAPIMeta
    )


class _ReifiedRelationDocumentHeadViewBase(_HeadViewBase):
    pass


class ReifiedRelationDocument[TTarget](_DeclaredClass):
    __metatype__ = "ReifiedRelationDocument"
    Meta: ClassVar[type[ReifiedRelationDocumentMeta]] = ReifiedRelationDocumentMeta
    model_config = ConfigDict(validate_assignment=True)
    _meta: ClassVar[ReifiedRelationDocumentMeta] = ReifiedRelationDocumentMeta()  # pyright: ignore[reportIncompatibleVariableOverride]

    Create: ClassVar[type[_ReifiedRelationDocumentCreateBase]]
    CreateDB: ClassVar[type[_ReifiedRelationDocumentCreateDBBase]]
    Update: ClassVar[type[_ReifiedRelationDocumentUpdateBase]]
    UpdateDB: ClassVar[type[_ReifiedRelationDocumentUpdateDBBase]]
    ReferenceView: ClassVar[type[_ReifiedRelationDocumentReferenceViewBase]]

    View: ClassVar[type[_ReifiedRelationDocumentViewBase]]
    HeadView: ClassVar[type[_ReifiedRelationDocumentHeadViewBase]]

    target: list[TTarget]

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs) -> None:

        if (
            cls is ReifiedRelationDocument
        ):  # or cls.__pydantic_generic_metadata__["args"]:
            return

        cls._initialised = False

        # Make sure _meta class is new and not inherited
        cls._meta = cls.__dict__.get("_meta", ReifiedRelationDocumentMeta())  # pyright: ignore[reportIncompatibleVariableOverride]

        # Set owner class on cls._meta
        cls._meta._owner_class = cls

        cls._register()
