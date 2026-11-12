from collections.abc import Awaitable, Callable
from typing import Annotated, Any, ClassVar, Self
from uuid import UUID, uuid7

from pydantic import AnyHttpUrl, ConfigDict, Field, model_validator

from pangloss_models.companions import Companion
from pangloss_models.exceptions import PanglossMetaError
from pangloss_models.field_definitions import (
    FieldDefinition,
    ModelFieldDict,
    ModelFields,
)
from pangloss_models.label_templates import LabelTemplateOption
from pangloss_models.merging import MergeRules
from pangloss_models.meta_kit import BaseMeta, InheritValue, MetaRules, WithMeta
from pangloss_models.model_bases.base_models import (
    DeclaredClassMeta,
    _CreateBase,
    _CreateDBBase,
    _DeclaredClass,
    _EditViewBase,
    _HeadViewBase,
    _ListItems,
    _ReferenceSetBase,
    _ReferenceViewBase,
    _UpdateBase,
    _UpdateDBBase,
    _ViewBase,
)
from pangloss_models.model_bases.model_tools import make_id


class EntityMeta(BaseMeta, DeclaredClassMeta):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    _owner_class: type[Entity] | InheritValue = InheritValue.AS_DEFAULT
    # How its label is worked out from what it holds (`pangloss_models.label_templates`): kept as its label if it has
    # one, else how it reads in the label of what holds it
    label_template: LabelTemplateOption = None
    abstract: Annotated[bool, MetaRules.DO_NOT_INHERIT] = False
    create_with_id: bool | InheritValue = False
    create_inline: bool | InheritValue = False
    accept_url_as_id: bool | InheritValue = True
    # Documents offered with a new one, and written with it if they are filled in (implementation_docs/companion-documents.md).
    # Inherited; `companions=[]` on a subclass has none. Not data
    companions: list[Companion] = Field(default_factory=list)
    # What a merge of two of these does by default with what the survivor does not take (`Entity.merge`;
    # implementation_docs/entity-identity.md). Inherited. Not data
    merge: MergeRules | None = None
    # Whether "search everything" (the homepage's box) finds it. Not inherited: `class Book(ZoteroBacked)` is found
    # although the class it is built on is not
    global_search: Annotated[bool, MetaRules.DO_NOT_INHERIT] = True
    # Fields of this class to keep an index of, for searching by them (see implementation_docs/structured-search.md). The
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
    field_definitions: Annotated[ModelFields, MetaRules.DO_NOT_INHERIT] = Field(
        default_factory=ModelFields
    )

    @property
    def fields(self) -> ModelFieldDict[str, FieldDefinition]:
        if self.field_definitions:
            return self.field_definitions.fields
        raise Exception(f"{self.__class__.__name__}.field_definition missing")

    @model_validator(mode="after")
    def check_create_with_id_set_with_create_inline(self) -> Self:
        if self.create_inline and not self.create_with_id:
            raise PanglossMetaError(
                "If EntityMeta.create_inline=True, EntityMeta.create_with_id must also be set to True"
            )
        return self


class _EntityCreateBase(_CreateBase):
    # The URLs it is to have (one given as its id is added to them)
    urls: list[AnyHttpUrl] = Field(default_factory=list)

    def save(self: Self) -> None: ...

    # (bound when the models are initialised: `pangloss_models.companions.save_with_companions`)
    async def save_with_companions(
        self: Self,
        companions: dict[str, dict[str, Any]],
        detail: bool = False,
        **options: Any,
    ) -> tuple[Any, list[Any]]: ...


class _EntityCreateDBBase(_CreateDBBase):
    id: UUID
    urls: set[AnyHttpUrl] = Field(default_factory=set)

    @model_validator(mode="before")
    @classmethod
    def ensure_id(cls, data: Any) -> Any:
        """If provided with a URL as id, pass the url to the urls field and replace with UUID;
        otherwise, generate a UUID. (Anything but a dict is for another member of a union to take.)"""
        if not isinstance(data, dict):
            return data

        if (id_value := data.get("id", None)) and isinstance(id_value, AnyHttpUrl):
            data["id"] = uuid7()
            data["urls"] = {*(data.get("urls") or ()), id_value}

        if not data.get("id", None):
            make_id(cls, data)
        return data


class _EntityReferenceSetBase(_ReferenceSetBase):
    pass


class _EntityReferenceViewBase(_ReferenceViewBase):
    label: str
    # The id of the entity this one was merged into, if it was (`Entity.merge`): only a relation that a merge
    # leaves where it is (`KeepOnMerge()`) still shows such an entity
    merged_into: UUID | None = None


class _EntityUpdateBase(_UpdateBase):
    # The URLs the entity should have, which replace its present ones; `None` (not
    # given) leaves them as they are, and `[]` removes them all
    urls: list[AnyHttpUrl] | None = None

    def save(self: Self) -> None: ...


class _EntityUpdateDBBase(_UpdateDBBase):
    urls: list[AnyHttpUrl] | None = None


class _EntityViewBase(_ViewBase):
    pass


class _EntityHeadViewBase(_HeadViewBase):
    urls: list[AnyHttpUrl] = Field(default_factory=list)


class _EntityEditViewBase(_EditViewBase):
    urls: list[AnyHttpUrl] = Field(default_factory=list)


class Entity(_DeclaredClass, WithMeta[EntityMeta]):
    __metatype__ = "Entity"
    Meta: ClassVar[type[EntityMeta]] = EntityMeta
    _meta: ClassVar[EntityMeta] = EntityMeta(create_with_id=False)

    Create: ClassVar[type[_EntityCreateBase]]
    CreateDB: ClassVar[type[_EntityCreateDBBase]]
    ReferenceSet: ClassVar[type[_EntityReferenceSetBase]]
    ReferenceView: ClassVar[type[_EntityReferenceViewBase]]
    Update: ClassVar[type[_EntityUpdateBase]]
    UpdateDB: ClassVar[type[_EntityUpdateDBBase]]

    View: ClassVar[type[_EntityViewBase]]
    HeadView: ClassVar[type[_EntityHeadViewBase]]
    EditView: ClassVar[type[_EntityEditViewBase]]

    def __new__(cls, *args, **kwargs) -> _EntityCreateBase:
        # (as for a document: `Person(...)` is `Person.Create(...)`)
        return cls.Create(*args, **kwargs)

    get: ClassVar[
        Callable[
            [AnyHttpUrl | UUID],
            _EntityHeadViewBase | None | Awaitable[_EntityHeadViewBase | None],
        ]
    ]

    get_for_edit: ClassVar[
        Callable[
            [AnyHttpUrl | UUID],
            _EntityEditViewBase | None | Awaitable[_EntityEditViewBase | None],
        ]
    ]

    delete: ClassVar[
        Callable[
            [AnyHttpUrl | UUID],
            None | Awaitable[None],
        ]
    ]

    # (bound when the models are initialised: implementation_docs/entity-identity.md)
    merge: ClassVar[Callable[..., Any]]
    """`await Person.merge(absorb=b, into=a)`: everything that refers to `b` refers to `a` instead, `a` has the
    fields chosen (`values`, an `Update` or what one takes; by default `pangloss_models.merging.merged_values`), and
    `b` is kept, marked as merged into `a`. Gives a `MergeResult`"""
    unmerge: ClassVar[Callable[..., Any]]
    """`await Person.unmerge(merge_id)`: undoes a merge. Gives an `UnmergeResult`"""
    merge_preview: ClassVar[Callable[..., Any]]
    """What a merge would do, writing nothing: a `MergePreview`"""
    merges: ClassVar[Callable[..., Any]]
    """`await Person.merges(id)`: the merges an entity is part of (`MergeRecord`s), the latest first"""

    list: ClassVar[
        Callable[
            [str],
            _ListItems[_EntityReferenceViewBase]
            | Awaitable[_ListItems[_EntityReferenceViewBase]],
        ]
    ]
