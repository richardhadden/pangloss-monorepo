from collections.abc import Awaitable
from typing import Annotated, Any, Callable, ClassVar, Self
from uuid import UUID, uuid7

from pydantic import AnyHttpUrl, ConfigDict, Field, model_validator
from pydantic_meta_kit import BaseMeta, InheritValue, MetaRules, WithMeta

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
    _ReferenceSetBase,
    _ReferenceViewBase,
    _UpdateBase,
    _UpdateDBBase,
    _ViewBase,
)


class DocumentMeta(BaseMeta, DeclaredClassMeta):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    abstract: Annotated[bool, MetaRules.DO_NOT_INHERIT] = False
    create_with_id: bool | InheritValue = False
    accept_url_as_id: bool | InheritValue = False
    require_label: bool | InheritValue = True
    view_extra_fields: Annotated[list[str], MetaRules.ACCUMULATE] = Field(
        default_factory=list
    )
    reference_view_extra_fields: Annotated[list[str], MetaRules.ACCUMULATE] = Field(
        default_factory=list
    )
    use_in_semantic_space_label: bool = True
    field_definitions: ModelFields = Field(default_factory=ModelFields)
    _owner_class: type[Document] | InheritValue = InheritValue.AS_DEFAULT  # noqa: F821

    @property
    def fields(self) -> ModelFieldDict[str, FieldDefinition]:
        return self.field_definitions.fields


class _DocumentCreateBase(_CreateBase):
    def save(self: Self) -> None: ...


class _DocumentCreateDBBase(_CreateDBBase):
    id: UUID
    db_labels: set[str] = Field(default_factory=set)

    @model_validator(mode="before")
    @classmethod
    def ensure_id(cls, data: Any) -> Any:
        if not data.get("id", None):
            data["id"] = uuid7()
        return data


class _DocumentViewAPIMeta(_BaseObject):
    semantic_spaces: list[str] = Field(default_factory=list)
    semantic_space_labels: list[str] = Field(default_factory=list)


class _DocumentViewBase(_ViewBase):
    meta: _DocumentViewAPIMeta = Field(default_factory=_DocumentViewAPIMeta)


class _DocumentHeadViewBase(_HeadViewBase):
    pass


class _DocumentUpdateBase(_UpdateBase):
    pass


class _DocumentUpdateDBBase(_UpdateDBBase):
    pass


class _DocumentReferenceViewAPIMeta(_BaseObject):
    is_head_node: bool = False
    head_node_id: UUID | None = None
    head_node_type: str | None = None
    semantic_spaces: list[str] = Field(default_factory=list)
    semantic_space_labels: list[str] = Field(default_factory=list)


class _DocumentReferenceViewBase(_ReferenceViewBase):
    meta: _DocumentReferenceViewAPIMeta = Field(
        default_factory=_DocumentReferenceViewAPIMeta
    )


class _DocumentReferenceSetBase(_ReferenceSetBase):
    pass


class Document(_DeclaredClass, WithMeta[DocumentMeta]):
    """An arbitrarily complex object, with nestable subdocuments and relations to Entities"""

    __metatype__ = "Document"
    Meta: ClassVar[type[DocumentMeta]] = DocumentMeta
    model_config = ConfigDict(validate_assignment=True)

    _meta: ClassVar[DocumentMeta] = DocumentMeta(create_with_id=False)  # pyright: ignore[reportIncompatibleVariableOverride]

    Create: ClassVar[type[_DocumentCreateBase]]
    CreateDB: ClassVar[type[_DocumentCreateDBBase]]

    Update: ClassVar[type[_DocumentUpdateBase]]
    UpdateDB: ClassVar[type[_DocumentUpdateDBBase]]
    View: ClassVar[type[_DocumentViewBase]]
    HeadView: ClassVar[type[_DocumentHeadViewBase]]

    ReferenceView: ClassVar[type[_DocumentReferenceViewBase]]
    ReferenceSetBase: ClassVar[type[_DocumentReferenceSetBase]]

    # @classmethod
    # def get(cls, id: UUID | AnyHttpUrl) -> _DocumentHeadViewBase:
    #    raise NotImplementedError()

    get: ClassVar[
        Callable[
            [AnyHttpUrl | UUID],
            _DocumentHeadViewBase | Awaitable[_DocumentHeadViewBase],
        ]
    ]

    def __new__(cls, *args, **kwargs) -> _DocumentCreateBase:
        return cls.Create(*args, **kwargs)

    @classmethod
    def __pydantic_init_subclass__(cls, **_):

        # Set model it uninitialised, as may inherit _initialised from parent class
        cls._initialised = False

        # Make sure _meta class is new and not inherited
        cls._meta = cls.__dict__.get("_meta", DocumentMeta())  # pyright: ignore[reportIncompatibleVariableOverride]

        # Set owner class on cls._meta
        cls._meta._owner_class = cls

        cls._register()
