"""Reading the relations *to* an entity: the documents (and entities) that refer
to it, for the `HeadView` of an entity.

For each relation, the `HeadView` has a field named after the reverse relation
(`involves_person_reverse`) holding a list of:

- a `ReferenceView` of the document, for a direct relation, or one through a chain
  of embedded objects (it points to the document that the chain starts from); or
- for a relation through generic wrappers (reified relations, semantic spaces,
  conjunctions), a view of that document containing only its `id`, `type` and
  `meta`, and the field with the chain of wrappers: each with its own values, and
  the next in the chain in the field that holds it (`target` of a reified relation,
  `contents` of a semantic space, `cause` or `result` of a conjunction). At the
  end of the chain are all the targets of the wrapper next to the entity.
"""

import functools
import logging
import typing
import uuid

from pangloss_models.field_definitions import RelationFieldDefinition, RelationToTypeVar
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_registry import ModelRegistry

from pangloss_memgraph.databases.memgraph.build_read_query import (
    WRAPPER_LABELS,
    build_fetch_held_query,
    build_fetch_incoming_query,
)
from pangloss_memgraph.databases.memgraph.database import Transaction

logger = logging.getLogger(__name__)

# (the labels of the generic wrappers: what a relation to an entity can pass through)
WRAPPERS = set(WRAPPER_LABELS)

# Not values of a reified relation
INTERNAL_KEYS = {"_labels", "meta", "head_node_id", "head_node_type"}


@functools.cache
def held_fields(wrapper_name: str) -> dict[str, RelationFieldDefinition]:
    """The fields of a generic wrapper that hold what it is made for (its type variables): `target` of a
    reified relation, `contents` of a semantic space, `cause` and `result` of a conjunction"""
    wrapper = ModelRegistry.all_models().get(wrapper_name)
    if wrapper is None:
        return {}
    return {
        name: definition
        for name, definition in wrapper._meta.fields.relation_fields.items()
        if any(
            isinstance(option, RelationToTypeVar) for option in definition.type_options
        )
    }


def clear_wrapper_fields() -> None:
    """(the models have changed: forget what was worked out from them)"""
    held_fields.cache_clear()


def field_leading_to(wrapper_name: str, reverse_edge: str) -> str | None:
    """The field of a wrapper that holds the node a reverse edge comes from"""
    for name, definition in held_fields(wrapper_name).items():
        if definition.reverse_name == reverse_edge:
            return name
    return None


def unlinked(value: dict) -> dict:
    return {k: v for k, v in value.items() if k != "meta"}


def wrapper_view(
    chain: list[dict], index: int, edge_types: list[str], held: dict[str, list[dict]]
) -> dict:
    """The view of the wrapper at `chain[index]`: its own values, and its fields that hold what it is
    made for. In the one that leads down the chain is the next wrapper; the others hold their targets
    (for the one next to the entity, that is every target of it, the entity itself and any others)."""
    node = {k: v for k, v in chain[index].items() if k not in INTERNAL_KEYS}
    holds = held.get(node["id"], [])
    leading = (
        field_leading_to(node["type"], edge_types[index - 1]) if index > 0 else None
    )

    for name, definition in held_fields(node["type"]).items():
        if name == leading:
            child = wrapper_view(chain, index - 1, edge_types, held)
            node[name] = definition.wrapper([child]) if definition.wrapper else child
            continue
        targets = [t for t in holds if t["edge"] == name]
        if index > 0 and any("Entity" not in t["labels"] for t in targets):
            # (only an entity can be shown for a part that is not on the way down to this one)
            raise UnrepresentableChain(node["type"], name)
        values = [unlinked(t["node"]) for t in targets]
        node[name] = values if definition.wrapper else (values[0] if values else None)
    return node


class UnrepresentableChain(Exception):
    """A relation to an entity that cannot be shown from the entity: a wrapper above the one next to the
    entity has another part that is not an entity (a conjunction of the entity's relation and a
    document)"""

    def __init__(self, wrapper: str, field: str):
        super().__init__(f"{wrapper}.{field} holds something that is not an entity")


def holder_meta(holder: dict, creation_meta: dict) -> dict:
    """The `meta` of a `ReferenceView`: the node's own record of who created it, if
    it has one (a nested node), otherwise that of the document it is the head of"""
    own_meta = holder.get("meta") or {}
    return {
        "is_head_node": "HeadNode" in holder["_labels"],
        "head_node_id": creation_meta["head_node_id"],
        "head_node_type": creation_meta["head_node_type"],
        "semantic_spaces": own_meta.get("semantic_spaces") or [],
        "context_labels": own_meta.get("context_labels"),
        "created_by": own_meta.get("created_by") or creation_meta["created_by"],
        "created_when": own_meta.get("created_when") or creation_meta["created_when"],
        "updated_by": creation_meta["updated_by"],
        "updated_when": creation_meta["updated_when"],
    }


async def fetch_held(tx: Transaction, node_ids: list[str]) -> dict[str, list[dict]]:
    """What each of the wrappers holds, by the name of the field: `{"edge": ..., "node": {...}}`"""
    if not node_ids:
        return {}
    query, params = build_fetch_held_query(sorted(set(node_ids)))
    result = await tx.run(query, **params)  # ty: ignore[invalid-argument-type]
    return {row["id"]: row["held"] for row in await result.data()}


async def fetch_incoming_relations(
    tx: Transaction, entity_class: type[Entity], entity_id: uuid.UUID
) -> dict[str, list[dict[str, typing.Any]]]:
    """Get what refers to an entity, as the values of the incoming fields of its
    `HeadView`"""

    # What can be on the other end of each incoming field, according to the models.
    # A relation that a subclass narrows (`carried_out_by` for `concerns_person`) is
    # stored under both names, but only appears under the narrower one, and so
    # the model does not allow the subclass under the wider one.
    incoming_definitions = entity_class._meta.field_definitions.incoming_fields

    query, params = build_fetch_incoming_query(entity_class, entity_id)
    result = await tx.run(query, **params)  # ty: ignore[invalid-argument-type]
    records = await result.data()

    # What the wrappers next to the entity hold (their targets), for those that come to it through one
    held = await fetch_held(
        tx,
        [
            node["id"]
            for record in records
            for node in record["chain"]
            if set(node["_labels"]) & WRAPPERS
        ],
    )

    incoming: dict[str, list[dict[str, typing.Any]]] = {}
    for record in records:
        chain: list[dict] = record["chain"]
        edge_types: list[str] = record["chain_edge_types"]
        holder = chain[-1]

        via_reified = bool(chain[0]["_labels"]) and bool(
            set(chain[0]["_labels"]) & WRAPPERS
        )

        # The name of the relation (as seen from the entity) is the reverse edge
        # that the chain of wrappers, if any, ends with, or else the first reverse edge
        reified_run = 0
        if via_reified:
            while reified_run + 1 < len(chain) and (
                set(chain[reified_run + 1]["_labels"]) & WRAPPERS
            ):
                reified_run += 1
            name = edge_types[reified_run]
        else:
            name = record["first_edge_type"]

        definitions = [
            definition
            for definition in incoming_definitions.get(name, [])
            if definition.source.__name__ == holder["type"]
            and definition.via_reified == via_reified
        ]
        if not definitions:
            continue

        meta = holder_meta(holder, record["creation_meta"])

        if via_reified:
            field_definition = definitions[0].field_definition
            try:
                relation = wrapper_view(chain, reified_run, edge_types, held)
            except UnrepresentableChain as error:
                logger.warning(
                    "A relation to %s %s from %s %s is not shown: %s",
                    entity_class.__name__,
                    entity_id,
                    holder["type"],
                    holder["id"],
                    error,
                )
                continue
            item = {
                "id": holder["id"],
                "type": holder["type"],
                "meta": meta,
                # (the field of the document, which may be a list of reified relations)
                field_definition.field_name: (
                    field_definition.wrapper([relation])
                    if field_definition.wrapper
                    else relation
                ),
            }
        else:
            item = {
                **{k: v for k, v in holder.items() if k not in INTERNAL_KEYS},
                "meta": meta,
            }
        incoming.setdefault(name, []).append(item)

    return incoming
