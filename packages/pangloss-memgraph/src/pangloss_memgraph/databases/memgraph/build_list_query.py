from typing import LiteralString

from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity


def build_generic_list_query(
    object_class: type[Document | Entity],
    search_terms: str | None = None,
    page_number: int | None = None,
    page_size: int | None = None,
) -> tuple[LiteralString, dict]:
    if search_terms:
        params = {}
        return (
            """


        """,
            params,
        )

    else:
        params = {
            "node_type": object_class.__name__,
            "page_number": page_number or 1,
            "page_size": page_size or 50,
        }
        return (
            """
            MATCH (n)
            WHERE "Factoid" in labels(n)
            WITH count(n) AS total

            MATCH (n)
            WHERE "Factoid" in labels(n)
            WITH n, total
            ORDER BY n.id
            SKIP ($page_number - 1) * $page_size
            LIMIT $page_size

            OPTIONAL MATCH (hn:HeadNode {id: n.head_node_id})
            WITH n, total, coalesce(hn, n) AS headnode
            MATCH (headnode)<-[:is_creation_of]-(creation:PGCreation)
            MATCH (creation)-[:created_by]->(user:PGUser)

            WITH collect(n{.*, meta: {
                created_by: user.username,
                created_when: creation.created_when,
                updated_by: null,
                updated_when: null,
                semantic_spaces: n.semantic_spaces,
                semantic_space_labels: n.semantic_space_labels
            }}) AS items, total, toInteger(ceil(toFloat(total) / $page_size)) AS totalPages

            RETURN {
              results: items,
              count: total,
              page: $page_number,
              page_size: $page_size,
              page_count: toInteger(ceil(toFloat(total) / $page_size)),
              previous_page: CASE WHEN $page_number > 1 THEN $page_number - 1 ELSE null END,
              next_page: CASE WHEN $page_number < totalPages THEN $page_number + 1 ELSE null END
            } AS result
        """,
            params,
        )
