"""Reading the relations *to* an entity: the documents (and entities) that refer
to it, for the `HeadView` of an entity.

For each relation, the `HeadView` has a field named after the reverse relation
(`involves_person_reverse`) holding a list of:

- a `ReferenceView` of the document, for a direct relation, or one through a chain
  of embedded objects (it points to the document that the chain starts from); or
- for a relation through reified relations, a view of that document containing
  only its `id`, `type` and `meta`, and the field with the chain of reified
  relations: each with its own values, and the next in the chain as its `target`.
  At the end of the chain, `target` is every target of that reified relation.
"""

import typing
import uuid

from pangloss_models.model_bases.entity import Entity

from pangloss_memgraph.databases.memgraph.build_read_query import (
    build_fetch_incoming_query,
)
from pangloss_memgraph.databases.memgraph.database import Transaction

REIFIED_LABELS = {"ReifiedRelation", "ReifiedRelationDocument"}
CHAIN_LABELS = REIFIED_LABELS | {"Embedded"}

# Not values of a reified relation
INTERNAL_KEYS = {"_labels", "meta", "head_node_id", "head_node_type"}


def reified_view(chain: list[dict], index: int, next_targets: list[dict]) -> dict:
    """The view of the reified relation at `chain[index]`, with (as its `target`) the
    next one down the chain, or, for the last, all of its targets"""
    node = {k: v for k, v in chain[index].items() if k not in INTERNAL_KEYS}
    if index == 0:
        node["target"] = [
            {k: v for k, v in target.items() if k != "meta"} for target in next_targets
        ]
    else:
        node["target"] = [reified_view(chain, index - 1, next_targets)]
    return node


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
    result = await tx.run(query, **params)
    records = await result.data()

    incoming: dict[str, list[dict[str, typing.Any]]] = {}
    for record in records:
        chain: list[dict] = record["chain"]
        edge_types: list[str] = record["chain_edge_types"]
        holder = chain[-1]

        via_reified = bool(chain[0]["_labels"]) and bool(
            set(chain[0]["_labels"]) & REIFIED_LABELS
        )

        # The name of the relation (as seen from the entity) is the reverse edge
        # that the reified chain, if any, ends with, or else the first reverse edge
        reified_run = 0
        if via_reified:
            while reified_run + 1 < len(chain) and (
                set(chain[reified_run + 1]["_labels"]) & REIFIED_LABELS
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
            relation = reified_view(chain, reified_run, record["next_targets"])
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
