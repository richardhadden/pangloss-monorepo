"""Typologies: `class RoleTypology(Typology)` makes the entity `RoleType`, a vocabulary of types in a hierarchy.

    class Role(Entity):
        has_type: list[Typed[RoleTypology]]

    class RoleTypology(Typology):
        _typology_meta = TypologyMeta(name="RoleType")

A `Typology` is not a model: it holds the meta, the entity it makes (`RoleTypology.Type`) and the operations on the
vocabulary. The entity is an ordinary one, so it has everything an entity has. Its relations are always `has_type` (from
the entity that has the type) and `is_subtype_of` (from a type to its one supertype); `pangloss_typology.service` keeps the
hierarchy valid.
"""

import re
from dataclasses import dataclass, field
from types import get_original_bases
from typing import Annotated, Any, ClassVar, ForwardRef, Literal, get_origin

from annotated_types import MaxLen
from pangloss_models.exceptions import PanglossMetaError
from pangloss_models.model_bases.configs import RelationConfig
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_registry import ModelRegistry
from pangloss_models.protection import Protection
from pydantic.fields import FieldInfo

HAS_TYPE = "has_type"
TYPE_OF = "type_of"
IS_SUBTYPE_OF = "is_subtype_of"
IS_SUPERTYPE_OF = "is_supertype_of"
IS_CONCRETE = "is_concrete"

Concrete = Literal["per_type", "always"]


@dataclass(frozen=True)
class TypologyMeta:
    """What a typology says about itself"""

    name: str
    """The name of the entity made, ending in `Type`: `RoleType`"""
    also: type[Entity] | None = None
    """An entity class that a type can also be (`Role`): the generated entity is a subclass of it, so a relation to `Role`
    accepts a type that is also a `Role`"""
    concrete: Concrete = "per_type"
    """When a type is also the `also` class: `"per_type"` (each type has a switch, `is_concrete`, which starts off) or
    `"always"`"""
    defaults: dict[str, Any] = field(default_factory=dict)
    """Values for the required fields of `also` that a type cannot know (a type is created with these)"""
    languages: list[str] | None = None
    """The languages that a label can be given in besides the default (`label_de`); the project's `INTERFACE_LANGUAGES`
    if not given"""

    def __post_init__(self):
        if not isinstance(self.name, str) or not re.fullmatch(
            r"[A-Z][A-Za-z0-9]*Type", self.name
        ):
            raise PanglossMetaError(
                f"TypologyMeta.name must be a class name ending in 'Type' (and more than that): {self.name!r}"
            )
        if self.concrete not in ("per_type", "always"):
            raise PanglossMetaError(
                f"TypologyMeta.concrete must be 'per_type' or 'always': {self.concrete!r}"
            )
        if self.also is None and (self.defaults or self.concrete != "per_type"):
            raise PanglossMetaError(
                "TypologyMeta.defaults and .concrete are for a typology that is `also` another class"
            )


def language_field(code: str) -> str:
    """The field that holds the label in a language: `label_de`, `label_pt_br`"""
    return "label_" + re.sub(r"[^a-z0-9]+", "_", code.lower()).strip("_")


def setting(name: str, default: Any) -> Any:
    from pangloss_core import settings as core_settings

    return getattr(core_settings.__dict__.get("SETTINGS"), name, default)


def languages_of(meta: TypologyMeta) -> list[str]:
    """The languages besides the default that a label can be given in"""
    if meta.languages is not None:
        return list(meta.languages)
    default = setting("DEFAULT_INTERFACE_LANGUAGE", "en")
    return [code for code in setting("INTERFACE_LANGUAGES", []) if code != default]


class Typology:
    """Inherit directly from this, with a `_typology_meta`, to make a typology"""

    _typology_meta: ClassVar[TypologyMeta]
    Type: ClassVar[type[Entity]]
    """The entity made: `RoleType`"""

    registry: ClassVar[dict[str, type[Typology]]] = {}
    """The typologies by the name of their entity"""

    @classmethod
    def new_values(cls) -> dict[str, Any]:
        """What a type is created with besides what is asked: an empty supertype, and the `defaults` and empty lists for
        the fields of `also` that a type cannot know (a `Create` requires them all)"""
        return {
            IS_SUBTYPE_OF: [],
            **getattr(cls.Type, "__typology_values__", {}),
        }

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if get_original_bases(cls) != (Typology,):
            raise PanglossMetaError(
                f"{cls.__name__} must inherit directly from Typology (a typology cannot be subclassed: "
                "a narrower vocabulary is a subtype in the hierarchy)"
            )
        if not re.fullmatch(r"[A-Z][A-Za-z0-9]*Typology", cls.__name__):
            raise PanglossMetaError(
                f"The name of the typology {cls.__name__} must end in 'Typology'"
            )
        meta = cls.__dict__.get("_typology_meta")
        if not isinstance(meta, TypologyMeta):
            raise PanglossMetaError(
                f"{cls.__name__} needs a `_typology_meta = TypologyMeta(name=...)`"
            )
        if meta.name in ModelRegistry._model_dict:
            raise PanglossMetaError(
                f"{cls.__name__}: there is already a model called {meta.name}"
            )
        cls.Type = make_entity(cls, meta)
        Typology.registry[meta.name] = cls

    # --- the operations (see `pangloss_typology.service`) ---

    @classmethod
    async def create(cls, label: str, **kwargs: Any):
        from pangloss_typology import service

        return await service.create(cls, label, **kwargs)

    @classmethod
    async def move(cls, id: Any, to: Any = None):
        from pangloss_typology import service

        return await service.move(cls, id, to)

    @classmethod
    async def tree(cls):
        from pangloss_typology import service

        return await service.tree_of(cls)

    @classmethod
    async def path(cls, id: Any):
        from pangloss_typology import service

        return await service.path(cls, id)

    @classmethod
    async def ancestors(cls, id: Any):
        from pangloss_typology import service

        return await service.ancestors(cls, id)

    @classmethod
    async def descendants(cls, id: Any):
        from pangloss_typology import service

        return await service.descendants(cls, id)

    @classmethod
    async def view(cls, id: Any, **kwargs: Any):
        from pangloss_typology import service

        return await service.view(cls, id, **kwargs)

    @classmethod
    async def merge(cls, from_: Any, into: Any):
        from pangloss_typology import service

        return await service.merge(cls, from_, into)

    @classmethod
    async def delete(cls, id: Any):
        from pangloss_typology import service

        return await service.delete(cls, id)

    @classmethod
    async def set_concrete(cls, id: Any, on: bool):
        from pangloss_typology import service

        return await service.set_concrete(cls, id, on)


class Typed:
    """`Typed[RoleTypology]` in a field: a type of that typology (it is the entity the typology made)

        has_type: list[Typed[RoleTypology]]

    The field is called `has_type`, whatever the typology: the edge is always `has_type`, so a query for what has a type
    never needs to know the field names. A field that goes to several typologies is one `has_type`
    (`list[Typed[RoleTypology] | Typed[OfficeTypology]]`)."""

    def __class_getitem__(cls, typology: Any) -> Any:
        if not (isinstance(typology, type) and issubclass(typology, Typology)):
            raise PanglossMetaError(
                f"Typed[...] takes a typology (a class that inherits from Typology): {typology!r}"
            )
        return typology.Type


# --- making the entity -------------------------------------------------------------------------------


def unmanaged_labels(also: type[Entity]) -> tuple[str, ...]:
    """The labels that a type has only when it is switched on as `also`: those the `also` class gives"""
    from pangloss_models.model_bases.labels import labels_for_model

    return tuple(labels_for_model(also, also.__metatype__)[:-1])


def is_list(annotation: Any) -> bool:
    """Whether an annotation is a list, also one not yet evaluated (the class that it names is not made yet)"""
    if isinstance(annotation, ForwardRef):
        annotation = annotation.__forward_arg__
    if isinstance(annotation, str):
        return annotation.replace(" ", "").startswith("list[")
    return get_origin(annotation) is list


def values_for_also(
    also: type[Entity], defaults: dict[str, Any], name: str
) -> dict[str, Any]:
    """What a type is created with for the fields of `also` that a type cannot know: the `defaults`, and `[]` for a list.
    (A `Create` requires every field that has no `None` default, so the service fills these in.) Another required field is
    an error: it says which"""
    unknown = sorted(set(defaults) - set(also.model_fields))
    if unknown:
        raise PanglossMetaError(
            f"TypologyMeta(name={name!r}).defaults has fields that {also.__name__} does not: {', '.join(unknown)}"
        )
    values = dict(defaults)
    missing = []
    for field_name, info in also.model_fields.items():
        if field_name in ("type", "label") or field_name in values:
            continue
        if not info.is_required():
            continue
        if is_list(info.annotation):
            values[field_name] = []
        else:
            missing.append(field_name)
    if missing:
        raise PanglossMetaError(
            f"A {name} is also a {also.__name__}, which requires {', '.join(missing)}: give a value "
            f"for each in TypologyMeta(defaults={{...}})"
        )
    return values


def interface_meta() -> dict[str, Any]:
    """The pages of the interface module of this package (`pangloss_typology/interface/`) for the entity, if the interface
    is installed: the list as a tree, the item page with the hierarchy, and a card that marks a type; and the section of the navigation bar the types are listed under. They are used when
    `pangloss_typology` is in `INSTALLED_APPS`, which is where its module is found"""
    try:
        from pangloss_interface import InterfaceMeta
    except ImportError:
        return {}
    return {
        "_interface_meta": InterfaceMeta(
            nav_section="Typologies",
            list_page="pangloss_typology:TypeTree",
            item_page="pangloss_typology:TypeItem",
            view_card="pangloss_typology:TypeCard",
        )
    }


def make_entity(typology: type[Typology], meta: TypologyMeta) -> type[Entity]:
    """The entity of a typology, made as if it had been declared"""
    annotations: dict[str, Any] = {
        "description": "str | None",
        IS_SUBTYPE_OF: Annotated[
            list[meta.name],  # ty: ignore[invalid-type-form]
            RelationConfig(reverse_name=IS_SUPERTYPE_OF, validators=[MaxLen(1)]),
        ],
    }
    namespace: dict[str, Any] = {
        "__module__": typology.__module__,
        "__qualname__": meta.name,
        "__doc__": f"A type of {typology.__name__}",
        "__relation_names__": (HAS_TYPE, TYPE_OF),
        "__relation_names_except__": (IS_SUBTYPE_OF,),
        "__typology__": typology,
        "description": None,
        IS_SUBTYPE_OF: [],
    }
    protected = [IS_SUBTYPE_OF]
    base: type[Entity] = Entity
    if meta.also is not None:
        base = meta.also
        if meta.concrete == "per_type":
            annotations[IS_CONCRETE] = "bool | None"
            namespace[IS_CONCRETE] = None
            namespace["__labels_unmanaged__"] = unmanaged_labels(meta.also)
            protected.append(IS_CONCRETE)
    namespace["__annotations__"] = annotations
    namespace.update(interface_meta())
    if meta.also is not None:
        namespace["__typology_values__"] = values_for_also(
            meta.also, meta.defaults, meta.name
        )
    namespace["_protect_meta"] = Protection(read_only=tuple(protected))
    return type(base)(meta.name, (base,), namespace)


def complete_typologies() -> None:
    """Before the models are initialised: give each typology's entity the label of each language (`label_de`), which the
    settings say (so they are known only now)"""
    for typology in Typology.registry.values():
        entity = typology.Type
        if entity not in ModelRegistry._model_set:
            continue  # (made for an earlier set of models)
        for code in languages_of(typology._typology_meta):
            name = language_field(code)
            if name in entity.model_fields:
                continue
            entity.model_fields[name] = FieldInfo(annotation=str | None, default=None)
            entity.__annotations__[name] = str | None


ModelRegistry.before_finalise.append(complete_typologies)


def typology_of(entity: type) -> type[Typology] | None:
    """The typology that made an entity class, if one did"""
    return getattr(entity, "__typology__", None)
