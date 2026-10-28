import datetime
import warnings
from abc import ABC, abstractmethod
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Literal,
    Self,
    cast,
)
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    create_model,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel

from pangloss_models.hooks import convert_from_database
from pangloss_models.meta_kit import WithMeta
from pangloss_models.meta_slots import apply_meta_slots
from pangloss_models.model_bases.binding import bind_values_to_children
from pangloss_models.model_bases.context_label import ContextLabel
from pangloss_models.model_bases.from_database import (
    unwrap_single_item_lists,
)
from pangloss_models.model_bases.fulfilment import (
    build_fulfilled_model,
    fulfilled_classes_of,
)
from pangloss_models.model_bases.instance_context import (
    recursively_propagate_context_types,
)
from pangloss_models.model_bases.labels import get_labels_for_db_classes
from pangloss_models.model_bases.model_tools import (
    data_for_db,
    inherit_fields,
    make_id,
)
from pangloss_models.model_registry import ModelRegistry

if TYPE_CHECKING:
    from pangloss_models.field_definitions import (
        FieldDefinition,
        ModelFieldDict,
        ModelFields,
    )
    from pangloss_models.model_bases.edge_model import EdgeModel


# --- what every generated model is made of ----------------------------------------------------------


class _BaseObject(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True, alias_generator=to_camel, populate_by_name=True
    )


class DeclaredClassMeta(ABC):
    @property
    @abstractmethod
    def fields(self) -> ModelFieldDict[str, FieldDefinition]: ...

    field_definitions: ModelFields

    @property
    def description(self) -> str | None:
        """Gets description for a class by looking up its docstring"""
        if _owner := getattr(self, "_owner_class", None):
            _owner = cast(_DeclaredClass, _owner)
            if _owner.__doc__:
                return _owner.__doc__
        return None


class _DeclaredClass(_BaseObject):
    _meta: ClassVar[DeclaredClassMeta]
    _depends_on_classes: ClassVar[set[type[_DeclaredClass]]] = PrivateAttr()
    __metatype__: ClassVar[
        Literal[
            "AnnotatedValue",
            "Conjunction",
            "Document",
            "EdgeModel",
            "Embedded",
            "Entity",
            "ReifiedRelation",
            "ReifiedRelationDocument",
            "SemanticSpace",
        ]
    ]

    _kind_base: ClassVar[bool] = False
    """Set on the classes of the library that stand for a kind (`Document`, `Trait`), which are not declared models"""

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        """Every declared model: its `_meta` is made from its parent's (by `WithMeta`), says which class owns
        it, and the class is registered."""
        super().__pydantic_init_subclass__(**kwargs)
        own = cls.__dict__
        if "__metatype__" in own or own.get("_kind_base"):
            return
        cls._initialised = False
        apply_meta_slots(cls)
        if not issubclass(cls, WithMeta):
            # (a trait: it has a meta of its own, and does not inherit one)
            if (meta_class := getattr(cls, "Meta", None)) is None:
                return
            cls._meta = own.get("_meta", meta_class())
        elif origin := cls.__pydantic_generic_metadata__["origin"]:
            # (`WithMeta` gives a parametrisation of a generic, `AnnotatedValue[str]`, the meta of the generic itself:
            # it needs its own, made as for a subclass with none)
            cls._meta = origin._meta & None  # type: ignore[operator]
        cls._meta._owner_class = cls  # type: ignore[attr-defined]
        cls._register()

    @classmethod
    def _register(cls):
        cls._depends_on_classes = set()

        ModelRegistry.register(cls)


class MetaGetter[T: type[_ActionClass]]:
    """Descriptor class for getting the _meta class from
    the _DeclaredClass of an _ActionClass"""

    def __get__(self, instance, owner: T):
        return owner._owner._meta


class GetItemViaAttrDict[T](dict):
    def __getattr__(self, name) -> type[T]:
        if name in self:
            return self[name]
        return super().__getattribute__(name)


class _ActionClass(_BaseObject):
    _owner: ClassVar[type[_DeclaredClass]]
    _meta: ClassVar = MetaGetter[type[Self]]()
    _via: ClassVar[GetItemViaAttrDict[Self]]

    @property
    def __metatype__(self):
        return self._owner.__metatype__

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        cls._via = GetItemViaAttrDict()
        ModelRegistry._action_classes.append(cls)
        return super().__pydantic_init_subclass__(**kwargs)

    @classmethod
    def apply_edge_model(cls, edge_model: type[EdgeModel]) -> type[Self]:
        """Creates a variant of the model with additional 'edge_property' field
        of the type supplied (once: it is kept in `_via`)"""

        made = cls._via.get(edge_model.__name__)
        if (
            made is not None
            and made.model_fields["edge_properties"].annotation is edge_model
        ):
            return made

        # For a ReifiedRelationDocument, we need to construct a better name for the class by
        # some introspection of the origin and args
        if origin := cls._owner.__pydantic_generic_metadata__["origin"]:
            base_model_name = (
                f"{origin.__name__}"
                f"[{', '.join(arg.__name__ for arg in cls._owner.__pydantic_generic_metadata__['args'])}]"
                f"{cls.__name__.split(']')[1]}"
            )

        else:
            base_model_name = cls.__name__

        model = create_model(
            f"{base_model_name}Via{edge_model.__name__}",
            __base__=cls,
            edge_properties=edge_model,
        )
        inherit_fields(model, cls)
        cls._via[edge_model.__name__] = model
        return model


class _ReferenceViewBase(_ActionClass):
    id: UUID
    label: str


class _ReferenceSetBase(_ActionClass):
    id: UUID

    @model_validator(mode="after")
    def remove_label(self):
        """Should not start setting the label of a ReferenceSet,
        but it's allowed as a field as it might be nice sometimes
        to write it in code for clarity"""
        self.label = None
        return self


# --- writing: Create and Update, and what is written to the database -----------------------------------


class _CreateBase(_ActionClass):
    def _to_db_model(self):

        db_model_instance: _CreateDBBase = self._owner.CreateDB(**self.model_dump())
        recursively_propagate_context_types(db_model_instance, [], [], None)

        if db_model_instance._fulfils_classes:
            return build_fulfilled_model(
                db_model_instance, db_model_instance._fulfils_classes
            )

        return db_model_instance

    @model_validator(mode="after")
    def propagate_bound_values(self) -> Self:
        """Get any binding-fields for this model and try to bind on nested objects"""
        bind_values_to_children(self)
        return self


class _CreateDBBase(_ActionClass):
    _propagation_pass: bool = False
    semantic_spaces: list[str] = Field(default_factory=list)
    context_labels: list[ContextLabel] | None = None
    _labels = property(get_labels_for_db_classes)
    _fulfils_cache: list | None = None
    _fulfils_classes = property(lambda self: fulfilled_classes_of(self, "Create"))

    type: str
    id: UUID

    @model_validator(mode="before")
    @classmethod
    def ensure_id(cls, data: Any) -> Any:
        """Create an ID for writing in advance"""
        if isinstance(data, dict) and not data.get("id", None):
            make_id(cls, data)
        return data

    def __init__(self, **kwargs):
        # (`model_construct` warns that the data might not be valid; it is validated by `__init__`)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            super().__init__(**data_for_db(self, kwargs, "to_db_create", "to_db"))


class _UpdateBase(_ActionClass):
    id: UUID

    def _to_db_model(self):

        db_model_instance = self._owner.UpdateDB(**self.model_dump())
        recursively_propagate_context_types(db_model_instance, [], [], None)
        return db_model_instance

    @model_validator(mode="after")
    def propagate_bound_values(self) -> Self:
        """Get any binding-fields for this model and try to bind on nested objects"""
        bind_values_to_children(self)
        return self


class _UpdateDBBase(_ActionClass):
    id: UUID
    semantic_spaces: list[str] = Field(default_factory=list)
    context_labels: list[ContextLabel] = Field(default_factory=list)
    _labels = property(get_labels_for_db_classes)
    _fulfils_cache: list | None = None
    _fulfils_classes = property(lambda self: fulfilled_classes_of(self, "Update"))

    def __init__(self, **kwargs):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            super().__init__(**data_for_db(self, kwargs, "to_db_update", "to_db"))


# --- reading: what the database returns ---------------------------------------------------------------


class _FromDatabaseBase(_ActionClass):
    """A model that is made from what the database returns"""

    @model_validator(mode="before")
    @classmethod
    def convert_database_types(cls, data: Any) -> Any:
        return convert_from_database(data)

    @model_validator(mode="before")
    @classmethod
    def convert_lists(cls, data: Any) -> Any:
        return unwrap_single_item_lists(cls, data)


class _ViewBase(_FromDatabaseBase):
    id: UUID


class _APIHeadMeta(_BaseObject):
    created_by: str
    created_when: datetime.datetime
    updated_by: str | None
    updated_when: datetime.datetime | None
    semantic_spaces: list[str] = Field(default_factory=list)
    context_labels: list[ContextLabel] | None = None
    head_node_type: str | None = None
    head_node_id: UUID | None = None
    # An entity that something refers to cannot be deleted: when someone tried to,
    # it was marked instead
    marked_for_deletion: bool = False
    # 1 when made, and 1 more for each update: an update can say which version it
    # was based on, and is refused if that is no longer the latest
    version: int = 1
    # False for a document that has not been published (seen only by those who are logged in), and
    # `review_status` (`unchecked`, `errors_found` or `checked`) if `pangloss-review` keeps one. Read only: an
    # update neither takes nor changes them
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
    def context_labels_labels_to_empty_list(cls, v):
        return [] if v is None else v

    @field_validator("marked_for_deletion", mode="before")
    @classmethod
    def marked_for_deletion_to_false(cls, v):
        return False if v is None else v

    @model_validator(mode="before")
    @classmethod
    def convert_database_types(cls, data: Any) -> Any:
        return convert_from_database(data)


class _ListItems[T: _ReferenceViewBase](_BaseObject):
    results: list[T]
    count: int
    page: int
    page_size: int
    next_page: int | None
    previous_page: int | None
    # True if a word of the search had more hits in the text index than were looked at (`SEARCH_HIT_LIMIT`):
    # then there are more results than `count`
    truncated: bool = False


class _HeadViewBase(_FromDatabaseBase):
    id: UUID
    meta: _APIHeadMeta

    def __repr__(self):
        return f"<{self._owner.__name__} {super().__repr__()}>"

    def __str__(self):
        return f"<{self._owner.__name__}.HeadView {super().__str__()}>"


class _EditViewBase(_HeadViewBase):
    """A head node as it is edited: its own values and outgoing relations, but none of
    the incoming relations (those belong to the documents they are written in)"""

    def __str__(self):
        return f"<{self._owner.__name__}.EditView {_ActionClass.__str__(self)}>"
