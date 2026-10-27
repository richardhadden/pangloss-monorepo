"""Which class a Zotero item type is written as. Nothing is guessed: a class says which types it stands for
(`_zotero_meta`), and a type that two classes claim needs one to be the `default`.

For a type no class claims, the `fallback` class is used, or `ZoteroObject`. Only the class that declares a
`_zotero_meta` counts as claiming (a subclass that inherits it does not: see `meta_slots.declared_slots`)."""

from dataclasses import dataclass, field

from pangloss_models.exceptions import PanglossMetaError
from pangloss_models.meta_slots import declared_slots
from pangloss_models.model_registry import ModelRegistry

from pangloss_zotero.item_types import SLOT, ZoteroMeta
from pangloss_zotero.models import ZoteroBacked, ZoteroObject


@dataclass
class TypeTable:
    by_type: dict[str, type[ZoteroBacked]] = field(default_factory=dict)
    fallback: type[ZoteroBacked] = ZoteroObject

    def class_for(self, item_type: str) -> type[ZoteroBacked]:
        return self.by_type.get(item_type, self.fallback)

    def describe(self) -> dict[str, str]:
        return {t: c.__name__ for t, c in sorted(self.by_type.items())}


def zotero_classes() -> list[type[ZoteroBacked]]:
    return [
        model
        for model in ModelRegistry.all_models().values()
        if isinstance(model, type) and issubclass(model, ZoteroBacked)
    ]


def concrete_classes() -> list[type[ZoteroBacked]]:
    return [m for m in zotero_classes() if not getattr(m._meta, "abstract", False)]


def build_table() -> TypeTable:
    """The table of the models there are now. Raises `PanglossMetaError` for a declaration that is wrong."""
    claims: dict[str, list[type[ZoteroBacked]]] = {}
    defaults: dict[str, list[type[ZoteroBacked]]] = {}
    fallbacks: list[type[ZoteroBacked]] = []

    for model in zotero_classes():
        if SLOT not in declared_slots(model):
            continue
        meta: ZoteroMeta = model.__dict__[SLOT]
        if getattr(model._meta, "abstract", False):
            raise PanglossMetaError(
                f"{model.__name__} is abstract, so it cannot stand for Zotero item types"
            )
        if model is ZoteroObject:
            continue
        if not (meta.item_types or meta.fallback):
            raise PanglossMetaError(
                f"{model.__name__}._zotero_meta says nothing: give item_types, or fallback=True"
            )
        for name in meta.type_names:
            claims.setdefault(name, []).append(model)
            if meta.default:
                defaults.setdefault(name, []).append(model)
        if meta.fallback:
            fallbacks.append(model)

    table = TypeTable()
    for name, models in sorted(claims.items()):
        chosen = defaults.get(name, [])
        if len(models) == 1:
            table.by_type[name] = models[0]
        elif len(chosen) == 1:
            table.by_type[name] = chosen[0]
        else:
            names = ", ".join(sorted(m.__name__ for m in models))
            how = (
                f"{len(chosen)} of them say default=True"
                if chosen
                else "none says default=True"
            )
            raise PanglossMetaError(
                f"Zotero item type {name!r} is claimed by {names}, and {how}: exactly one should"
            )
    if len(fallbacks) > 1:
        raise PanglossMetaError(
            "Only one class can be the Zotero fallback, but "
            + ", ".join(sorted(m.__name__ for m in fallbacks))
            + " say fallback=True"
        )
    if fallbacks:
        table.fallback = fallbacks[0]
    return table


def accepts(model: type[ZoteroBacked], item_type: str) -> bool:
    """Whether a class can be an item of this Zotero type (for linking a node made by hand to an item). A
    class that says nothing about Zotero types accepts any; one that does accepts those it names. A
    subclass is judged by the nearest declaration it inherits."""
    meta = getattr(model, SLOT, None)
    if meta is None or not meta.item_types:
        return True
    return item_type in meta.type_names
