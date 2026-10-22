"""Which classes a node fulfils (`Fulfils`), as the snapshot says.

A class declared `Fulfils[X]` supplies what `X` requires. A node of it is written with the labels of
`X` too if it has everything `X` requires (`get_fulfilled_classes`: if what it holds is a valid `X`).
The snapshot records, for each model that fulfils anything, `fulfils`: for each class, which of its
fields the model's own fields stand in for (`{"class": "X", "fields": {"x_field": "own_field"}}`).

`fulfilment(snapshot, model)` works out from that, for a model, what decides each class's labels:
the labels, and what a node needs to have. It is what a migration is given (`RecomputeFulfils`),
so that it needs nothing but itself. A change to it is a change to which nodes have which labels.
"""

import json
from typing import Any

# Fields every node has, or that are not the model's to give
SYSTEM_FIELDS = {"type", "label"}


def required(field: dict[str, Any]) -> bool:
    """Whether a node must have a value for the field to be a valid node of its model"""
    if field.get("dbField"):
        return False
    kind = field["kind"]
    if kind in ("literal", "annotatedValue"):
        return not field.get("nullable", False)
    if kind in ("relation", "embedded"):
        return not field.get("many", False)
    return False


def needs_of(snapshot: dict[str, Any], model: str, fulfilled: dict[str, Any]) -> list[dict[str, Any]]:
    """What a node of `model` must have to fulfil a class: for each field the class requires, where
    the node keeps its value (a `property` or an `edge`), or `never` if it has no such field"""
    own = {f["name"]: f for f in snapshot["models"][model]["fields"]}
    other = snapshot["models"].get(fulfilled["class"])
    if other is None:
        return [{"never": True}]
    needs: list[dict[str, Any]] = []
    for field in other["fields"]:
        name = field["name"]
        if name in SYSTEM_FIELDS or not required(field):
            continue
        mine = own.get(fulfilled.get("fields", {}).get(name, name))
        if mine is None:
            needs.append({"never": True, "field": name})
            continue
        storage = mine.get("storage", {})
        if storage.get("kind") in ("property", "map_property"):
            needs.append({"property": mine["name"]})
        elif storage.get("edges"):
            needs.append({"edge": storage["edges"][0][0]})
        else:
            needs.append({"never": True, "field": name})
    # (in a steady order: the order the fields were declared in is not what is stored)
    return sorted(needs, key=lambda need: json.dumps(need, sort_keys=True))


def fulfilment(snapshot: dict[str, Any], model: str) -> list[dict[str, Any]]:
    """For each class the model fulfils: its `labels`, and what a node needs to have (`needs`)"""
    entry = snapshot["models"].get(model, {})
    result = []
    for fulfilled in entry.get("fulfils", []):
        other = snapshot["models"].get(fulfilled["class"], {})
        result.append(
            {
                "class": fulfilled["class"],
                "labels": list(other.get("labels", [fulfilled["class"]])),
                "needs": needs_of(snapshot, model, fulfilled),
            }
        )
    return sorted(result, key=lambda e: e["class"])
