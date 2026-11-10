"""`InterfaceMeta`: what the interface is told about a model, on the class (the meta slot
`_interface_meta`, see implementation_docs/meta-slots.md):

    class Negative[T](SemanticSpace[T]):
        _interface_meta = InterfaceMeta(colour="rose")

A subclass that sets none has its parent's.
"""

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, get_args

from pangloss_models import Entity, PanglossMetaError, included_only_when_referenced

# The base colours of Tailwind, except black and white. (The interface has the same list in
# `interface-core/src/types/models.ts`; a test holds the two together.)
Colour = Literal[
    "slate",
    "gray",
    "zinc",
    "neutral",
    "stone",
    "mauve",
    "olive",
    "mist",
    "taupe",
    "red",
    "orange",
    "amber",
    "yellow",
    "lime",
    "green",
    "emerald",
    "teal",
    "cyan",
    "sky",
    "blue",
    "indigo",
    "violet",
    "purple",
    "fuchsia",
    "pink",
    "rose",
]
COLOURS: tuple[str, ...] = get_args(Colour)


# Where the interface finds a component for a model: "<app>:<name>", the name of an installed app and
# a key of `components` in the manifest of its interface module (implementation_docs/interface-modules-implementation.md)
ComponentRef = str
COMPONENT_REF = re.compile(r"^([A-Za-z_]\w*):([A-Za-z_]\w*)$")
# (`False` turns off one that a parent model names: the generic page or card is used again)
Slot = ComponentRef | Literal[False] | None
SLOTS = ("list_page", "item_page", "view_card", "edit_card")
# (the kinds of model that can be shown folded into what they hold)
COLLAPSIBLE_KINDS = ("ReifiedRelation", "Conjunction")


# (what `Collapse(when=...)` can compare a field with: a plain value, or a member of an enum, by its value)
CollapseValue = str | int | float | bool | Enum | None
IDENTIFIER = re.compile(r"^[A-Za-z_]\w*$")


def _listed(
    values: CollapseValue | Sequence[CollapseValue],
) -> tuple[CollapseValue, ...]:
    # (a single value is a list of one)
    if isinstance(values, Sequence) and not isinstance(values, str):
        return tuple(values)
    return (values,)


@dataclass(frozen=True)
class Collapse:
    """Conditions on top of the built-in rule of `InterfaceMeta(collapse=True)`, by the names of the
    model's fields (implementation_docs/interface-features.md):

        _interface_meta = InterfaceMeta(
            collapse=Collapse(blocking=["certainty"], hidden=["note"], when={"role": ["author"]})
        )
    """

    # These, filled, show it whole
    blocking: Sequence[str] = ()
    # These are not shown beside what it holds when it is folded (and do not stop it, whatever they hold)
    hidden: Sequence[str] = ()
    # Each of these must hold one of its values (a single value is a list of one; None for an empty field)
    when: Mapping[str, CollapseValue | Sequence[CollapseValue]] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        for name in ("blocking", "hidden"):
            given = getattr(self, name)
            if isinstance(given, str) or not all(
                isinstance(key, str) and IDENTIFIER.match(key) for key in given
            ):
                raise PanglossMetaError(
                    f"Collapse({name}={given!r}): a list of the names of fields"
                )
            object.__setattr__(self, name, tuple(given))
        when: dict[str, tuple[CollapseValue, ...]] = {}
        for key, values in dict(self.when).items():
            if not isinstance(key, str) or not IDENTIFIER.match(key):
                raise PanglossMetaError(
                    f"Collapse(when=...): {key!r} is not the name of a field"
                )
            listed = _listed(values)
            if not listed or not all(
                value is None or isinstance(value, (str, int, float, bool, Enum))
                for value in listed
            ):
                raise PanglossMetaError(
                    f"Collapse(when={{{key!r}: {values!r}}}): one or more values (text, numbers, yes/no, "
                    "members of an enum, None)"
                )
            when[key] = listed
        object.__setattr__(self, "when", when)

    def names(self) -> set[str]:
        return {*self.blocking, *self.hidden, *self.when}

    def export(self, keys: Mapping[str, str]) -> dict[str, Any]:
        """By the keys of the fields (`keys`: name to key), enum members by their values"""
        return {
            "blocking": [keys[name] for name in self.blocking],
            "hidden": [keys[name] for name in self.hidden],
            "when": {
                keys[name]: [
                    v.value if isinstance(v, Enum) else v for v in _listed(values)
                ]
                for name, values in self.when.items()
            },
        }


@dataclass(frozen=True)
class InterfaceMeta:
    """How the interface shows a model. A field that is not set (None) is the parent's; `False`
    turns off a component that a parent names."""

    # The colour of the model's type wherever it is shown, and of the band round an item in a
    # semantic space. Without one: blue for entities, green for documents, and for a semantic
    # space a colour by how deep it is.
    colour: Colour | None = None
    # The section of the navigation bar the type is listed under, instead of Entities or Documents (a
    # subclass has its parent's). An app's `NavModel` for the type, in its `InterfaceConfig`, still wins.
    # The title is translated by the slot `nav_section_<title in snake case>` in `ui.jsonc`
    nav_section: str | None = None
    # A component of an interface module, for the whole page of the list of the type
    list_page: Slot = None
    # ... for the whole page of one item
    item_page: Slot = None
    # ... for a card that shows an item where it is part of something else (a result in a list,
    # a reference, an embedded item)
    view_card: Slot = None
    # ... for a card (a form) that edits an item
    edit_card: Slot = None
    # (a ReifiedRelation or a Conjunction only) Whether the item page shows it folded into the one thing it
    # holds, when it holds only one: `True` by the built-in rule, `Collapse(...)` by the built-in rule with
    # conditions on its fields, "<app>:<name>" by a rule (a TypeScript function) in `collapseRules` of an
    # interface module. View only (implementation_docs/interface-features.md)
    collapse: bool | Collapse | ComponentRef | None = None
    # (a ReifiedRelation only) Shown without its head bar, as only what it holds and its own fields, where it
    # is the only thing a field can hold and the field holds one of it, and must: its type says nothing
    # there, and it is never added or removed. In the view and the form
    headless: bool | None = None
    # Fields the forms of the model do not show (the item's page still does; what a form loaded of them is sent back
    # as it was): their names, or a function of the class (a subclass's own, when it is exported) that gives them, for
    # a package whose fields matter to some of the classes built on its base. `()` turns off the parent's
    hide_on_forms: Sequence[str] | Callable[[type], Iterable[str]] | None = None
    # (an Entity only) The list page of the type shows, at first, only the items that something refers to, with a button
    # beside the search for all of them, and each item says how many things refer to it. Unset, what the class's
    # `Usage(include_only_when_referenced=...)` says. True, False to turn off
    # the parent's, or a function of the class (a subclass's own, when it is exported)
    list_used_only: bool | Callable[[type], bool] | None = None

    @staticmethod
    def editor_choices(option: str) -> list[str] | None:
        """What the language server offers for an option: the components, or rules, that the interface modules of the
        installed apps declare (`pangloss_models.editor_schema`)"""
        block = (
            "components"
            if option in SLOTS
            else "collapseRules"
            if option == "collapse"
            else None
        )
        if block is None:
            return None
        from pangloss_core import settings as core_settings

        from pangloss_interface.modules import declared_names, discover

        settings = getattr(core_settings, "SETTINGS", None)
        if settings is None:
            return None
        try:
            return [
                name
                for module in discover(settings.INSTALLED_APPS)
                for name in declared_names(module, block)
            ]
        except OSError:
            return None

    def __post_init__(self) -> None:
        if self.colour is not None and self.colour not in COLOURS:
            raise PanglossMetaError(
                f"InterfaceMeta(colour={self.colour!r}): the colour must be one of Tailwind's base colours "
                f"(not black or white): {', '.join(COLOURS)}"
            )
        if self.nav_section is not None and not self.nav_section.strip():
            raise PanglossMetaError(
                "InterfaceMeta(nav_section=...): the title of a section cannot be empty"
            )
        for slot in SLOTS:
            value = getattr(self, slot)
            if value is None or value is False:
                continue
            if not isinstance(value, str) or not COMPONENT_REF.match(value):
                raise PanglossMetaError(
                    f"InterfaceMeta({slot}={value!r}): a component is named '<app>:<Name>' "
                    "(an installed app, and a key of 'components' in its interface module), or False "
                    "to turn off the parent's"
                )
        if not (
            self.hide_on_forms is None
            or callable(self.hide_on_forms)
            or (
                not isinstance(self.hide_on_forms, str)
                and all(isinstance(name, str) for name in self.hide_on_forms)
            )
        ):
            raise PanglossMetaError(
                f"InterfaceMeta(hide_on_forms={self.hide_on_forms!r}): the names of fields, or a function of the "
                "class that gives them"
            )
        if not (
            self.list_used_only is None
            or isinstance(self.list_used_only, bool)
            or callable(self.list_used_only)
        ):
            raise PanglossMetaError(
                f"InterfaceMeta(list_used_only={self.list_used_only!r}): True, False to turn off the parent's, or a "
                "function of the class"
            )
        if self.headless is not None and not isinstance(self.headless, bool):
            raise PanglossMetaError(
                f"InterfaceMeta(headless={self.headless!r}): True, or False to turn off the parent's"
            )
        if self.collapse is not None and not isinstance(
            self.collapse, (bool, Collapse)
        ):
            if not isinstance(self.collapse, str) or not COMPONENT_REF.match(
                self.collapse
            ):
                raise PanglossMetaError(
                    f"InterfaceMeta(collapse={self.collapse!r}): True for the built-in rule, Collapse(...) for it "
                    "with conditions, '<app>:<name>' "
                    "for a rule in 'collapseRules' of an app's interface module, or False to turn off the parent's"
                )


def split_reference(reference: str) -> dict[str, str]:
    app, name = reference.split(":")
    return {"module": app, "name": name}


def resolved_meta(model: type) -> dict[str, Any] | None:
    """The `InterfaceMeta` of a class, field by field: each from the nearest class (the class
    itself, then its parents) that sets it. None if no class sets any."""
    metas = [
        meta
        for klass in model.__mro__
        if isinstance(meta := klass.__dict__.get("_interface_meta"), InterfaceMeta)
    ]
    if not metas:
        # (a slot that is not in `__dict__`, as an older class has it)
        meta = getattr(model, "_interface_meta", None)
        metas = [meta] if isinstance(meta, InterfaceMeta) else []
    usage = issubclass(model, Entity) and included_only_when_referenced(model)
    if not metas and not usage:
        return None
    resolved: dict[str, Any] = {
        "colour": next((m.colour for m in metas if m.colour is not None), None),
        "navSection": next(
            (m.nav_section for m in metas if m.nav_section is not None), None
        ),
    }
    for slot in SLOTS:
        value = next((v for m in metas if (v := getattr(m, slot)) is not None), None)
        resolved[_camel(slot)] = (
            split_reference(value) if isinstance(value, str) else None
        )
    collapse = next((m.collapse for m in metas if m.collapse is not None), None)
    # (`Collapse(...)` is exported by `export_definitions`, which knows the keys of the fields)
    resolved["collapse"] = (
        split_reference(collapse)
        if isinstance(collapse, str)
        else collapse
        if isinstance(collapse, Collapse)
        else (True if collapse is True else None)
    )
    headless = next((m.headless for m in metas if m.headless is not None), None)
    resolved["headless"] = True if headless else None
    # (by name: `export_definitions` gives the keys, and checks the names)
    hidden = next((m.hide_on_forms for m in metas if m.hide_on_forms is not None), None)
    names = list(hidden(model) if callable(hidden) else hidden or [])
    resolved["hideOnForms"] = names or None
    used = next((m.list_used_only for m in metas if m.list_used_only is not None), None)
    # (what the class says of itself, unless the interface was told otherwise)
    used = usage if used is None else used
    resolved["listUsedOnly"] = (
        True if (used(model) if callable(used) else used) else None
    )
    return resolved


def _camel(name: str) -> str:
    first, *rest = name.split("_")
    return first + "".join(word.title() for word in rest)


def export_definitions() -> dict[str, Any]:
    """`export_models()`, with the `interfaceMeta` of each model: `{"colour": ..., "listPage": {"module",
    "name"} or None, ...}`, resolved through the parents, or None for a model with none; `readOnly` on each field
    (something other than a person keeps it up to date: `Protection`, which the API enforces); the `nav`; and the
    `searchPatterns` (`export_search_patterns`). (Not in `export_models()` itself: the migrations' snapshots are
    made from that, and what a form may edit is not a change to the models.)"""
    from pangloss_models import ModelRegistry, export_models, protection_of

    exported = export_models()
    classes = {
        model.__name__: model
        for model in ModelRegistry._models
        if not (getattr(model, "__pydantic_generic_metadata__", None) or {}).get(
            "origin"
        )
    }
    from pangloss_core import settings as core_settings

    from pangloss_interface.config import export_disabled, export_nav

    settings = core_settings.__dict__.get("SETTINGS")
    apps = getattr(settings, "INSTALLED_APPS", [])
    exported["projectName"] = getattr(settings, "PROJECT_NAME", None)
    exported["nav"] = export_nav(apps, exported["models"])
    exported["disabled"] = export_disabled(apps)
    # (the search patterns of the models: the interface's types of them, `LetterWhere`)
    from pangloss_models.search_where import export_search_patterns

    exported["searchPatterns"] = export_search_patterns(classes.values())
    for name, definition in exported["models"].items():
        cls = classes.get(name)
        protected = () if cls is None else protection_of(cls).read_only
        for exported_field in definition["fields"]:
            exported_field["readOnly"] = exported_field["name"] in protected
        meta = definition["interfaceMeta"] = None if cls is None else resolved_meta(cls)
        if meta and meta["collapse"]:
            if definition["kind"] not in COLLAPSIBLE_KINDS:
                raise PanglossMetaError(
                    f"{name}: InterfaceMeta(collapse=...) is for a ReifiedRelation or a Conjunction, and this is "
                    f"a {definition['kind']}"
                )
            if isinstance(meta["collapse"], Collapse):
                meta["collapse"] = _export_collapse(name, definition, meta["collapse"])
        if meta and meta["hideOnForms"]:
            meta["hideOnForms"] = _export_hidden(name, definition, meta["hideOnForms"])
        if meta and meta["listUsedOnly"] and definition["kind"] != "Entity":
            raise PanglossMetaError(
                f"{name}: InterfaceMeta(list_used_only=...) is for an Entity, and this is a {definition['kind']}"
            )
        if meta and meta["headless"] and definition["kind"] != "ReifiedRelation":
            raise PanglossMetaError(
                f"{name}: InterfaceMeta(headless=True) is for a ReifiedRelation, and this is a {definition['kind']}"
            )
    return exported


def _export_hidden(
    name: str, definition: dict[str, Any], names: list[str]
) -> list[str]:
    """`hide_on_forms` by the keys of the fields; raises if it names a field the model does not have"""
    keys = {f["name"]: f["key"] for f in definition["fields"]}
    wrong = sorted(set(names) - set(keys))
    if wrong:
        raise PanglossMetaError(
            f"{name}: InterfaceMeta(hide_on_forms=...) names {', '.join(wrong)}, which is not one of its fields"
        )
    return [keys[n] for n in names]


def _export_collapse(
    name: str, definition: dict[str, Any], rule: Collapse
) -> dict[str, Any]:
    """`Collapse(...)` by the keys of the fields; raises if it names a field the model does not have, or the
    one that holds what it folds into"""
    fields = definition["fields"]
    if definition["kind"] == "ReifiedRelation":
        held = {"target"}
    else:
        held = {f["name"] for f in fields if f["kind"] == "relation"}
    keys = {f["name"]: f["key"] for f in fields if f["name"] not in held}
    wrong = sorted(rule.names() - set(keys))
    if wrong:
        raise PanglossMetaError(
            f"{name}: Collapse(...) names {', '.join(wrong)}, which is not one of its own fields "
            f"({', '.join(keys) or 'none'}; not what it holds)"
        )
    return rule.export(keys)
