"""Which models a migration could have made unreadable: what is worth reading afterwards.

Adding a model, an optional field or an enum member changes nothing that exists, so there is
nothing to read. A change to what exists can break the reading of:

- the models it names (and their subclasses, which have their fields and labels);
- the models that **contain** them: a Document is read with the Documents nested in it, its
  embedded objects, reified relations, semantic spaces and conjunctions in full;
- the entities on the other end of a relation that changed: an entity is read with the documents
  that refer to it (and chains of reified relations), so if `Statement.person` changes, `Person`
  is read differently;
- the models that use an enum which changed.

`affected_models(changes, snapshot)` gives their names (all that are models in the snapshot, not
only those that can be read on their own; `check_data` reads those that can).
"""

import json
from collections.abc import Iterable
from typing import Any

from pangloss_models.migrations import changes as c

# Changes to the models, or to what the data says, that nothing existing is made to disagree with
NO_EFFECT = (
    c.CreateModel,
    c.CreateEnum,
    c.AddEnumMember,
    c.RenameEnumMember,  # (the values are the same)
    c.RenameEnum,  # (nothing is stored of the name)
    c.RemoveEnum,
    c.RecomputeFulfils,  # (labels only: the data is read by the model of its `type`)
    c.AlterModelOption,
    c.AlterAnnotatedValue,
    c.AddIndex,
    c.RemoveIndex,
    c.AddConstraint,
    c.RemoveConstraint,
    c.DeleteModel,  # (what refers to it has changed in its own right)
)
OWNED_KINDS = {"reifiedRelation", "reifiedRelationDocument", "semanticSpace", "conjunction", "document"}


def model_names_in(options: Iterable[dict[str, Any]], owned_only: bool = False) -> set[str]:
    """The models an option list leads to (itself, and through the parameters of a wrapper)"""
    names: set[str] = set()
    for option in options:
        kind = option.get("kind")
        if kind in ("document", "entity"):
            if not owned_only or kind in OWNED_KINDS:
                names.add(option["type"])
        elif kind in OWNED_KINDS or kind == "unknown":
            if option.get("type"):
                names.add(option["type"])
            for parameter in option.get("params", {}).values():
                names |= model_names_in(parameter["options"], owned_only)
    return names


def entity_targets(options: Iterable[dict[str, Any]], snapshot: dict[str, Any]) -> set[str]:
    """The entities a relation is to (directly, or in the parameters of a wrapper)"""
    found: set[str] = set()
    for option in options:
        if option.get("kind") == "entity":
            found.add(option["type"])
        for parameter in option.get("params", {}).values():
            found |= entity_targets(parameter["options"], snapshot)
    return found


def owned_by(field: dict[str, Any]) -> set[str]:
    """The models a field holds in the node that has it (not those it only refers to)"""
    if field["kind"] == "embedded":
        return set(field.get("types", [])) | ({field["model"]} if field.get("model") else set())
    if field["kind"] == "annotatedValue":
        return {field["model"]} if field.get("model") else set()
    if field["kind"] == "relation":
        owned: set[str] = set()
        for option in field.get("options", []):
            if option.get("kind") in OWNED_KINDS:
                owned.add(option["type"])
                for parameter in option.get("params", {}).values():
                    owned |= {
                        o["type"] for o in parameter["options"] if o.get("kind") in OWNED_KINDS
                    }
        return owned
    return set()


def enums_in(field: dict[str, Any]) -> set[str]:
    text = json.dumps({k: v for k, v in field.items() if k in ("type", "item", "valueType")})
    found = set()
    pending = [json.loads(text)]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            if item.get("type") == "enum":
                found.add(item["enum"])
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return found


def adds_nothing_unreadable(change: c.Change) -> bool:
    """An added field that every node can do without: optional, or a list"""
    if not isinstance(change, c.AddField):
        return False
    if change.from_narrowing:
        return True
    kind = change.definition.get("kind")
    if kind in ("literal", "list", "annotatedValue", "typeVar"):
        return not change.needs_value  # (a required one is given a value, which is worth reading)
    if kind == "relation":
        return bool(change.definition.get("many"))
    return False  # (an embedded object, or a single relation, is needed)


def named_by(change: c.Change) -> set[str]:
    names: set[str] = set()
    for attribute in ("model", "new"):
        value = getattr(change, attribute, None)
        if isinstance(value, str) and (attribute == "model" or isinstance(change, c.RenameModel)):
            names.add(value)
    return names


def affected_models(changes: Iterable[c.Change], snapshot: dict[str, Any]) -> set[str]:
    """The models to read after the changes; `snapshot` is the state they leave"""
    models: dict[str, Any] = snapshot["models"]
    touched: set[str] = set()
    entity_roots: set[str] = set()  # (entities read through a relation that changed)
    changed_enums: set[str] = set()

    expanded: list[c.Change] = []
    for change in changes:
        if isinstance(change, c.StateOnly):
            expanded.extend(change.changes)  # (the data was moved by hand, but is worth reading)
        elif isinstance(change, (c.RunCypher, c.RunPython)):
            # (by hand: it may have changed anything, unless it says what)
            touched |= set(models) if change.affects is None else set(change.affects)
        else:
            expanded.append(change)

    for change in expanded:
        if isinstance(change, (c.RemoveEnumMember, c.AlterEnumMemberValue)):
            changed_enums.add(change.enum)
            continue
        if isinstance(change, NO_EFFECT) or adds_nothing_unreadable(change):
            continue
        names = named_by(change)
        touched |= names
        if isinstance(change, c.AddField):
            continue  # (what a new relation is to only gets a reverse relation, empty)
        for name in names:
            model = models.get(name)
            if not model:
                continue
            field_name = getattr(change, "name", None)
            fields = [f for f in model["fields"] if f["name"] == field_name] or (
                model["fields"] if not field_name or isinstance(change, (c.RenameModel, c.AlterModelLabels, c.AlterModelKind)) else []
            )
            for entry in fields:
                if entry["kind"] == "relation":
                    entity_roots |= entity_targets(entry.get("options", []), snapshot)

    # the models that use an enum that changed
    for name, model in models.items():
        if any(enums_in(f) & changed_enums for f in model["fields"]):
            touched.add(name)

    # subclasses have what their parents have (labels, fields)
    for name, model in models.items():
        if set(model.get("labels", [])) & touched:
            touched.add(name)

    # the models that hold them, and what they refer to
    affected = set(touched)
    pending = list(touched)
    while pending:
        inner = pending.pop()
        for name, model in models.items():
            if name in affected:
                continue
            for entry in model["fields"]:
                if inner in owned_by(entry):
                    affected.add(name)
                    pending.append(name)
                    entity_roots |= entity_targets(entry.get("options", []), snapshot)
                    break

    affected |= {n for n in entity_roots if n in models}
    # (and their subclasses)
    for name, model in models.items():
        if set(model.get("labels", [])) & affected:
            affected.add(name)
    return {name for name in affected if name in models}
