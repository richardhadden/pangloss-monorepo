"""Fields that something other than a person keeps up to date, and entities that cannot be deleted by hand.

    class ZoteroBacked(Entity):
        _protect_meta = Protection(read_only=("zotero_key", "citation"), delete_only_if="removed_from_zotero")

The **API** refuses a request that changes a protected field (or creates a model with one set), and a delete
of a model whose `delete_only_if` field is not true, or that its `delete_refused` gives a reason against. Code
that writes through Python (`Model.Create(...).save()`) is not stopped: it is trusted. A subclass adds to the
protection of its parents (the fields are the union; the nearest `delete_only_if` and `delete_refused` win),
where a meta slot would otherwise replace it.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pangloss_models.meta_slots import declared_slots, register_meta_slot

SLOT = "_protect_meta"


@dataclass(frozen=True)
class Protection:
    read_only: tuple[str, ...] = ()
    """Fields that a request may not change from what is stored (nor set when creating)"""
    delete_only_if: str | None = None
    """The name of a field that must be true for the API to delete the model"""
    delete_refused: Callable[[type, Any], Awaitable[str | None]] | None = None
    """Asked by the API before it deletes one (the model and the id): the reason it cannot be deleted, or `None`. For
    a package whose own rule is stricter than an entity's (a type of a typology that is in use is not marked for
    deletion, as an entity that is referred to would be: it is refused, and nothing is changed)"""


register_meta_slot(SLOT, Protection)


def protection_of(model: type) -> Protection:
    """What protects a model: its own and its parents', put together"""
    fields: list[str] = []
    delete_only_if: str | None = None
    delete_refused = None
    for cls in model.__mro__:
        if SLOT not in declared_slots(cls):
            continue
        own: Protection = cls.__dict__[SLOT]
        fields.extend(name for name in own.read_only if name not in fields)
        if delete_only_if is None:
            delete_only_if = own.delete_only_if
        if delete_refused is None:
            delete_refused = own.delete_refused
    return Protection(tuple(fields), delete_only_if, delete_refused)


def changed_fields(model: type, body: Any, stored: Any | None) -> list[str]:
    """The protected fields that `body` (a Create or Update) changes. `stored` is what is there now (None
    for a creation: the field may not be set at all)"""
    changed = []
    for name in protection_of(model).read_only:
        value = getattr(body, name, None)
        if stored is None:
            field = type(body).model_fields.get(name)
            default = field.get_default(call_default_factory=True) if field else None
            if value not in (None, default, [], {}):
                changed.append(name)
        elif value != getattr(stored, name, None):
            changed.append(name)
    return changed
