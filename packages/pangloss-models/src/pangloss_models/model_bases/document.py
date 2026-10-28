import datetime
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, ClassVar, Literal, Self
from uuid import UUID

from pydantic import AnyHttpUrl, ConfigDict, Field, field_validator, model_validator

from pangloss_models.field_definitions import (
    FieldDefinition,
    ModelFieldDict,
    ModelFields,
)
from pangloss_models.hooks import convert_from_database
from pangloss_models.meta_kit import BaseMeta, InheritValue, MetaRules, WithMeta
from pangloss_models.model_bases.base_models import (
    DeclaredClassMeta,
    _BaseObject,
    _CreateBase,
    _CreateDBBase,
    _DeclaredClass,
    _HeadViewBase,
    _ListItems,
    _ReferenceSetBase,
    _ReferenceViewBase,
    _UpdateBase,
    _UpdateDBBase,
    _ViewBase,
)
from pangloss_models.model_bases.context_label import ContextLabel
from pangloss_models.model_bases.model_tools import make_id


class DocumentMeta(BaseMeta, DeclaredClassMeta):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    abstract: Annotated[bool, MetaRules.DO_NOT_INHERIT] = False
    create_with_id: bool | InheritValue = False
    accept_url_as_id: bool | InheritValue = False
    require_label: bool | InheritValue = True
    # Fields of this class to keep an index of, for searching by them (see docs/structured-search.md). The
    # nodes of its subclasses are in it too, so it is not inherited
    indexes: Annotated[list[str], MetaRules.DO_NOT_INHERIT] = Field(
        default_factory=list
    )
    view_extra_fields: Annotated[list[str], MetaRules.ACCUMULATE] = Field(
        default_factory=list
    )
    reference_view_extra_fields: Annotated[list[str], MetaRules.ACCUMULATE] = Field(
        default_factory=list
    )
    use_in_semantic_space_label: bool = True
    field_definitions: Annotated[ModelFields, MetaRules.DO_NOT_INHERIT] = Field(
        default_factory=ModelFields
    )
    _owner_class: type[Document] | InheritValue = InheritValue.AS_DEFAULT

    @property
    def fields(self) -> ModelFieldDict[str, FieldDefinition]:
        return self.field_definitions.fields


# What a document can say of its review status when it is written (see `pangloss-review`): for data that is
# known to be right, or to have been checked already, such as a load from outside. Optional, and without
# `pangloss-review` (or for a class it does not review) it is ignored. It is not stored as a field: the review
# package writes the state (`published`, who, when) on the head node.
REVIEW_STATUS_DESCRIPTION = (
    "With pangloss-review: write the document with this review status ('checked' publishes it). "
    "Without it, a new document is 'unchecked' and an update keeps the state it has."
)


class _DocumentCreateBase(_CreateBase):
    review_status: Literal["unchecked", "errors_found", "checked"] | None = Field(
        default=None, description=REVIEW_STATUS_DESCRIPTION
    )

    def save(self: Self) -> None: ...


class _DocumentCreateDBBase(_CreateDBBase):
    id: UUID
    review_status: Literal["unchecked", "errors_found", "checked"] | None = None
    db_labels: set[str] = Field(default_factory=set)

    @model_validator(mode="before")
    @classmethod
    def ensure_id(cls, data: Any) -> Any:
        if isinstance(data, dict) and not data.get("id", None):
            make_id(cls, data)
        return data


class _DocumentViewAPIMeta(_BaseObject):
    semantic_spaces: list[str] = Field(default_factory=list)
    context_labels: list[ContextLabel] | None = None


class _DocumentViewBase(_ViewBase):
    meta: _DocumentViewAPIMeta = Field(default_factory=_DocumentViewAPIMeta)


class _DocumentHeadViewBase(_HeadViewBase):
    pass


class _DocumentUpdateBase(_UpdateBase):
    review_status: Literal["unchecked", "errors_found", "checked"] | None = Field(
        default=None, description=REVIEW_STATUS_DESCRIPTION
    )

    def save(self: Self) -> None: ...


class _DocumentUpdateDBBase(_UpdateDBBase):
    review_status: Literal["unchecked", "errors_found", "checked"] | None = None


class _DocumentReferenceViewAPIMeta(_BaseObject):
    is_head_node: bool = False
    head_node_id: UUID | None = None
    head_node_type: str | None = None
    semantic_spaces: list[str] | None = Field(default_factory=list)
    context_labels: list[ContextLabel] | None = None
    created_by: str | None = None
    created_when: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
    updated_by: str | None = None
    updated_when: datetime.datetime | None = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
    # As in the meta of a head view: False if it is not published, and the status if `pangloss-review` keeps one
    published: bool = True
    review_status: str | None = None

    @field_validator("published", mode="before")
    @classmethod
    def no_published_is_true(cls, v):
        return True if v is None else v

    @field_validator("semantic_spaces", mode="before")
    @classmethod
    def semantic_spaces_to_empty_list(cls, v):
        return [] if v is None else v

    @field_validator("context_labels", mode="before")
    @classmethod
    def context_labels_to_empty_list(cls, v):
        return [] if v is None else v

    @field_validator("created_when", mode="before")
    @classmethod
    def convert_database_created_when_date(cls, v) -> Any:
        return convert_from_database(v)

    @field_validator("updated_when", mode="before")
    @classmethod
    def convert_database_updated_when_date(cls, v) -> Any:
        return convert_from_database(v)


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

    _meta: ClassVar[DocumentMeta] = DocumentMeta(create_with_id=False)

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

    delete: ClassVar[
        Callable[
            [AnyHttpUrl | UUID],
            None | Awaitable[None],
        ]
    ]

    list: ClassVar[
        Callable[
            [str],
            _ListItems[_DocumentReferenceViewBase]
            | Awaitable[_ListItems[_DocumentReferenceViewBase]],
        ]
    ]

    def __new__(cls, *args, **kwargs) -> _DocumentCreateBase:
        return cls.Create(*args, **kwargs)
