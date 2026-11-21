"""`_vectors_meta`: whether a class is a group that a search can be narrowed to, and whether its items have vectors.

    class Person(Entity):
        _vectors_meta = VectorsMeta(searchable=True)

    class Note(Document):
        _vectors_meta = VectorsMeta(include=False)

A subclass has its parent's setting unless it sets its own; a class with none anywhere is `VectorsMeta()`.

- `include=False`: the items of the class get no vectors at all (the store leaves out their rows), and so are never
  found by a search nor give one. The project's settings say it too, without the class's package knowing this one
  (`VECTORS_EXCLUDE`, `VECTORS_INCLUDE`): `included` has the rule, and its order.
- `searchable=True` (a document or entity class only, refused at `initialise()` on anything else): the class is a
  **group**. Every combined vector of an item of the class, or of a class below it, has the group's label as well, and
  each profile has a vector index of the group's own, so that "people like this one" searches people only. A group is
  a class that says `searchable=True` itself: a subclass that inherits the setting is in its parent's group, and is
  not a group of its own unless it says so too (a group of each subclass would be an index of each).

(implementation_docs/similarity-build-plan.md, step 2.2)
"""

import dataclasses
from typing import Any

from pangloss_models import (
    Document,
    Entity,
    ModelRegistry,
    PanglossMetaError,
    hooks,
    register_meta_slot,
)
from pangloss_models.exceptions import PanglossInitialisationError
from pangloss_models.meta_slots import declared_slots

from pangloss_vectors.settings import vectors_exclude, vectors_include

SLOT = "_vectors_meta"


@dataclasses.dataclass(frozen=True)
class VectorsMeta:
    searchable: bool = False
    """Whether the class is a group a search can be narrowed to (a vector index of its own, for each profile)"""

    include: bool = True
    """Whether the items of the class have vectors"""


register_meta_slot(SLOT, VectorsMeta)

DEFAULT = VectorsMeta()


def vectors_meta(model: type) -> VectorsMeta:
    """The class's setting, its parent's, or the default"""
    meta = getattr(model, SLOT, None)
    return meta if isinstance(meta, VectorsMeta) else DEFAULT


def is_group(model: type) -> bool:
    """Whether the class says `searchable=True` itself"""
    return (
        SLOT in declared_slots(model)
        and vectors_meta(model).searchable
        and issubclass(model, (Document, Entity))
    )


def model_named(type_name: str) -> type | None:
    return ModelRegistry._model_dict.get(type_name)


def _names_above(model: type) -> set[str]:
    """The names of the class and of each registered class above it"""
    return {
        cls.__name__
        for cls in model.__mro__
        if ModelRegistry._model_dict.get(cls.__name__) is cls
    }


def stand_in_documents() -> list[type]:
    """The document classes that stand in for an entity (`hooks.stand_ins` that name a declared `Document` class: a
    generic wrapper, `MatchesCriteria`, is never an item)"""
    from pangloss_models.initialise_models.initialise_field_definitions import (
        is_generic_stand_in,
    )

    found = []
    for stand_in in hooks.stand_ins:
        document = model_named(stand_in.document)
        if (
            isinstance(document, type)
            and issubclass(document, Document)
            and not is_generic_stand_in(document)
        ):
            found.append(document)
    return found


def model_included(model: type, settings: Any = None) -> bool:
    """Whether the items of the class have vectors. In this order, the first that says:

    1. the class, or a class above it, is named in `VECTORS_EXCLUDE`: no (the project's last word);
    2. the class or a class above it sets `_vectors_meta` (the nearest): its `include`;
    3. the class is a stand-in's document (`hooks.stand_ins`), or below one: no, unless it or a class above it is
       named in `VECTORS_INCLUDE`;
    4. yes."""
    above = _names_above(model)
    if above & set(vectors_exclude(settings)):
        return False
    own = getattr(model, SLOT, None)
    if isinstance(own, VectorsMeta):
        return own.include
    if any(issubclass(model, document) for document in stand_in_documents()):
        return bool(above & set(vectors_include(settings)))
    return True


def included(type_name: str) -> bool:
    """Whether items of the class of this name have vectors (`model_included`; a name that is no model's has: what to
    make of it is the part's business)"""
    model = model_named(type_name)
    return model is None or model_included(model)


def excluded() -> list[str]:
    """The registered classes of documents and entities whose items have no vectors, in the order of their names:
    part of what a rebuild depends on (`store.part_signature`), and what a search leaves out"""
    return sorted(
        name
        for name, model in ModelRegistry._model_dict.items()
        if isinstance(model, type)
        and issubclass(model, (Document, Entity))
        and not model_included(model)
    )


def check_settings(settings: Any = None) -> None:
    """(`pangloss_vectors.check_profiles`, at `initialise()`) `VECTORS_EXCLUDE` and `VECTORS_INCLUDE` name classes
    of documents or entities, and no class is named in both"""
    exclude, include = vectors_exclude(settings), vectors_include(settings)
    for setting, names in (("VECTORS_EXCLUDE", exclude), ("VECTORS_INCLUDE", include)):
        for name in names:
            model = model_named(name)
            if model is None:
                raise PanglossInitialisationError(
                    f"{setting} names {name!r}, which is no model's: it names classes of documents or entities"
                )
            if not (isinstance(model, type) and issubclass(model, (Document, Entity))):
                raise PanglossInitialisationError(
                    f"{setting} names {name!r}, which is not a class of documents or entities: only their items "
                    "have vectors"
                )
    both = sorted(set(exclude) & set(include))
    if both:
        raise PanglossInitialisationError(
            f"{', '.join(repr(name) for name in both)} is named in both VECTORS_EXCLUDE and VECTORS_INCLUDE: say "
            "whether its items have vectors in one of them"
        )


def groups_of(type_name: str) -> list[str]:
    """The groups an item of the class of this name is in: the class and each class above it that is a group, in the
    order of their names"""
    model = model_named(type_name)
    if model is None:
        return []
    return sorted(
        {
            cls.__name__
            for cls in model.__mro__
            if ModelRegistry._model_dict.get(cls.__name__) is cls and is_group(cls)
        }
    )


def groups() -> list[str]:
    """Every group of the registered models, in the order of their names"""
    return sorted(
        name for name, model in ModelRegistry._model_dict.items() if is_group(model)
    )


def check_searchable() -> None:
    """(`ModelRegistry.before_finalise`) `searchable=True` is for a class of documents or entities: anything else
    (an embedded object, a reified relation) is never an item a search gives"""
    for name, model in ModelRegistry._model_dict.items():
        if (
            SLOT in declared_slots(model)
            and vectors_meta(model).searchable
            and not issubclass(model, (Document, Entity))
        ):
            raise PanglossMetaError(
                f"{name}: VectorsMeta(searchable=True) is for a class of documents or entities, which are what a "
                "search finds; this class is neither"
            )


def install() -> None:
    if check_searchable not in ModelRegistry.before_finalise:
        ModelRegistry.before_finalise.append(check_searchable)


# (done as soon as a model can say it, whether or not the app is installed)
install()
