"""Meta slots: settings that an optional package keeps on a model class, next to `_meta`.

    register_meta_slot("_interface_meta", InterfaceMeta)

    class Person(Entity):
        _interface_meta = InterfaceMeta(card="PersonCard")

`Person._interface_meta` is then the object. A subclass that sets none has its parent's, one that sets its own
replaces it, and a class with none anywhere has `None`. Which classes set a slot *themselves* is kept too
(`declared_slots`), for a slot where only the class that says it counts and not the ones that inherit it.

Pydantic turns an unannotated `_name = value` into a private attribute and removes it from the class, so the
value is taken from `__private_attributes__` and put back as a plain class attribute (see docs/meta-slots.md).
"""

from typing import TYPE_CHECKING, Any

from pangloss_models.exceptions import PanglossMetaError

if TYPE_CHECKING:
    from pangloss_models.model_bases.base_models import _DeclaredClass

_slots: dict[str, type] = {}

OWN = "__own_meta_slots__"


def register_meta_slot(name: str, meta_class: type) -> None:
    """Say that `name` on a model class holds an instance of `meta_class`. Applies the slot to the models that
    were declared already, so the order of imports does not matter."""
    if not (name.startswith("_") and name.endswith("_meta") and name != "_meta"):
        raise PanglossMetaError(
            f"{name!r} cannot be a meta slot: it must start with an underscore and end with '_meta' "
            "(and not be '_meta' itself)"
        )
    taken = _slots.get(name)
    if taken is not None and taken is not meta_class:
        raise PanglossMetaError(
            f"The meta slot {name!r} is already used for {taken.__module__}.{taken.__qualname__}"
        )
    _slots[name] = meta_class

    from pangloss_models.model_registry import ModelRegistry

    for model in list(ModelRegistry._models):
        apply_meta_slot(model, name, meta_class)


def meta_slots() -> dict[str, type]:
    return dict(_slots)


def declared_slots(cls: type) -> frozenset[str]:
    """The slots the class sets in its own body (not those it inherits)"""
    return cls.__dict__.get(OWN, frozenset())


def _own_value(cls: type, name: str) -> tuple[bool, Any]:
    """(whether the class set the slot itself, its value). A private attribute that is the one of a parent
    is inherited."""
    private = getattr(cls, "__private_attributes__", {}).get(name)
    if private is None:
        return False, None
    for base in cls.__bases__:
        if getattr(base, "__private_attributes__", {}).get(name) is private:
            return False, None
    return True, private.default


def _inherited_value(cls: type, name: str) -> Any:
    for parent in cls.__mro__[1:]:
        if name in parent.__dict__:
            return parent.__dict__[name]
    return None


def apply_meta_slot(cls: type, name: str, meta_class: type) -> None:
    own, value = _own_value(cls, name)
    if own:
        if not isinstance(value, meta_class):
            raise PanglossMetaError(
                f"{cls.__name__}.{name} must be a {meta_class.__qualname__}, not {value!r}"
            )
    else:
        value = _inherited_value(cls, name)
    setattr(cls, name, value)
    if own:
        setattr(cls, OWN, declared_slots(cls) | {name})
    elif OWN not in cls.__dict__:
        setattr(cls, OWN, frozenset())


def apply_meta_slots(cls: type[_DeclaredClass]) -> None:
    """Set every registered slot on a class that has just been declared"""
    if OWN not in cls.__dict__:
        setattr(cls, OWN, frozenset())
    for name, meta_class in _slots.items():
        apply_meta_slot(cls, name, meta_class)
