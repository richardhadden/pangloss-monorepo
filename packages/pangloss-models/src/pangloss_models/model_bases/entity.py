from collections.abc import Awaitable, Callable
from typing import Annotated, Any, ClassVar, Self
from uuid import UUID, uuid7

from pydantic import AnyHttpUrl, ConfigDict, Field, model_validator
from pydantic_meta_kit import BaseMeta, InheritValue, MetaRules, WithMeta

from pangloss_models.exceptions import PanglossMetaError
from pangloss_models.field_definitions import (
    FieldDefinition,
    ModelFieldDict,
    ModelFields,
)
from pangloss_models.model_bases.base_models import (
    make_id,
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


class EntityMeta(BaseMeta, DeclaredClassMeta):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    _owner_class: type[Entity] | InheritValue = InheritValue.AS_DEFAULT
    abstract: Annotated[bool, MetaRules.DO_NOT_INHERIT] = False
    create_with_id: bool | InheritValue = False
    create_inline: bool | InheritValue = False
    accept_url_as_id: bool | InheritValue = True
    view_extra_fields: Annotated[list[str], MetaRules.ACCUMULATE] = Field(
        default_factory=list
    )
    reference_view_extra_fields: Annotated[list[str], MetaRules.ACCUMULATE] = Field(
        default_factory=list
    )
    field_definitions: ModelFields = Field(default_factory=ModelFields)

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
    def save(self: Self) -> None: ...


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
            if not data.get("urls", None):
                data["urls"] = set([id_value])
            else:
                data["urls"].add(id_value)

        if not data.get("id", None):
            make_id(cls, data)
        return data


class _EntityReferenceSetBase(_ReferenceSetBase):
    pass


class _EntityReferenceViewBase(_ReferenceViewBase):
    label: str


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
    _meta: ClassVar[EntityMeta] = EntityMeta(create_with_id=False)  # pyright: ignore[reportIncompatibleVariableOverride]

    Create: ClassVar[type[_EntityCreateBase]]
    CreateDB: ClassVar[type[_EntityCreateDBBase]]
    ReferenceSet: ClassVar[type[_EntityReferenceSetBase]]
    ReferenceView: ClassVar[type[_EntityReferenceViewBase]]
    Update: ClassVar[type[_EntityUpdateBase]]
    UpdateDB: ClassVar[type[_EntityUpdateDBBase]]

    View: ClassVar[type[_EntityViewBase]]
    HeadView: ClassVar[type[_HeadViewBase]]
    EditView: ClassVar[type[_EntityEditViewBase]]

    @classmethod
    def __pydantic_init_subclass__(cls, **_):

        cls._initialised = False

        cls._meta = cls.__dict__.get("_meta", EntityMeta(_owner_class=cls))  # pyright: ignore[reportIncompatibleVariableOverride]

        cls._meta._owner_class = cls

        cls._register()

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

    list: ClassVar[
        Callable[
            [str],
            _ListItems[_EntityReferenceViewBase]
            | Awaitable[_ListItems[_EntityReferenceViewBase]],
        ]
    ]
