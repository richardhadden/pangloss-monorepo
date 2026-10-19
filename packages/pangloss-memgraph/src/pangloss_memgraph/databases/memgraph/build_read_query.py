import uuid

from pangloss_models.model_bases.document import Document

from pangloss_memgraph.databases.memgraph.build_create_query import QueryParams


def build_fetch_document_query(
    document_class: type[Document], document_id: uuid.UUID
) -> tuple[str, QueryParams]:
    query_params = QueryParams()
    document_id_identifier = query_params.add(document_id)
    document_type_identifier = query_params.add(document_class.__name__)
    query = f"""
    MATCH rp = (root:PGIndexableNode {{id: ${document_id_identifier}}})
    WHERE ${document_type_identifier} in labels(root)
    OPTIONAL MATCH (hn:HeadNode {{id: root.head_node_id}})
    WITH root, rp, coalesce(hn, root) AS headnode
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
    OPTIONAL MATCH tree_path = (root)-[*BFS (e, n | NOT n:Entity AND NOT coalesce(e.reverse, false))]->(descendant)
    WITH headnode, root, creation, user, updated_by, updated_when, rp, collect(tree_path) AS tree_paths
    // The entities that the nodes of the tree refer to
    OPTIONAL MATCH entity_path = (root)-[*BFS (e, n | NOT n:Entity AND NOT coalesce(e.reverse, false))]->(holder)-[holder_edge]->(:Entity)
    WHERE NOT coalesce(holder_edge.reverse, false)
    WITH headnode, root, creation, user, updated_by, updated_when, rp, tree_paths, collect(entity_path) AS entity_paths
    OPTIONAL MATCH root_entity_path = (root)-[root_edge]->(:Entity)
    WHERE NOT coalesce(root_edge.reverse, false)
    WITH headnode, root, creation, user, updated_by, updated_when,
         collect(rp) + tree_paths + entity_paths + collect(root_entity_path) AS paths
    CALL convert_c.to_tree(paths) YIELD value
    RETURN map.merge(value, {{meta: {{
        created_by: user.username,
        created_when: creation.created_when,
        updated_by: updated_by, updated_when: updated_when,
        semantic_spaces: root.meta.semantic_spaces,
        context_labels: root.meta.context_labels,
        head_node_type: headnode.type,
        head_node_id: headnode.id
    }}}})
    """
    return (query, query_params)
