from typing import LiteralString

from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity

from pangloss_neo4j.databases.neo4j.schema import (
    search_patterns as schema_search_patterns,
)
from pangloss_neo4j.databases.neo4j.visibility import unpublished_visible

# The deep search (see docs/deep-search.md). Nothing large is carried from row to row: the hits are reduced to
# the ids of the documents (the roots) that have every word, and only those are expanded. (It once kept a list of
# every hit on each row, and took time and memory by the number of rows times the number of hits.)
#
# $tokens: one `.*word.*` for each word
# $limit: the most hits of the text index looked at for each
# $targetType: the class listed
# $page (1-indexed), $page_size
_DEEP_ROOTS = """
    UNWIND $tokens AS token
    CALL db.index.fulltext.queryNodes("label_text", token, {limit: $limit}) YIELD node AS matchedNode
    CALL (matchedNode) {
      WITH matchedNode
      WHERE NOT "Entity" IN labels(matchedNode)
      RETURN coalesce(matchedNode.head_node_id, matchedNode.id) AS treeRootId
      UNION
      WITH matchedNode
      WHERE "Entity" IN labels(matchedNode)
      MATCH (matchedNode)--(neighbor:PGIndexableNode)
      WHERE NOT "Entity" IN labels(neighbor)
      RETURN coalesce(neighbor.head_node_id, neighbor.id) AS treeRootId
    }
    // (a root qualifies if every word is found somewhere in its tree)
    WITH treeRootId, count(DISTINCT token) AS wordsFound
    WHERE wordsFound = size($tokens)
    WITH collect(treeRootId) AS qualifyingRoots
    UNWIND qualifyingRoots AS rootId
"""

# (the documents of the class in the trees found; they are ordered by the label of their head node)
_DEEP_DOCUMENTS = """
    CALL (rootId) {
      MATCH (n:PGIndexableNode {id: rootId})
      WHERE $targetType IN labels(n)
      RETURN n
      UNION
      MATCH (n:PGIndexableNode {head_node_id: rootId})
      WHERE $targetType IN labels(n)
      RETURN n
    }
    WITH DISTINCT n
    // (what has been deleted is not listed: a deleted entity, or a node of a deleted document)
    OPTIONAL MATCH (n_head:HeadNode {id: n.head_node_id})
    WITH n, n_head
    WHERE NOT coalesce(CASE WHEN n:Entity THEN n.deleted ELSE coalesce(n_head, n).deleted END, false)
AND (n:Entity OR $see_unpublished OR coalesce(coalesce(n_head, n).published, true))
AND ($published IS NULL OR coalesce(coalesce(n_head, n).published, true) = $published)
AND ($review_status IS NULL OR coalesce(n_head, n).review_status = $review_status)
    WITH n, toLower(coalesce(coalesce(n_head, n).label, "")) AS headLabel
    ORDER BY headLabel, n.id
"""

# (the entities of the class that the nodes of the trees found refer to; ordered by their labels)
_DEEP_ENTITIES = """
    CALL (rootId) {
      MATCH (t:PGIndexableNode {id: rootId})
      RETURN t
      UNION
      MATCH (t:PGIndexableNode {head_node_id: rootId})
      RETURN t
    }
    WITH DISTINCT t
    // (what has been deleted is not listed: a deleted entity, or a node of a deleted document)
    OPTIONAL MATCH (t_head:HeadNode {id: t.head_node_id})
    WITH t, t_head
    WHERE NOT coalesce(CASE WHEN t:Entity THEN t.deleted ELSE coalesce(t_head, t).deleted END, false)
AND (t:Entity OR $see_unpublished OR coalesce(coalesce(t_head, t).published, true))
AND ($published IS NULL OR coalesce(coalesce(t_head, t).published, true) = $published)
AND ($review_status IS NULL OR coalesce(t_head, t).review_status = $review_status)
    MATCH (t)--(n:Entity)
    WHERE $targetType IN labels(n)
    WITH DISTINCT n
    // (the same for the entity found)
    OPTIONAL MATCH (n_head:HeadNode {id: n.head_node_id})
    WITH n, n_head
    WHERE NOT coalesce(CASE WHEN n:Entity THEN n.deleted ELSE coalesce(n_head, n).deleted END, false)
AND (n:Entity OR $see_unpublished OR coalesce(coalesce(n_head, n).published, true))
AND ($published IS NULL OR coalesce(coalesce(n_head, n).published, true) = $published)
AND ($review_status IS NULL OR coalesce(n_head, n).review_status = $review_status)
    WITH n, toLower(coalesce(coalesce(n_head, n).label, "")) AS headLabel
    ORDER BY headLabel, n.id
"""

# (the page of what is ordered above, and its enrichment, isolated so that it always returns exactly one row)
_DEEP_PAGE = """
    WITH collect(n) AS allResults
    WITH allResults, size(allResults) AS total

    CALL {
      WITH allResults
      UNWIND allResults AS n
      WITH n
      SKIP ($page - 1) * $page_size
      LIMIT $page_size

      OPTIONAL MATCH (hn:HeadNode {id: n.head_node_id})
      WITH n, coalesce(hn, n) AS headnode
      MATCH (headnode)<-[:is_creation_of]-(creation:PGCreation)
      MATCH (creation)-[:created_by]->(user:PGUser)

      WITH collect(n{.*, meta: {
          created_by: user.username,
          created_when: creation.created_when,
          updated_by: null,
          updated_when: null,
          semantic_spaces: coalesce(n.`meta.semantic_spaces`, []),
          context_labels: n.`meta.context_labels#json`,
          head_node_id: n.head_node_id,
          head_node_type: n.head_node_type,
          is_head_node: n:HeadNode,
          published: coalesce(headnode.published, true),
          review_status: headnode.review_status
      }}) AS pagedResults
      RETURN pagedResults
    }

    RETURN {
      results: pagedResults,
      count: total,
      page: $page,
      page_size: $page_size,
      page_count: toInteger(ceil(toFloat(total) / $page_size)),
      previous_page: CASE WHEN $page > 1 THEN $page - 1 ELSE null END,
      next_page: CASE WHEN $page < toInteger(ceil(toFloat(total) / $page_size)) THEN $page + 1 ELSE null END
    } AS response
"""


# What the text index is asked for, of each word, if the settings say nothing (`SEARCH_HIT_LIMIT`). The index
# gives 1000 if it is not asked: a word with more hits than that had most of its results left out, unseen.
DEFAULT_HIT_LIMIT = 100_000

# Whether some word of the search has more hits than `$limit` (asked for one more, to know): then the results
# of the list are not all there are. Apart from the list's own query so that it gives an answer when the list is empty.
TRUNCATION_QUERY: LiteralString = """
    UNWIND $patterns AS pattern
    CALL db.index.fulltext.queryNodes("label_text", pattern, {limit: $limit + 1}) YIELD node
    WITH pattern, count(node) AS hits
    RETURN coalesce(max(hits), 0) > $limit AS truncated
"""


# (a pattern for each word of the search: `*word*`, folded as the index folds, with what Lucene reads as syntax left out;
# see `schema.search_patterns`)
search_patterns = schema_search_patterns


def build_truncation_query(
    search_terms: str | None, hit_limit: int = DEFAULT_HIT_LIMIT
) -> tuple[LiteralString, dict]:
    return TRUNCATION_QUERY, {
        "patterns": search_patterns(search_terms),
        "limit": hit_limit,
    }


def build_generic_list_query(
    object_class: type[Document | Entity],
    search_terms: str | None = None,
    page_number: int | None = None,
    page_size: int | None = None,
    deep_search: bool = False,
    published: bool | None = None,
    review_status: str | None = None,
    hit_limit: int = DEFAULT_HIT_LIMIT,
) -> tuple[LiteralString, dict]:
    query, params = _build_list_query(
        object_class, search_terms, page_number, page_size, deep_search, hit_limit
    )
    # (a document that is not published is listed only for those who may see it)
    params["see_unpublished"] = unpublished_visible()
    # (to list only the documents that are, or are not, published, or in a status of review)
    params["published"] = published
    params["review_status"] = review_status
    return query, params


def _build_list_query(
    object_class: type[Document | Entity],
    search_terms: str | None = None,
    page_number: int | None = None,
    page_size: int | None = None,
    deep_search: bool = False,
    hit_limit: int = DEFAULT_HIT_LIMIT,
) -> tuple[LiteralString, dict]:
    patterns = search_patterns(search_terms)

    if patterns and deep_search:
        params = {
            "targetType": object_class.__name__,
            "page": page_number or 1,
            "page_size": page_size or 50,
            "tokens": patterns,
            "limit": hit_limit,
        }
        if object_class.__metatype__ == "Document":
            found = _DEEP_DOCUMENTS
        else:
            found = _DEEP_ENTITIES
        return _DEEP_ROOTS + found + _DEEP_PAGE, params
    if patterns:
        params = {
            "node_type": object_class.__name__,
            "page_number": page_number or 1,
            "page_size": page_size or 50,
            "patterns": patterns,
            "limit": hit_limit,
        }
        return (
            """
            UNWIND $patterns AS pattern
            CALL db.index.fulltext.queryNodes("label_text", pattern, {limit: $limit}) YIELD node, score
            WITH node AS n, pattern, max(score) AS patternScore
            WITH n, count(*) AS matchedPatterns, sum(patternScore) AS totalScore
            WHERE matchedPatterns = size($patterns)
              AND $node_type IN labels(n)
            WITH n, totalScore
            // (what has been deleted is not listed: a deleted entity, or a node of a deleted document)
            OPTIONAL MATCH (n_head:HeadNode {id: n.head_node_id})
            WITH n, totalScore, n_head
            WHERE NOT coalesce(CASE WHEN n:Entity THEN n.deleted ELSE coalesce(n_head, n).deleted END, false)
AND (n:Entity OR $see_unpublished OR coalesce(coalesce(n_head, n).published, true))
AND ($published IS NULL OR coalesce(coalesce(n_head, n).published, true) = $published)
AND ($review_status IS NULL OR coalesce(n_head, n).review_status = $review_status)
            WITH n, totalScore
            ORDER BY totalScore DESC, elementId(n)
            WITH collect(n) AS allNodes
            WITH allNodes,
                 size(allNodes) AS total,
                 toInteger(ceil(toFloat(size(allNodes)) / $page_size)) AS totalPages
            WITH allNodes[($page_number - 1) * $page_size .. $page_number * $page_size] AS pageNodes,
                 total, totalPages
            CALL {
                WITH pageNodes
                UNWIND pageNodes AS n
                OPTIONAL MATCH (hn:HeadNode {id: n.head_node_id})
                WITH n, coalesce(hn, n) AS headnode
                OPTIONAL MATCH (headnode)<-[:is_creation_of]-(creation:PGCreation)
                OPTIONAL MATCH (creation)-[:created_by]->(user:PGUser)
                RETURN collect(n{.*, meta: {
                    created_by: user.username,
                    created_when: creation.created_when,
                    updated_by: null,
                    updated_when: null,
                    semantic_spaces: coalesce(n.`meta.semantic_spaces`, []),
                    context_labels: n.`meta.context_labels#json`,
                    head_node_id: n.head_node_id,
                    head_node_type: n.head_node_type,
                    is_head_node: n:HeadNode,
                    published: coalesce(headnode.published, true),
                    review_status: headnode.review_status
                }}) AS items
            }
            RETURN {
                results: items,
                count: total,
                page: $page_number,
                page_size: $page_size,
                page_count: totalPages,
                previous_page: CASE WHEN $page_number > 1 THEN $page_number - 1 ELSE null END,
                next_page: CASE WHEN $page_number < totalPages THEN $page_number + 1 ELSE null END
            } AS result;
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
            MATCH (n:$($node_type))
            // (what has been deleted is not listed: a deleted entity, or a node of a deleted document)
            OPTIONAL MATCH (counted_head:HeadNode {id: n.head_node_id})
            WITH n, counted_head
            WHERE NOT coalesce(CASE WHEN n:Entity THEN n.deleted ELSE coalesce(counted_head, n).deleted END, false)
AND (n:Entity OR $see_unpublished OR coalesce(coalesce(counted_head, n).published, true))
AND ($published IS NULL OR coalesce(coalesce(counted_head, n).published, true) = $published)
AND ($review_status IS NULL OR coalesce(counted_head, n).review_status = $review_status)

                        WITH count(n) AS total

                        MATCH (n:$($node_type))
            OPTIONAL MATCH (listed_head:HeadNode {id: n.head_node_id})
            WITH n, total, listed_head
            WHERE NOT coalesce(CASE WHEN n:Entity THEN n.deleted ELSE coalesce(listed_head, n).deleted END, false)
AND (n:Entity OR $see_unpublished OR coalesce(coalesce(listed_head, n).published, true))
AND ($published IS NULL OR coalesce(coalesce(listed_head, n).published, true) = $published)
AND ($review_status IS NULL OR coalesce(listed_head, n).review_status = $review_status)

                        WITH n, total
                        ORDER BY n.id
                        SKIP ($page_number - 1) * $page_size
                        LIMIT $page_size

                        OPTIONAL MATCH (hn:HeadNode:PGIndexableNode {id: n.head_node_id})
                        WITH n, total, coalesce(hn, n) AS headnode
                        MATCH (headnode)<-[:is_creation_of]-(creation:PGCreation)
                        MATCH (creation)-[:created_by]->(user:PGUser)

                        // The page, as one row: the facets are of the entities the whole page refers
                        // to (computed for each node they were one row each, and a page of
                        // documents that refer to entities came back as many rows)
                        WITH collect(n{.*, meta: {
                            created_by: user.username,
                            created_when: creation.created_when,
                            updated_by: null,
                            updated_when: null,
                            semantic_spaces: coalesce(n.`meta.semantic_spaces`, []),
                            context_labels: n.`meta.context_labels#json`,
                            head_node_id: n.head_node_id,
                            head_node_type: n.head_node_type,
                            is_head_node: n:HeadNode,
                            published: coalesce(headnode.published, true),
                            review_status: headnode.review_status
                        }}) AS items, collect(n) AS page_nodes, total,
                        toInteger(ceil(toFloat(total) / $page_size)) AS totalPages

                        CALL {
                          WITH page_nodes
                          UNWIND page_nodes AS m
                          OPTIONAL MATCH (m)-->(entities:Entity)
                          WITH entities
                          WHERE entities IS NOT NULL
                          WITH entities.type AS type, collect(DISTINCT entities{.id, .type, .label}) AS nodes
                          RETURN collect({type: type, nodes: nodes}) AS facets
                        }

                        RETURN {
                          results: items,
                          count: total,
                          page: $page_number,
                          page_size: $page_size,
                          page_count: toInteger(ceil(toFloat(total) / $page_size)),
                          previous_page: CASE WHEN $page_number > 1 THEN $page_number - 1 ELSE null END,
                          next_page: CASE WHEN $page_number < totalPages THEN $page_number + 1 ELSE null END,
                          facets: facets
                        } AS result
        """,
            params,
        )
