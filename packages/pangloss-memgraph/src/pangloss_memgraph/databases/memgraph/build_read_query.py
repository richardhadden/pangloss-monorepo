import uuid

from pangloss_models.model_bases import document
from pangloss_models.model_bases.document import Document

from pangloss_memgraph.databases.memgraph.build_create_query import QueryParams


def build_fetch_document_query(
    document_class: type[Document], document_id: uuid.UUID
) -> tuple[str, QueryParams]:
    query_params = QueryParams()
    document_id_identifier = query_params.add(document_id)
    document_type_identifier = query_params.add(document_class.__name__)
    query = f"""
    MATCH (root:PGIndexableNode {{id: ${document_id_identifier}}})
    WHERE ${document_type_identifier} in labels(root)
    MATCH (headnode:HeadNode) WHERE headnode = root OR headnode.id = root.id
    MATCH (headnode)<-[:is_creation_of]-(creation:PGCreation)
    MATCH (creation)-[:created_by]->(user:PGUser)

    OPTIONAL MATCH p1 = (root)-[*BFS (e, n | NOT n:Entity)]->(intermediate)
                -[]->(:Entity)
    OPTIONAL MATCH p2 = (root)-[*BFS]->()
    WITH root, creation, user, collect(p1) AS indirect_paths, collect(p2) as paths_to_docs

    OPTIONAL MATCH p3 = (root)-[]->(:Entity)
    WITH creation, user, indirect_paths, paths_to_docs,  collect(p3) AS direct_paths

    WITH creation, user, indirect_paths + direct_paths + paths_to_docs AS paths
    CALL convert_c.to_tree(paths) YIELD value
    RETURN map.merge(value, {{meta: {{created_by: user.username, created_when: creation.created_when, updated_by: null, updated_when: null}}}})
    """
    return (query, query_params)
