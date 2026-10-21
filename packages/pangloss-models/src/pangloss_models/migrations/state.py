"""Applying changes to a snapshot: what the models are after a change.

`replay(old, changes)` is the snapshot after the changes, and for the changes that
`diff(old, new)` finds it is `new` (as far as the snapshot is of what is stored: see
`data_view`). That is what lets a migration be checked against the models, and the state
before any migration be had without the classes of that time.

This is all about the snapshot; what a change does to a database is the business of the
database package (`pangloss_memgraph.databases.memgraph.migrations`).
"""

import copy
from collections.abc import Callable, Iterable
from typing import Any

from pydantic.alias_generators import to_camel

from pangloss_models.migrations import changes as c
from pangloss_models.migrations.snapshot import data_view


def replay(old: dict[str, Any], changes: Iterable[c.Change]) -> dict[str, Any]:
    """The snapshot (as `data_view` has it) after applying the changes to `old`"""
    snapshot = data_view(old)
    for change in changes:
        snapshot = apply_change(snapshot, change)
    # (in the order that `data_view` puts things in, which the order of declaration is not)
    return data_view(snapshot)


def apply_change(snapshot: dict[str, Any], change: c.Change) -> dict[str, Any]:
    """The snapshot after one change. (The snapshot given is not changed.)"""
    handler = HANDLERS.get(type(change))
    if handler is None:
        raise NotImplementedError(f"No way to apply {type(change).__name__} to a snapshot")
    snapshot = copy.deepcopy(snapshot)
    handler(snapshot, change)
    return snapshot


# --- looking things up ----------------------------------------------------------------------------


def model_entry(snapshot: dict, name: str) -> dict:
    try:
        return snapshot["models"][name]
    except KeyError:
        raise KeyError(f"The snapshot has no model {name}") from None


def field_entry(snapshot: dict, model: str, name: str) -> dict:
    for entry in model_entry(snapshot, model)["fields"]:
        if entry["name"] == name:
            return entry
    raise KeyError(f"The snapshot has no field {model}.{name}")


# --- renames (also used by `diff` to compare under the new names) -------------------------------


def rename_model(snapshot: dict, old_name: str, new_name: str) -> dict:
    """The snapshot with a model under another name, wherever it is mentioned"""
    snapshot = replace_strings(copy.deepcopy(snapshot), old_name, new_name)
    snapshot["models"] = {
        (new_name if name == old_name else name): model
        for name, model in snapshot["models"].items()
    }
    return snapshot


def rename_enum(snapshot: dict, old_name: str, new_name: str) -> dict:
    snapshot = replace_strings(copy.deepcopy(snapshot), old_name, new_name)
    snapshot["enums"] = {
        (new_name if name == old_name else name): enum
        for name, enum in snapshot["enums"].items()
    }
    for name, enum in snapshot["enums"].items():
        if name == new_name:
            enum["name"] = new_name
    return snapshot


def replace_strings(value: Any, old: str, new: str) -> Any:
    """Every string that is `old`, replaced. (A class name is not likely to be a field's
    name or a value, which is the only way this goes wrong.)"""
    if isinstance(value, dict):
        return {key: replace_strings(item, old, new) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_strings(item, old, new) for item in value]
    if isinstance(value, str):
        return new if value == old else value
    return value


def rename_field(snapshot: dict, model: str, old_name: str, new_name: str) -> dict:
    snapshot = copy.deepcopy(snapshot)
    for entry in model_entry(snapshot, model)["fields"]:
        if entry["name"] != old_name:
            continue
        entry["name"] = new_name
        entry["key"] = to_camel(new_name)
        # (the reverse edges follow the name when they were named from it)
        if entry.get("reverseName") == f"{old_name}_reverse":
            entry["reverseName"] = f"{new_name}_reverse"
        edges = entry.get("storage", {}).get("edges")
        if edges:
            edges[0][0] = new_name
            if edges[0][1] == f"{old_name}_reverse":
                edges[0][1] = f"{new_name}_reverse"
    return snapshot


def rename_enum_member(snapshot: dict, enum: str, old_name: str, new_name: str) -> dict:
    snapshot = copy.deepcopy(snapshot)
    for member in snapshot["enums"][enum]["members"]:
        if member["name"] == old_name:
            member["name"] = new_name
    return snapshot


# --- one handler for each kind of change ------------------------------------------------------------
# (each changes the snapshot given)


def _rename_model(snapshot, change: c.RenameModel):
    snapshot.update(rename_model(snapshot, change.old, change.new))


def _rename_enum(snapshot, change: c.RenameEnum):
    snapshot.update(rename_enum(snapshot, change.old, change.new))


def _rename_field(snapshot, change: c.RenameField):
    snapshot.update(rename_field(snapshot, change.model, change.old, change.new))


def _rename_enum_member(snapshot, change: c.RenameEnumMember):
    snapshot.update(rename_enum_member(snapshot, change.enum, change.old, change.new))


def _create_enum(snapshot, change: c.CreateEnum):
    snapshot["enums"][change.enum] = copy.deepcopy(change.definition)


def _add_enum_member(snapshot, change: c.AddEnumMember):
    snapshot["enums"][change.enum]["members"].append(
        {"name": change.member, "value": change.value}
    )


def _remove_enum_member(snapshot, change: c.RemoveEnumMember):
    enum = snapshot["enums"][change.enum]
    enum["members"] = [m for m in enum["members"] if m["name"] != change.member]


def _remove_enum(snapshot, change: c.RemoveEnum):
    del snapshot["enums"][change.enum]


def _create_model(snapshot, change: c.CreateModel):
    snapshot["models"][change.model] = copy.deepcopy(change.definition)


def _delete_model(snapshot, change: c.DeleteModel):
    del snapshot["models"][change.model]


def _alter_model_kind(snapshot, change: c.AlterModelKind):
    entry = model_entry(snapshot, change.model)
    entry["kind"] = change.new
    entry["labels"] = [change.new if label == change.old else label for label in entry["labels"]]


def _alter_model_labels(snapshot, change: c.AlterModelLabels):
    entry = model_entry(snapshot, change.model)
    labels = [label for label in entry["labels"] if label not in change.removed]
    entry["labels"] = labels + [label for label in change.added if label not in labels]


def _alter_model_option(snapshot, change: c.AlterModelOption):
    model_entry(snapshot, change.model)[change.option] = change.new


def _add_field(snapshot, change: c.AddField):
    model_entry(snapshot, change.model)["fields"].append(copy.deepcopy(change.definition))


def _remove_field(snapshot, change: c.RemoveField):
    entry = model_entry(snapshot, change.model)
    entry["fields"] = [f for f in entry["fields"] if f["name"] != change.name]


def _replace_field(snapshot, change):
    """The change carries the field as it is now"""
    entry = model_entry(snapshot, change.model)
    entry["fields"] = [
        copy.deepcopy(change.definition) if f["name"] == change.name else f
        for f in entry["fields"]
    ]


def _alter_literal_type(snapshot, change: c.AlterLiteralType):
    field_entry(snapshot, change.model, change.name)["type"] = copy.deepcopy(change.new)


def _alter_list_item_type(snapshot, change: c.AlterListItemType):
    field_entry(snapshot, change.model, change.name)["item"] = copy.deepcopy(change.new)


def _alter_nullability(snapshot, change: c.AlterNullability):
    field_entry(snapshot, change.model, change.name)["nullable"] = change.nullable


def _alter_annotated_value(snapshot, change: c.AlterAnnotatedValue):
    entry = field_entry(snapshot, change.model, change.name)
    entry["model"] = change.new_model
    entry["valueType"] = copy.deepcopy(change.new_value_type)


def _alter_embedded(snapshot, change: c.AlterEmbedded):
    entry = field_entry(snapshot, change.model, change.name)
    entry["model"] = change.new_model
    entry["types"] = list(change.types)


def _set_options(snapshot, change):
    field_entry(snapshot, change.model, change.name)["options"] = copy.deepcopy(change.options)


def _literals_to_embedded(snapshot, change: c.LiteralsToEmbedded):
    entry = model_entry(snapshot, change.model)
    entry["fields"] = [f for f in entry["fields"] if f["name"] not in change.fields]
    entry["fields"].append(copy.deepcopy(change.definition))


def _embedded_to_literals(snapshot, change: c.EmbeddedToLiterals):
    entry = model_entry(snapshot, change.model)
    entry["fields"] = [f for f in entry["fields"] if f["name"] != change.name]
    entry["fields"].extend(copy.deepcopy(change.definitions))


def _alter_cardinality(snapshot, change: c.AlterCardinality):
    field_entry(snapshot, change.model, change.name)["many"] = change.many


def _alter_reverse_name(snapshot, change: c.AlterReverseName):
    entry = field_entry(snapshot, change.model, change.name)
    entry["reverseName"] = change.new
    if entry.get("storage", {}).get("edges"):
        entry["storage"]["edges"][0][1] = change.new


def _alter_parent_fields(snapshot, change: c.AlterParentFields):
    field_entry(snapshot, change.model, change.name)["storage"]["edges"] = copy.deepcopy(
        change.edges
    )


def _nothing(snapshot, change):
    """Changes by hand: what they do is to the data, and the other changes say what the models are"""


def _state_only(snapshot, change: c.StateOnly):
    after = snapshot
    for inner in change.changes:
        after = apply_change(after, inner)
    snapshot.clear()
    snapshot.update(after)


HANDLERS: dict[type, Callable[[dict, Any], None]] = {
    c.RenameModel: _rename_model,
    c.RenameEnum: _rename_enum,
    c.RenameField: _rename_field,
    c.RenameEnumMember: _rename_enum_member,
    c.CreateEnum: _create_enum,
    c.AddEnumMember: _add_enum_member,
    c.RemoveEnumMember: _remove_enum_member,
    c.RemoveEnum: _remove_enum,
    c.CreateModel: _create_model,
    c.DeleteModel: _delete_model,
    c.AlterModelKind: _alter_model_kind,
    c.AlterModelLabels: _alter_model_labels,
    c.AlterModelOption: _alter_model_option,
    c.AddField: _add_field,
    c.RemoveField: _remove_field,
    c.ChangeFieldKind: _replace_field,
    c.LiteralToAnnotatedValue: _replace_field,
    c.AnnotatedValueToLiteral: _replace_field,
    c.AlterLiteralType: _alter_literal_type,
    c.AlterListItemType: _alter_list_item_type,
    c.AlterNullability: _alter_nullability,
    c.AlterAnnotatedValue: _alter_annotated_value,
    c.AlterEmbedded: _alter_embedded,
    c.AlterRelationTarget: _set_options,
    c.AlterEdgeModel: _set_options,
    c.ChangeWrapper: _set_options,
    c.LiteralsToEmbedded: _literals_to_embedded,
    c.EmbeddedToLiterals: _embedded_to_literals,
    c.WrapRelation: _set_options,
    c.UnwrapRelation: _set_options,
    c.AlterCardinality: _alter_cardinality,
    c.AlterReverseName: _alter_reverse_name,
    c.AlterParentFields: _alter_parent_fields,
    c.RunCypher: _nothing,
    c.RunPython: _nothing,
    c.StateOnly: _state_only,
}
