import uuid

from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity

from pangloss_memgraph.databases.memgraph.build_create_query import (
    QueryParams,
    convert_type_for_writing,
)


def build_fetch_document_query(
    document_class: type[Document | Entity], document_id: uuid.UUID
) -> tuple[str, QueryParams]:
    """Build the query for a Document or Entity and what it contains: its own
    values, `meta`, and everything below it. It returns the root node, the edges of
    the tree below it, and the `meta` (`build_tree` makes the tree). (For an Entity, its relations to
    documents come from `build_fetch_incoming_query`)"""
    # (the names of the parameters are fixed, so that the text of the query is the same each
    # time and Memgraph finds its plan again: with a name made for each call it planned it
    # afresh each time, which took most of the time a read took)
    document_id_identifier = "document_id"
    document_type_identifier = "document_type"
    query_params = QueryParams()
    query_params[document_id_identifier] = convert_type_for_writing(document_id)
    query_params[document_type_identifier] = document_class.__name__
    query = f"""
    MATCH rp = (root:PGIndexableNode {{id: ${document_id_identifier}}})
    WHERE ${document_type_identifier} in labels(root)
    OPTIONAL MATCH (hn:HeadNode {{id: root.head_node_id}})
    WITH root, rp, coalesce(hn, root) AS headnode
    // (a deleted document, or one nested in it, or a deleted entity, is not found)
    WHERE NOT coalesce(CASE WHEN root:Entity THEN root.deleted ELSE headnode.deleted END, false)
    MATCH (headnode)<-[:is_creation_of]-(creation:PGCreation)
    MATCH (creation)-[:created_by]->(user:PGUser)
    CALL {{
        WITH headnode
        OPTIONAL MATCH (headnode)<-[:is_update_of]-(update:PGUpdate)-[:updated_by]->(update_user:PGUser)
        RETURN update.updated_when AS updated_when, update_user.username AS updated_by
        ORDER BY update.updated_when DESC
        LIMIT 1
    }}
    // The tree below the root: every node reachable by forward edges, without
    // entering entities. (Each relation is stored as a forward edge and a
    // reverse edge marked `reverse: true`, which is not followed.)
    OPTIONAL MATCH tree_path = (root)-[*BFS (e, n | NOT n:Entity AND NOT n:PGUrl AND NOT coalesce(e.reverse, false))]->(descendant)
    WITH headnode, root, creation, user, updated_by, updated_when, rp, collect(tree_path) AS tree_paths
    // The entities that the nodes of the tree refer to
    OPTIONAL MATCH entity_path = (root)-[*BFS (e, n | NOT n:Entity AND NOT n:PGUrl AND NOT coalesce(e.reverse, false))]->(holder)-[holder_edge]->(:Entity)
    WHERE NOT coalesce(holder_edge.reverse, false)
    WITH headnode, root, creation, user, updated_by, updated_when, rp, tree_paths, collect(entity_path) AS entity_paths
    OPTIONAL MATCH root_entity_path = (root)-[root_edge]->(:Entity)
    WHERE NOT coalesce(root_edge.reverse, false)
    WITH headnode, root, creation, user, updated_by, updated_when,
         collect(rp) + tree_paths + entity_paths + collect(root_entity_path) AS paths
    UNWIND paths AS path
    UNWIND (CASE WHEN size(relationships(path)) = 0 THEN [null] ELSE relationships(path) END) AS edge
    WITH headnode, root, creation, user, updated_by, updated_when,
         [found IN collect(DISTINCT edge) WHERE found IS NOT NULL] AS found_edges
    // A search reaches each node once, along one edge. A field that narrows another is stored
    // as an edge for each (to the same node), so the others between the same two nodes are
    // added: which one the search met first is not to decide what is read.
    UNWIND (CASE WHEN size(found_edges) = 0 THEN [null] ELSE found_edges END) AS found_edge
    WITH headnode, root, creation, user, updated_by, updated_when, found_edges, found_edge,
         CASE WHEN found_edge IS NULL THEN null ELSE startNode(found_edge) END AS from_node,
         CASE WHEN found_edge IS NULL THEN null ELSE endNode(found_edge) END AS to_node
    OPTIONAL MATCH (from_node)-[parallel]->(to_node)
    WHERE parallel <> found_edge AND NOT coalesce(parallel.reverse, false)
    WITH headnode, root, creation, user, updated_by, updated_when,
         found_edges + [p IN collect(DISTINCT parallel) WHERE p IS NOT NULL] AS all_edges
    UNWIND (CASE WHEN size(all_edges) = 0 THEN [null] ELSE all_edges END) AS edge
    WITH headnode, root, creation, user, updated_by, updated_when, collect(DISTINCT edge) AS edges
    RETURN
        properties(root) AS root,
        labels(root) AS root_labels,
        [(root)-[:has_url]->(url:PGUrl) | url.url] AS urls,
        [edge IN edges WHERE edge IS NOT NULL | {{
            source: startNode(edge).id,
            type: type(edge),
            properties: properties(edge),
            target: properties(endNode(edge)),
            target_labels: labels(endNode(edge))
        }}] AS edges,
        {{
            created_by: user.username,
            created_when: creation.created_when,
            updated_by: updated_by,
            updated_when: updated_when,
            semantic_spaces: root.meta.semantic_spaces,
            context_labels: root.meta.context_labels,
            head_node_type: headnode.type,
            head_node_id: headnode.id,
            marked_for_deletion: coalesce(root.marked_for_deletion, false),
            version: size([(headnode)<-[:is_update_of]-(version_update:PGUpdate) | version_update]) + 1
        }} AS meta
    """
    return (query, query_params)


def build_fetch_incoming_query(
    entity_class: type[Entity], entity_id: uuid.UUID
) -> tuple[str, dict]:
    """Build the query for the relations *to* an entity.

    Every relation is stored as a forward edge and a reverse edge marked
    `reverse: true`, so the relations to an entity are the reverse edges leading
    out of it. An entity can be related to through a chain of reified relations
    and embedded objects (`Statement -> Date -> Identification -> Person`); for
    each reverse edge, this follows the chain up to the node that holds the
    relation (the document, or entity, that the chain starts from).

    Each row has the reverse edge's name, the nodes of the chain from the one next
    to the entity up to that node (and the names of the edges between them), the
    targets of the first of them, and what is needed for the `meta` of that node.
    """
    params = {"id": str(entity_id), "type": entity_class.__name__}
    query = """
    MATCH (entity:PGIndexableNode {id: $id})
    WHERE $type IN labels(entity)
    MATCH (entity)-[first]->(next)
    WHERE coalesce(first.reverse, false)
    OPTIONAL MATCH ascent = (next)-[*BFS ..10 (edge, node | coalesce(edge.reverse, false))]->(top)
    WHERE (next:ReifiedRelation OR next:ReifiedRelationDocument OR next:Embedded)
      AND ALL(chain_node IN nodes(ascent)[0..-1]
              WHERE chain_node:ReifiedRelation OR chain_node:ReifiedRelationDocument OR chain_node:Embedded)
      AND NOT (top:ReifiedRelation OR top:ReifiedRelationDocument OR top:Embedded)
    WITH first, next, ascent, coalesce(top, next) AS holder
    OPTIONAL MATCH (hn:HeadNode {id: holder.head_node_id})
    WITH first, next, ascent, holder, coalesce(hn, holder) AS headnode
    // (what has been deleted no longer refers to the entity)
    WHERE NOT coalesce(CASE WHEN holder:Entity THEN holder.deleted ELSE headnode.deleted END, false)
    OPTIONAL MATCH (headnode)<-[:is_creation_of]-(creation:PGCreation)-[:created_by]->(creator:PGUser)
    CALL {
        WITH headnode
        OPTIONAL MATCH (headnode)<-[:is_update_of]-(update:PGUpdate)-[:updated_by]->(update_user:PGUser)
        RETURN update.updated_when AS updated_when, update_user.username AS updated_by
        ORDER BY update.updated_when DESC
        LIMIT 1
    }
    RETURN
        type(first) AS first_edge_type,
        CASE WHEN ascent IS NULL
            THEN [next{.*, _labels: labels(next)}]
            ELSE [chain_node IN nodes(ascent) | chain_node{.*, _labels: labels(chain_node)}]
        END AS chain,
        // All the targets of the reified relation next to the entity (the entity
        // itself, and any others). The others in the chain only lead to it.
        [(next)-[:target]->(target) | target{.*}] AS next_targets,
        CASE WHEN ascent IS NULL THEN [] ELSE [edge IN relationships(ascent) | type(edge)] END AS chain_edge_types,
        {
            created_by: creator.username,
            created_when: creation.created_when,
            updated_by: updated_by,
            updated_when: updated_when,
            head_node_type: headnode.type,
            head_node_id: headnode.id
        } AS creation_meta
    """
    return query, params
