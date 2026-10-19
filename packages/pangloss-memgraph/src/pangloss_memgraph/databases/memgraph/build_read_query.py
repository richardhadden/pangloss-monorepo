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
    OPTIONAL MATCH p1 = (root)-[*BFS (e, n | NOT n:Entity)]->(intermediate)-[]->(:Entity)
    OPTIONAL MATCH p2 =  (root)-[*BFS]->(intermediate)-[]->(:Document)
    OPTIONAL MATCH p3 = (root)-[]->(:Entity)
    WITH headnode, root, creation, user, updated_by, updated_when, collect(p1) AS indirect_paths, collect(p2) AS paths_to_docs, collect(p3) AS direct_paths, collect(rp) as root_path
    WITH headnode, creation, user, updated_by, updated_when, indirect_paths + direct_paths + paths_to_docs + root_path AS paths, root
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
