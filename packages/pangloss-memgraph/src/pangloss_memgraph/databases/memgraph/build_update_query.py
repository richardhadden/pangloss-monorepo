"""Queries for updating an existing head node (a Document or Entity).

An update replaces the whole tree below the head node, rather than working out
what has changed:

1. `build_replace_head_query` deletes every node below the head node, except
   entities, which belong to no document; deletes the edges the head node owns;
   and replaces the head node's properties.
2. `build_head_update_query` then writes the new tree in the same way as a
   creation, and records the update with a `PGUpdate` node.

Edges are always written in pairs: a forward edge, and a reverse edge marked
`{reverse: true}`. A node owns its outgoing edges that are not reverse edges, and
the reverse edges pointing back at it. Edges from documents *to* an entity (which
the entity does not own) are therefore left alone when an entity is updated.
"""

import datetime
import typing
import uuid

from pangloss_models.model_bases.document import _DocumentUpdateDBBase
from pangloss_models.model_bases.entity import _EntityUpdateDBBase
from pangloss_models.model_bases.labels import fulfillable_labels
from pangloss_users import current_request_username

from pangloss_memgraph.databases.memgraph.build_create_query import (
    ExistingEntity,
    InlineEntityKey,
    PropertyAssignments,
    QueryObject,
    QueryParams,
    build_attached_nodes,
    get_node_fields_as_writable_dict,
)

# Walks forward edges from the head node, without entering entities
# (The URLs of an entity are not part of what it owns)
TREE_TRAVERSAL = "[*BFS (edge, node | NOT node:Entity AND NOT node:PGUrl AND NOT coalesce(edge.reverse, false))]"


# The version of a head node: 1, and 1 more for each update of it
VERSION_OF_HEAD = "size([(head)<-[:is_update_of]-(update:PGUpdate) | update]) + 1"


def build_head_query(head_id: uuid.UUID) -> tuple[str, dict[str, typing.Any]]:
    """Find a head node, and get what is needed to check an update to it"""
    return (
        f"""
        MATCH (head:PGIndexableNode:HeadNode {{id: $head_id}})
        OPTIONAL MATCH (head)<-[:is_creation_of]-(creation:PGCreation)
                       -[:created_by]->(user:PGUser)
        RETURN labels(head) AS labels,
               creation.created_when AS created_when,
               user.username AS created_by,
               coalesce(head.deleted, false) AS deleted,
               {VERSION_OF_HEAD} AS version
        """,
        {"head_id": str(head_id)},
    )


def build_tree_meta_query(head_id: uuid.UUID) -> tuple[str, dict[str, typing.Any]]:
    """Get `meta` of every node below a head node, to keep its creation info"""
    return (
        f"""
        MATCH (head:HeadNode {{id: $head_id}})-{TREE_TRAVERSAL}->(node)
        WHERE node.meta IS NOT NULL
        RETURN node.id AS id, node.meta AS meta
        """,
        {"head_id": str(head_id)},
    )


def build_replace_head_query(
    instance: _DocumentUpdateDBBase | _EntityUpdateDBBase,
) -> tuple[str, dict[str, typing.Any]]:
    """Delete everything the head node owns, and replace its properties"""
    params = QueryParams()
    head_id_identifier = params.add(str(instance.id))
    data = get_node_fields_as_writable_dict(instance, is_new=True, is_head_node=True)
    assignments = PropertyAssignments(params, data)
    # the classes it fulfils now, by what it holds: their labels are put on, and those of the
    # classes it could fulfil and does not are taken off
    labels = instance._labels
    gone = sorted(fulfillable_labels(instance) - set(labels))
    relabel = "".join(
        [
            f"SET head{''.join(':' + label for label in labels)}\n        "
            if labels
            else "",
            f"REMOVE head{''.join(':' + label for label in gone)}\n        "
            if gone
            else "",
        ]
    )
    return (
        f"""
        MATCH (head:HeadNode {{id: ${head_id_identifier}}})
        OPTIONAL MATCH (head)-{TREE_TRAVERSAL}->(node)
        WITH head, collect(DISTINCT node) AS tree
        OPTIONAL MATCH (head)-[owned_out]->()
        WHERE NOT coalesce(owned_out.reverse, false) AND type(owned_out) <> 'has_url'
        WITH head, tree, collect(owned_out) AS owned_out_edges
        OPTIONAL MATCH ()-[owned_in]->(head)
        WHERE coalesce(owned_in.reverse, false)
        WITH head, tree, owned_out_edges,
             collect(owned_in) AS owned_in_edges
        FOREACH (edge IN owned_out_edges + owned_in_edges | DELETE edge)
        FOREACH (node IN tree | DETACH DELETE node)
        SET {assignments.set_items("head", replace=True)}
        {relabel}RETURN head.id AS id
        """,
        dict(params),
    )


def build_head_update_query(
    instance: _DocumentUpdateDBBase | _EntityUpdateDBBase,
    previous_meta: dict[str, dict[str, typing.Any]],
    existing_entities: dict[InlineEntityKey, ExistingEntity] | None = None,
) -> QueryObject:
    """Write the new tree below an existing head node, and record the update"""

    query_object = QueryObject(
        head_id=instance.id,
        head_type=instance.type,
        existing_entities=existing_entities,
    )
    query_object.previous_meta = previous_meta

    node_identifier = query_object.params.new_identifier()
    query_object.return_identifier = node_identifier

    head_id_identifier = query_object.params.add(str(instance.id))
    username_identifier = query_object.params.add(current_request_username.get())
    update_data_identifier = query_object.params.add(
        {
            "id": str(uuid.uuid7()),
            "updated_when": datetime.datetime.now(datetime.UTC),
        }
    )

    query_object.match_query_strings.append(
        f"""MATCH (user:PGUser {{username: ${username_identifier}}})
            MATCH ({node_identifier}:HeadNode {{id: ${head_id_identifier}}})"""
    )
    query_object.create_query_strings.append(f"""
        CREATE (update:PGUpdate)
        SET update = ${update_data_identifier}
        CREATE (update)-[:is_update_of]->({node_identifier})
        CREATE (update)-[:updated_by]->(user)
    """)

    build_attached_nodes(
        query_object, instance, node_identifier, instance.type, instance.id
    )

    return query_object
