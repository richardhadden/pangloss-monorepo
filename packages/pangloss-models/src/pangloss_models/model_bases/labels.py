"""The labels of the nodes the models are written as"""

from collections.abc import Iterable
from typing import TYPE_CHECKING

from pangloss_models.model_bases.fulfilment import get_fulfillable_models

if TYPE_CHECKING:
    from pangloss_models.model_bases.base_models import _DeclaredClass


def labels_for_model(owner: type[_DeclaredClass], metatype: str) -> list[str]:
    """The labels of the nodes of a model in the database: its name, those of its
    parents and traits, and its kind"""

    from pangloss_models.model_bases.trait import NonHeritableTrait, Trait
    from pangloss_models.utils import get_all_parent_classes, model_is_trait

    labels = [owner.__name__]

    parent_labels = []
    for c in get_all_parent_classes(owner):
        if not hasattr(c, "__pydantic_generic_metadata__"):
            continue  # (`Fulfils[...]`, and the like: not a model, so not a label)
        if (
            model_is_trait(c)
            and issubclass(c, NonHeritableTrait)
            and owner not in c.__subclasses__()
        ) or (
            c.__pydantic_generic_metadata__["parameters"] and not issubclass(c, Trait)
        ):
            pass
        else:
            parent_labels.append(c.__name__)
    labels.extend(parent_labels)
    labels.append(metatype)

    return labels


def get_labels_for_db_classes(self):
    """The labels of the node an instance is written as: those of its model and, for each class it
    fulfils (`Fulfils`, decided by what it holds: see `get_fulfilled_classes`), the labels of that
    class, before the kind"""
    labels = labels_for_model(self._owner, self.__metatype__)
    # (labels that something else puts on and takes off, `__labels_unmanaged__`: the typologies' `also`)
    unmanaged = getattr(self._owner, "__labels_unmanaged__", ())
    labels = [label for label in labels if label not in unmanaged]
    fulfilled = getattr(self, "_fulfils_classes", None)
    if not fulfilled:
        return labels
    kind = labels.pop()
    for fulfilled_class in fulfilled:
        for label in labels_for_model(fulfilled_class, fulfilled_class.__metatype__)[
            :-1
        ]:
            if label not in labels:
                labels.append(label)
    labels.append(kind)
    return labels


def fulfillable_labels(self) -> set[str]:
    """Every label that a class this instance could fulfil can give it (so that the labels of a
    node that no longer fulfils one can be taken off)"""
    found: set[str] = set()
    for fulfillable in get_fulfillable_models(self):
        found.update(labels_for_model(fulfillable, fulfillable.__metatype__))
    return found


def has_allowed_label(allowed_types: Iterable[str], node_labels: Iterable[str]) -> bool:
    """Whether a node with these labels is of one of the allowed types (the names a relation accepts: the class it goes to
    and its subclasses).

    A class can have labels that something else puts on and takes off (`__labels_unmanaged__`: a type that is also a
    `Role` only while it is switched on). It counts as one of the allowed types only if it has them, when the relation
    also accepts the class they come from (a relation to `Role` takes a `RoleType` that is a `Role`; a relation to
    `RoleType` takes any)."""
    from pangloss_models.model_registry import ModelRegistry

    allowed = set(allowed_types)
    labels = set(node_labels)
    models = ModelRegistry.all_models()
    for name in allowed & labels:
        unmanaged = getattr(models.get(name), "__labels_unmanaged__", ())
        if unmanaged and set(unmanaged) <= allowed and not set(unmanaged) <= labels:
            continue
        return True
    return False
