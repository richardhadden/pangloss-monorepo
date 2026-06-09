import datetime
import warnings
from abc import ABC, abstractmethod
from collections import defaultdict
from functools import cache
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Literal,
    NamedTuple,
    Self,
    cast,
)
from uuid import UUID, uuid7

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationError,
    create_model,
    model_validator,
)
from pydantic.alias_generators import to_camel

from pangloss_models.model_registry import ModelRegistry

if TYPE_CHECKING:
    from pangloss_models.field_definitions import (
        FieldBinding,
        FieldDefinition,
        ModelFieldDict,
        ModelFields,
    )
    from pangloss_models.model_bases.edge_model import EdgeModel


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

    @classmethod
    def _register(cls):
        cls._depends_on_classes = set()

        ModelRegistry.register(cls)


class MetaGetter[T: type[_ActionClass]]:
    """Descriptor class for getting the _meta class from
    the _DeclaredClass of an _ActionClass"""

    def __get__(self, instance, owner: T):
        return owner._owner._meta  # type: ignore


class GetItemViaAttrDict[T](dict):
    def __getattr__(self, name) -> type[T]:
        if name in self:
            return self[name]
        return super().__getattribute__(name)


def get_labels_for_db_classes(self):

    # print(self._meta.fields)

    from pangloss_models.model_bases.trait import NonHeritableTrait
    from pangloss_models.utils import get_all_parent_classes, model_is_trait

    labels = [self._owner.__name__]

    parent_labels = []
    for c in get_all_parent_classes(self._owner):
        if (
            model_is_trait(c)
            and issubclass(c, NonHeritableTrait)
            and self._owner not in c.__subclasses__()
        ):
            pass
        else:
            parent_labels.append(c.__name__)
    labels.extend(parent_labels)
    labels.append(self.__metatype__)

    return labels


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
        return super().__pydantic_init_subclass__(**kwargs)

    @classmethod
    @cache
    def apply_edge_model(cls, edge_model: type[EdgeModel]) -> type[Self]:
        """Creates a variant of the model with additional 'edge_property' field
        of the type supplied"""

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


def allow_bind_on_this_item(
    item: _CreateBase | _UpdateBase, binding: FieldBinding
) -> bool:
    return bool(
        (
            binding.allowed_type_names
            and getattr(item, "type") in binding.allowed_type_names
        )
        or (
            binding.excluded_type_names
            and getattr(item, "type") not in binding.excluded_type_names
        )
        or (not binding.allowed_type_names and not binding.excluded_type_names)
    )


def recursively_add_bound_field_values(
    item: _CreateBase | _UpdateBase, binding: FieldBinding, value=None
):
    """Given an item, a FieldBinding instance and a value, try to
    bind values where rules are followed, and call itself to try on
    all nested items"""
    child_bound_fields = binding.child_fields
    if isinstance(item, _CreateBase | _UpdateBase) and allow_bind_on_this_item(
        item, binding
    ):
        for child_bound_field in child_bound_fields:
            if isinstance(item, list):
                for ri in item:
                    if hasattr(ri, child_bound_field) and not getattr(
                        ri, child_bound_field, None
                    ):
                        setattr(ri, child_bound_field, value)
            else:
                if hasattr(item, child_bound_field) and not getattr(
                    item, child_bound_field, None
                ):
                    setattr(item, child_bound_field, value)
    for related_field_name in item._meta.fields.relation_fields.keys():
        child_item = getattr(item, related_field_name)
        if isinstance(child_item, list):
            for ci in child_item:
                recursively_add_bound_field_values(ci, binding, value)
        else:
            recursively_add_bound_field_values(child_item, binding, value)


def build_fulfiled_model[T: _CreateDBBase | _UpdateDBBase](
    instance: T, fulfiled_classes: list[type[_DeclaredClass]]
) -> T:
    if isinstance(instance, _CreateDBBase):
        metafunction = "Create"
    elif isinstance(instance, _UpdateDBBase):
        metafunction = "Update"

    base_models: list[type[_DeclaredClass]] = [instance._owner]
    base_models.extend(fulfiled_classes)

    names = [c.__name__ for c in base_models]

    if metafunction == "Create":
        base_db_models = [m.CreateDB for m in base_models]  # type: ignore
    else:
        base_db_models = [m.UpdateDB for m in base_models]  # type: ignore

    new_fulfiled_model = create_model(
        f"({','.join(names)}){metafunction}DB",
        __base__=tuple(base_db_models),
        __module__=instance.__class__.__module__,
    )

    fulfilled_fields = {}
    fulfilled_data = instance.model_dump()

    fulfillable_models = get_fulfillable_models(instance)
    for fm, fulfilments in fulfillable_models.items():
        if fm in fulfiled_classes:
            for f in fulfilments:
                fulfilled_fields[f.field_on_class_to_fulfil] = getattr(
                    fm, f"{metafunction}DB"
                ).model_fields[f.field_on_class_to_fulfil]
                fulfilled_data[f.field_on_class_to_fulfil] = getattr(
                    instance, f.this_field_name
                )

    instance_fields = instance.__class__.model_fields

    all_new_fields = {
        **fulfilled_fields,
        **instance_fields,
    }
    for field_name, field_info in all_new_fields.items():
        new_fulfiled_model.model_fields[field_name] = field_info

    ## can't just duplicate fields because because...
    # relations might be pointing some kind of new Create object...
    # unless that's ... already assigned an ID?

    new_fulfiled_model.model_rebuild(force=True)

    # TODO: find a way to copy _meta fields...

    new_instance = new_fulfiled_model(**fulfilled_data)

    return new_instance


class _CreateBase(_ActionClass):
    def _to_db_model(self):

        db_model_instance: _CreateDBBase = self._owner.CreateDB(**self.model_dump())  # type: ignore
        recursively_propagate_semantic_space_types(db_model_instance, [], [], None)

        if db_model_instance._fulfils_classes:
            return build_fulfiled_model(
                db_model_instance, db_model_instance._fulfils_classes
            )

        return db_model_instance

    @model_validator(mode="after")
    def propagate_bound_values(self) -> Self:
        """Get any binding-fields for this model and try to bind
        on nested objects"""
        for (
            field_name,
            bindings,
        ) in self._meta.fields.bind_to_child_field_bindings.items():
            for binding in bindings:
                value = getattr(self, binding.bound_field)
                if binding.converter:
                    value = binding.converter(value)
                related_item = getattr(self, field_name)
                recursively_add_bound_field_values(related_item, binding, value=value)

        return self


def recursively_propagate_semantic_space_types(
    item: _CreateDBBase | _UpdateDBBase,
    semantic_spaces: list[str],
    semantic_space_labels: list[str],
    parent: _CreateDBBase | _UpdateDBBase | None,
):
    """Takes a _CreateDBBase instance and recursively adds type of semantic
    spaces to each contained type below that semantic space node"""
    from pangloss_models.model_bases.document import _DocumentCreateDBBase
    from pangloss_models.model_bases.semantic_space import (
        _SemanticSpaceCreateDBBase,
        _SemanticSpaceUpdateDBBase,
    )

    if not isinstance(item, (_SemanticSpaceCreateDBBase, _SemanticSpaceUpdateDBBase)):
        item.semantic_spaces = [*semantic_spaces]
        item.semantic_space_labels = [*semantic_space_labels]

    if isinstance(item, (_SemanticSpaceCreateDBBase, _SemanticSpaceUpdateDBBase)):
        semantic_spaces.append(getattr(item, "type"))

        if (
            parent
            and isinstance(parent, _DocumentCreateDBBase)
            and parent._meta.use_in_semantic_space_label  # type: ignore
        ):
            semantic_space_labels.append(
                f"{getattr(parent, 'type')} -> {getattr(item, 'type')}"
            )
        else:
            semantic_space_labels.append(getattr(item, "type"))

    for field_name, field_definition in item._meta.fields.relation_fields.items():
        if related_item := getattr(item, field_name, None):
            if isinstance(related_item, list):
                for ri in related_item:
                    if isinstance(ri, (_CreateDBBase, _UpdateDBBase)):
                        recursively_propagate_semantic_space_types(
                            ri, semantic_spaces, semantic_space_labels, item
                        )

            else:
                if isinstance(related_item, (_CreateDBBase, _UpdateDBBase)):
                    recursively_propagate_semantic_space_types(
                        related_item, semantic_spaces, semantic_space_labels, item
                    )

    return item


class Fulfilment(NamedTuple):
    this_field_name: str
    class_to_fulfil: type[_DeclaredClass]
    field_on_class_to_fulfil: str


def get_fulfillable_models(self):
    ffs: list[Fulfilment] = []
    for field_name, field_info in self._meta.fields.items():
        for field_fulfilment in field_info.field_required_to_fulfil:
            ffs.append(
                Fulfilment(
                    this_field_name=field_name,
                    class_to_fulfil=field_fulfilment.fulfils_class,
                    field_on_class_to_fulfil=field_fulfilment.field_name,
                )
            )

    model_fulfilments: dict[type[_DeclaredClass], list[Fulfilment]] = defaultdict(list)
    for ff in ffs:
        model_fulfilments[ff.class_to_fulfil].append(ff)
    return model_fulfilments


def get_fulfilled_classes(self, metafunction: Literal["Update"] | Literal["Create"]):
    model_fulfilments = get_fulfillable_models(self)

    models_fulfiled = []
    for model_to_fulfil_base, fulfilments in model_fulfilments.items():
        if metafunction == "Update":
            model_to_fulfil: type[_UpdateDBBase | _CreateDBBase] = (
                model_to_fulfil_base.UpdateDB  # type: ignore
            )
        elif metafunction == "Create":
            model_to_fulfil: type[_UpdateDBBase | _CreateDBBase] = (
                model_to_fulfil_base.CreateDB  # type: ignore
            )
        data = self.model_dump()
        del data["type"]
        for fulfilment in fulfilments:
            data[fulfilment.field_on_class_to_fulfil] = getattr(
                self, fulfilment.this_field_name
            )
        try:
            model_to_fulfil(**data, type=model_to_fulfil_base.__name__)
            models_fulfiled.append(model_to_fulfil_base)
        except ValidationError:
            pass

    return models_fulfiled


class _CreateDBBase(_ActionClass):
    _propagation_pass: bool = False
    semantic_spaces: list[str] = Field(default_factory=list)
    semantic_space_labels: list[str] = Field(default_factory=list)
    _labels = property(get_labels_for_db_classes)
    _fulfils_classes = property(lambda self: get_fulfilled_classes(self, "Create"))

    type: str

    @model_validator(mode="before")
    @classmethod
    def ensure_id(cls, data: Any) -> Any:
        """Create an ID for writing in advance;"""
        if not data.get("id", None):
            data["id"] = uuid7()
        return data

    def __init__(self, **kwargs):

        # Calling model_construct emits a warning that the data might not be valid,
        # so catch these and supress. This is fine as we later pass the data back to
        # the class.__init__, which will validate it
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if f := getattr(
                self._owner, "to_db_create", getattr(self._owner, "to_db", None)
            ):
                data = f(self.__class__.model_construct(**kwargs))
                if isinstance(data, dict):
                    super().__init__(**data)
                else:
                    super().__init__(**data.model_dump())
            else:
                super().__init__(**kwargs)


class _ViewBase(_ActionClass):
    id: UUID


class _APIHeadMeta(_BaseObject):
    created_by: str
    created_when: datetime.datetime
    updated_by: str
    updated_when: datetime.datetime


class _HeadViewBase(_ActionClass):
    id: UUID
    meta: _APIHeadMeta


class _UpdateBase(_ActionClass):
    id: UUID

    def _to_db_model(self):
        print("called for", self.__class__._owner.__name__)
        db_model_instance = self._owner.UpdateDB(**self.model_dump())  # type: ignore
        recursively_propagate_semantic_space_types(db_model_instance, [], [], None)
        return db_model_instance

    @model_validator(mode="after")
    def propagate_bound_values(self) -> Self:
        """Get any binding-fields for this model and try to bind
        on nested objects"""
        for (
            field_name,
            bindings,
        ) in self._meta.fields.bind_to_child_field_bindings.items():
            for binding in bindings:
                value = getattr(self, binding.bound_field)
                if binding.converter:
                    value = binding.converter(value)
                related_item = getattr(self, field_name)
                recursively_add_bound_field_values(related_item, binding, value=value)

        return self


class _UpdateDBBase(_ActionClass):
    id: UUID
    semantic_spaces: list[str] = Field(default_factory=list)
    semantic_space_labels: list[str] = Field(default_factory=list)
    _labels = property(get_labels_for_db_classes)
    _fulfils_classes = property(lambda self: get_fulfilled_classes(self, "Update"))

    def __init__(self, **kwargs):

        # Calling model_construct emits a warning that the data might not be valid,
        # so catch these and supress. This is fine as we later pass the data back to
        # the class.__init__, which will validate it
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if f := getattr(
                self._owner, "to_db_update", getattr(self._owner, "to_db", None)
            ):
                data = f(self.__class__.model_construct(**kwargs))

                if isinstance(data, dict):
                    super().__init__(**data)
                else:
                    super().__init__(**data.model_dump())
            else:
                super().__init__(**kwargs)
