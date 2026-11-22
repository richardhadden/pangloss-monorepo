"""The unknowns of a write plan: the nodes in whose place an entity would be (implementation_docs/similarity-build-plan.md,
phase 10, "Read again (2026-11-22)", row c).

A node is an unknown when its class is the document of a `hooks.StandIn` that says which property names the one
entity class it stands for (`StandIn.named_type`: review's `Unreconciled` says `unreconciled_type`), and its
properties give a label that is not empty and, under that property, the name of a class of entities. A stand-in that
does not say (`named_type` None: a generic wrapper, criteria's `MatchesCriteria`) is no unknown: it stands for
whatever its field takes, and has no label of its own. Nothing here knows which package a stand-in is of.
"""

from typing import Any

from pangloss_models import Document, Entity, ModelRegistry, hooks

from pangloss_vectors.parts import Unknown


def _named_types() -> list[tuple[type, str]]:
    """The document classes of the stand-ins that name their type, each with the property that names it"""
    found = []
    for stand_in in hooks.stand_ins:
        if stand_in.named_type is None:
            continue
        document = ModelRegistry._model_dict.get(stand_in.document)
        if isinstance(document, type) and issubclass(document, Document):
            found.append((document, stand_in.named_type))
    return found


def _entity_class(name: Any) -> bool:
    model = ModelRegistry._model_dict.get(name) if isinstance(name, str) else None
    return isinstance(model, type) and issubclass(model, Entity)


def unknowns_of(plan: Any) -> list[Unknown]:
    """The unknowns of a write plan (`pangloss_cypher.write_plan.WritePlan`), in the order of the plan (`walk`): the
    nodes below its head, at any depth, whose class is (or is below) the document of a stand-in that names its type,
    with a label and a class of entities under that property. A node inside an entity written in the document is
    none: it is the entity's, not the document's"""
    from pangloss_cypher.write_plan import InlineEntity, PlannedNode

    named = _named_types()
    if not named:
        return []
    found: list[Unknown] = []
    # (the nodes of the entities written in the document, and everything below them)
    inside: set[str] = set()
    for source, relation, first in plan.walk():
        target = relation.target
        if isinstance(target, InlineEntity):
            if first and target.node is not None:
                inside.add(target.node.id)
            continue
        if not isinstance(target, PlannedNode):
            continue
        if source.id in inside:
            inside.add(target.id)
            continue
        model = ModelRegistry._model_dict.get(target.type)
        if not isinstance(model, type):
            continue
        for document, property_name in named:
            if not issubclass(model, document):
                continue
            label = target.properties.get("label")
            type_name = target.properties.get(property_name)
            if isinstance(label, str) and label.strip() and _entity_class(type_name):
                found.append(Unknown(id=str(target.id), type=type_name, label=label))
            break
    return found
