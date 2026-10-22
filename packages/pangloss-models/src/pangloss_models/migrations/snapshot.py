"""The schema snapshot: the initialised models as plain data, with how they are stored.

It is `export_models()` (what the interface reads), with what a migration needs on top:

- `module` of each model: where the class is, to say which app a change to it belongs to;
- `labels` of each model: the labels of its nodes (its name, its parents and traits, its
  kind);
- `storage` of each field: how it is written to the graph (`property`, `map_property`,
  `embedded_node` or `edge`), and for the last two the edge types: `[forward, reverse]`
  for the field and, after them, one pair for each parent field it narrows
  (`subclasses_parent_fields`), since an edge pair is written for each.
"""

import copy
import hashlib
import json
from typing import Any

from pangloss_models.export import export_models
from pangloss_models.field_definitions import (
    AnnotatedValueFieldDefinition,
    EmbeddedFieldDefinition,
    FieldDefinition,
    RelationFieldDefinition,
)
from pangloss_models.model_bases.base_models import labels_for_model
from pangloss_models.model_registry import ModelRegistry

SNAPSHOT_VERSION = 1

# Not part of what is stored, or derived from other parts: a change of these is not a change
# of the data, and is not in the hash
NOT_DATA_KEYS = {
    "module",  # where the class is (for which app a change belongs to)
    "description",  # documentation
    "validators",  # checked when writing; see `check-data`
    "itemValidators",
    "dbField",  # only whether it is in `CreateDB`
    "required",  # whether it has a default
    "concreteTypes",  # follows from the models that exist
    "incoming",  # follows from the fields of the other models
    "app",  # the app an index or constraint is for (which migration makes it)
}


def field_storage(definition: FieldDefinition) -> dict[str, Any]:
    if isinstance(definition, AnnotatedValueFieldDefinition):
        return {"kind": "map_property"}

    if isinstance(definition, EmbeddedFieldDefinition):
        return {
            "kind": "embedded_node",
            "edges": [[definition.field_name, f"{definition.field_name}_reverse"]],
        }

    if isinstance(definition, RelationFieldDefinition):
        edges = [[definition.field_name, definition.reverse_name]]
        for parent in sorted(
            definition.subclasses_parent_fields,
            key=lambda p: getattr(p, "field_name", str(p)),
        ):
            name = getattr(parent, "field_name", str(parent))
            reverse = None
            on_model = getattr(parent, "field_on_model", None)
            if on_model is not None:
                parent_field = on_model._meta.fields.relation_fields.get(name)
                reverse = parent_field.reverse_name if parent_field else None
            edges.append([name, reverse])
        return {"kind": "edge", "edges": edges}

    return {"kind": "property"}


def fulfils_of(model) -> list[dict[str, Any]]:
    """The classes a model fulfils (`Fulfils[...]`, also from a parent class), and which of their
    fields its own fields stand in for. (Nothing for most models, which then have no `fulfils`.)"""
    from pangloss_models.initialise_models.initialise_field_definitions import get_fulfilled_types

    classes = get_fulfilled_types(model)
    stands_in: dict[str, dict[str, str]] = {cls.__name__: {} for cls in classes}
    for name, definition in model._meta.field_definitions.fields.items():
        for fulfilment in getattr(definition, "field_required_to_fulfil", ()):
            stands_in.setdefault(fulfilment.fulfils_class.__name__, {})[fulfilment.field_name] = name
    return [
        {"class": cls, "fields": dict(sorted(fields.items()))} for cls, fields in sorted(stands_in.items())
    ]


def build_snapshot(structure: dict[str, Any] | None = None) -> dict[str, Any]:
    """The snapshot of the models that are registered (initialise them first).

    `structure` is what the database needs besides the models, as the database package says it
    (`indexes` and `constraints`: lists of `{"kind", "label", "properties", ...}`, each perhaps with
    the `app` whose migration is to make it); without it the snapshot has none."""
    exported = export_models()
    models = ModelRegistry.all_models()

    for name, entry in exported["models"].items():
        model = models[name]
        entry["labels"] = labels_for_model(model, model.__metatype__)
        entry["module"] = model.__module__
        definitions = model._meta.field_definitions.fields
        for field in entry["fields"]:
            field["storage"] = field_storage(definitions[field["name"]])
        fulfils = fulfils_of(model)
        if fulfils:
            entry["fulfils"] = fulfils

    snapshot = {"version": SNAPSHOT_VERSION, **exported}
    if structure:
        snapshot["indexes"] = copy.deepcopy(structure.get("indexes", []))
        snapshot["constraints"] = copy.deepcopy(structure.get("constraints", []))
    return snapshot


def data_view(snapshot: Any) -> Any:
    """The snapshot without what is not stored (documentation, validators, what is
    derived): what a hash and a comparison are of"""
    if isinstance(snapshot, dict):
        view = {
            key: data_view(value)
            for key, value in snapshot.items()
            if key not in NOT_DATA_KEYS
        }
        # (the order they were declared in is not stored)
        if isinstance(view.get("fields"), list):
            view["fields"] = sorted(view["fields"], key=lambda f: f["name"])
        if isinstance(view.get("labels"), list):
            view["labels"] = sorted(view["labels"])
        if "models" in view:  # (the snapshot as a whole)
            for key in ("indexes", "constraints"):
                view[key] = sorted(
                    view.get(key, []), key=lambda e: json.dumps(e, sort_keys=True)
                )
        if isinstance(view.get("members"), list) and all(
            isinstance(m, dict) and "name" in m for m in view["members"]
        ):
            view["members"] = sorted(view["members"], key=lambda m: m["name"])
        return view
    if isinstance(snapshot, list):
        return [data_view(item) for item in snapshot]
    return copy.deepcopy(snapshot)


def snapshot_hash(snapshot: dict[str, Any]) -> str:
    """A hash of what is stored, the same for models that are stored the same"""
    canonical = json.dumps(data_view(snapshot), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
