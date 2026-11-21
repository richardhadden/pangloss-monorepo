"""`_vectors_meta`: whether a class is a group that a search can be narrowed to, and whether its items have vectors.

    class Person(Entity):
        _vectors_meta = VectorsMeta(searchable=True)

    class Note(Document):
        _vectors_meta = VectorsMeta(include=False)

A subclass has its parent's setting unless it sets its own; a class with none anywhere is `VectorsMeta()`.

- `include=False`: the items of the class get no vectors at all (the store leaves out their rows), and so are never
  found by a search nor give one.
- `searchable=True` (a document or entity class only, refused at `initialise()` on anything else): the class is a
  **group**. Every combined vector of an item of the class, or of a class below it, has the group's label as well, and
  each profile has a vector index of the group's own, so that "people like this one" searches people only. A group is
  a class that says `searchable=True` itself: a subclass that inherits the setting is in its parent's group, and is
  not a group of its own unless it says so too (a group of each subclass would be an index of each).

(implementation_docs/similarity-build-plan.md, step 2.2)
"""

import dataclasses

from pangloss_models import (
    Document,
    Entity,
    ModelRegistry,
    PanglossMetaError,
    register_meta_slot,
)
from pangloss_models.meta_slots import declared_slots

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


def included(type_name: str) -> bool:
    """Whether items of the class of this name have vectors (a name that is no model's has: what to make of it is the
    part's business)"""
    model = model_named(type_name)
    return model is None or vectors_meta(model).include


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
