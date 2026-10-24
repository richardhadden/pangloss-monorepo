"""The labels of the nodes the models are written as"""

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
